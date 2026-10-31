from __future__ import annotations

import json
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import load_workbook

from .db import digest, norm, now
from .excel import REVIEW_HEADERS, review_book, text
from .questionnaire import extract, patch_copy
from .grounding import known_draft, load_selections
from .providers import TaskRouter
from .gap_review import ingest_gaps,make_gaps
from .sme_review import export_sme_review


RISK = re.compile(r"\b(guarantee\w*|contract\w*|indemn\w*|liability|certif\w*|compliant|compliance|warrant\w*|sla|soc\s*2|iso\s*27001|hipaa|pci|vpat|wcag)\b", re.I)


def draft(store, question, scope, router=None, max_age_days=365):
    router = router or TaskRouter()
    evidence = store.retrieve(question, scope)
    if not evidence:
        return {"answer": "", "status": "insufficient", "reason": "No approved evidence found in scope", "evidence": []}
    best = evidence[0]
    answer = best["answer"]
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(best["approved_at"])).days
    pending = any(p["target"] == best["id"] or norm(p["question"]) in {norm(question), best["normalized"]}
        for p in store.db.execute("SELECT target,question FROM proposals WHERE status='pending' AND scope=? AND kind='canonical'", (scope,)))
    risk = bool(RISK.search(question + " " + answer))
    if best["exact"] and age <= max_age_days and not pending and not risk:
        status, reason = "high-confidence", "Approved exact question or current approved variant"
    elif best["exact"]:
        status, reason = "needs-review", "Exact evidence requires freshness, conflict or commitment review"
    elif best["score"] >= 0.65:
        status, reason = "needs-review", "Related evidence; equivalence is not approved"
    else:
        status, reason = "partial", "Related evidence covers only part of the wording; requirement coverage is unverified"
    # Only exact/approved-variant reuse can avoid generation. Models never promote status.
    try:
        if not best["exact"]:
            generated = router.generate(question, evidence)
            answer = generated["answer"]
        for task in ("equivalence", "verification"):
            verdict = router.evaluate(task, question, evidence, answer)
            if not verdict["supported"]:
                return {"answer": "", "status": "insufficient", "reason": f"{task} rejected support", "evidence": evidence}
            if verdict["requires_review"]:
                status, reason = "needs-review", f"{task} requested SME review"
    except Exception:
        # Provider errors must not leak secrets or leave a confident result.
        answer, status, reason = best["answer"], "needs-review", "Provider failed or returned invalid evidence; extractive fallback"
    return {"answer": answer, "status": status, "reason": reason, "evidence": evidence}


def answer_rfp(store, source, scope, config=None, max_age_days=365, *, evidence_map=None, known_only=True, **mapping):
    if max_age_days < 0:
        raise ValueError("max_age_days must be nonnegative")
    source = Path(source).resolve()
    before = source.read_bytes()
    layouts, rows = extract(source, **mapping)
    if source.read_bytes() != before:
        raise ValueError("Source changed during extraction; retry from a stable copy")
    if not rows:
        raise ValueError("No questionnaire rows")
    selections,selection_snapshot=load_selections(evidence_map,before,scope,rows)
    router = TaskRouter.load(config)
    run_id = uuid.uuid4().hex
    output = store.root / "runs" / run_id
    output.mkdir()
    extension=source.suffix.lower()
    snapshot = output / ("input"+extension)
    snapshot.write_bytes(before)
    drafts, changes = [], {}
    # A single read transaction pins retrieval to a consistent approved KB snapshot.
    try:
        with store.db:
            store.db.execute("BEGIN")
            for row in rows:
                result = known_draft(store,row,scope,router,max_age_days,selections.get((row["sheet"],row["response_cell"]))) if known_only else draft(store, row["question"], scope, router, max_age_days)
                result.update(row, id=uuid.uuid4().hex, run_id=run_id, scope=scope)
                if not result["answer"] and not result.get("requirements"):
                    result["requirements"]=[{"id":"unresolved","text":row["question"],"state":"missing",
                        "sme_question":row["question"],"note":result["reason"]}]
                state = "written"
                if row["existing"]:
                    state = "preserved-existing"
                elif row["merged"] or row["protected"] or row["validated"]:
                    state = "preserved-merged-protected-or-validated"
                elif not result["answer"]:
                    state = "blank-insufficient"
                else:
                    value = result["answer"]
                    if not known_only and result["status"] != "high-confidence":
                        value = f'[{result["status"].upper()}: SME REVIEW] ' + value
                    changes.setdefault(row["sheet"], {})[row["response_cell"]] = value
                result["write_state"] = state
                result["sme_gaps"] = make_gaps(result)
                drafts.append(result)
            patch_copy(snapshot, output / ("completed"+extension), changes, mapping=mapping)
            if known_only:
                export_sme_review(store,output / "sme-review.xlsx",drafts)
            else:
                review_book(output / "sme-review.xlsx", drafts)  # Legacy synthetic demo/feedback.
            manifest = {"id": run_id, "source": str(source), "source_sha256": digest(before),
                "scope": scope, "layouts": layouts, "counts": dict(Counter(d["status"] for d in drafts)),
                "write_counts":dict(Counter(d["write_state"] for d in drafts)),
                "missing_items":sum(i["state"]=="missing" for d in drafts for i in d.get("requirements",[])),
                "known_only":known_only,"output_format":extension,
                "evidence_map_sha256":selection_snapshot["sha256"] if selection_snapshot else None,
                "usage": router.usage, "external_calls": router.calls, "created_at": now(),
                "task_routing": {task: {k: v for k, v in settings.items() if k in {
                    "provider", "model", "allow_network", "max_output_tokens", "timeout_seconds"}}
                    for task, settings in router.config.get("tasks", {}).items()},
                "limits": router.config.get("limits", {}),
                "config": str(Path(config).resolve()) if config else "offline-extractive"}
            store.db.execute("INSERT INTO runs VALUES(?,?,?)", (run_id, json.dumps(manifest), now()))
            for d in drafts:
                store.db.execute("INSERT INTO drafts VALUES(?,?,?)", (d["id"], run_id, json.dumps(d)))
            store.audit("rfp-agent", "run_created", {"run": run_id})
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2))
        (output / "drafts.json").write_text(json.dumps(drafts, indent=2))
        if selection_snapshot:
            (output / "evidence-map.json").write_text(json.dumps(selection_snapshot,indent=2))
        return dict(manifest, output=str(output))
    except Exception:
        # Leave an explicit failure marker; no success manifest is produced.
        (output / "FAILED.txt").write_text("Run failed. Outputs are incomplete; do not use. See CLI error.")
        raise


def ingest_feedback(store, path):
    from .sme_review import looks_like_sme_review,apply_sme_review
    if looks_like_sme_review(path):
        return apply_sme_review(store,path)
    path = Path(path).resolve()
    content = path.read_bytes()
    book = load_workbook(path, data_only=False)
    try:
        ws = book["SME review"]
        if [c.value for c in ws[1]] != REVIEW_HEADERS:
            raise ValueError("Review headers were changed")
        staged, seen = [], set()
        with store.db:
            for cells in ws.iter_rows(min_row=2):
                values = {h: text(c.value) for h, c in zip(REVIEW_HEADERS, cells)}
                action = values["action"].casefold()
                if not action or action == "skip":
                    continue
                if action not in {"canonical", "variant", "reject"}:
                    raise ValueError("Unknown feedback action")
                if any(c.data_type == "f" for c in cells):
                    raise ValueError("Formula cells are not permitted in feedback")
                did = values["draft_id"]
                if did in seen:
                    raise ValueError("Duplicate feedback draft ID")
                seen.add(did)
                row = store.db.execute("SELECT payload FROM drafts WHERE id=?", (did,)).fetchone()
                if not row:
                    raise ValueError("Unknown draft ID: use the original workspace")
                original = json.loads(row[0])
                if values["question"] != original["question"] or values["draft_answer"] != original["answer"]:
                    raise ValueError("Question or original draft was changed; edit corrected_answer only")
                reviewer, note = values["reviewer"], values["review_note"]
                if not reviewer or not note:
                    raise ValueError("Explicit reviewer and review_note are required")
                fingerprint = digest(json.dumps([did, action, values["corrected_answer"],
                    values["target_entry"], reviewer, note]).encode())
                if action == "reject":
                    if not store.db.execute("SELECT 1 FROM audit WHERE event='draft_rejected' AND payload=?",
                                            (json.dumps({"fingerprint": fingerprint, "draft": did, "note": note}),)).fetchone():
                        store.audit(reviewer, "draft_rejected", {"fingerprint": fingerprint, "draft": did, "note": note})
                    continue
                replay = store.db.execute("SELECT id FROM proposals WHERE fingerprint=?", (fingerprint,)).fetchone()
                if replay:
                    staged.append(replay[0])
                    continue
                target = int(values["target_entry"]) if values["target_entry"] else None
                if target is not None and target not in [e["id"] for e in original["evidence"]]:
                    raise ValueError("Target must be from this draft's evidence")
                if target is None and original["evidence"] and original["evidence"][0]["exact"]:
                    target = original["evidence"][0]["id"]
                if target is not None:
                    captured = next(e for e in original["evidence"] if e["id"] == target)
                    if store.evidence(target)["revision"] != captured["revision"]:
                        raise ValueError("Review evidence is stale; generate a fresh RFP review")
                answer = values["corrected_answer"]
                if action == "variant":
                    if target is None:
                        raise ValueError("Variant requires target_entry")
                    canonical = store.evidence(target)["answer"]
                    if answer and answer != canonical:
                        raise ValueError("Variant cannot change canonical answer")
                    answer = canonical
                elif not answer:
                    raise ValueError("Canonical proposal requires explicit corrected_answer")
                provenance = {"source": str(path), "sha256": digest(content), "draft_id": did,
                    "run_id": original["run_id"], "reviewer": reviewer, "note": note,
                    "evidence": original["evidence"]}
                staged.append(store.stage(question=original["question"], answer=answer, scope=original["scope"],
                    provenance=provenance, submitter=reviewer, kind=action, target=target, fingerprint=fingerprint))
            staged.extend(ingest_gaps(store,book,path,content))
            snapshot = store.root / "sources" / (digest(content) + ".xlsx")
            if not snapshot.exists():
                snapshot.write_bytes(content)
        return staged
    finally:
        book.close()
