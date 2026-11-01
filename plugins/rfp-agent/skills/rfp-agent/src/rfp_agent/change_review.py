"""Editable import-change review packets and transactional SME-approved KB updates."""
from __future__ import annotations

import csv
from datetime import date, datetime
import difflib
import io
import json
from pathlib import Path
import uuid

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from .db import digest, norm, now
from .excel import literal, text


HEADERS = ["question", "current_answer", "proposed_answer", "final_answer", "review_status",
           "sme_name", "review_note", "reviewed_on", "current_source", "proposed_source",
           "evidence_status", "review_gap", "change_type", "change_summary", "scope",
           "current_revision", "proposal_id", "review_id"]
EDITABLE = {"final_answer", "review_status", "sme_name", "review_note", "reviewed_on"}
IMMUTABLE = set(HEADERS) - EDITABLE
PROPOSAL_FIELDS = ("id", "fingerprint", "kind", "question", "answer", "scope", "target", "base",
                   "provenance", "submitted_by", "status")
INSTRUCTIONS = [
    "KB CHANGE REVIEW — edit final_answer, review_status, sme_name, review_note and reviewed_on only.",
    "Compare current_answer and proposed_answer. final_answer is prefilled with the proposed wording; replace it with the wording you approve.",
    "Set review_status to Approved, Rejected, Needs review or Pending. Only Approved rows update approved KB answers. Rejected rows close the pending proposal.",
    "An Approved or Rejected row requires sme_name. review_note and reviewed_on are optional; include a reason or evidence reference when useful.",
    "The SME must differ from the original proposal submitter. Names are local audit fields, not cryptographically authenticated identities.",
    "Approved answers cannot be blank. Complete blank answers only when you have authority/evidence to supply them. Unknown capabilities must not be invented.",
    "Leave unresolved rows Pending or Needs review. Their edits are archived in the returned file but do not change approved KB content.",
    "Keep all headers and context/ID cells intact. You may sort complete rows or return only the rows you reviewed. Do not mix review IDs or duplicate a proposal row.",
    "Upload the returned XLSX/CSV to the skill and request application of the SME review. That upload authorizes applying explicit Approved/Rejected decisions without another approval round.",
    "The skill checks the original proposal, review ID, source context and current KB revision before applying the batch. Stale or altered context blocks the batch; regenerate a fresh review.",
    "Identical reuploads are safe and do not create duplicate revisions. A changed decision on an already-applied row requires a new change-review packet.",
    "Forward referenced source documents separately if the SME cannot access the listed source paths. The workbook contains source references, not the full original documents.",
]


def proposal_state(proposal):
    return {key: proposal[key] for key in PROPOSAL_FIELDS}


def reference(provenance):
    p = json.loads(provenance) if isinstance(provenance, str) else provenance
    keys = ("source", "location", "sha256", "source_record_id", "source_metadata", "document_version", "url")
    return json.dumps({k: p[k] for k in keys if k in p}, ensure_ascii=False, sort_keys=True)


def current_target(store, proposal):
    target = proposal["target"]
    if target is None:
        row = store.db.execute("SELECT id FROM entries WHERE normalized=? AND scope=?",
                               (norm(proposal["question"]), proposal["scope"])).fetchone()
        if row:
            target = row[0]
    evidence = store.evidence(target) if target is not None else None
    if target is not None and (not evidence or evidence["scope"] != proposal["scope"]):
        raise ValueError("Review target is missing or belongs to another scope")
    return target, evidence


def summary(before, after):
    if not before:
        return "New canonical answer" if after else "New unanswered intake item — SME answer required"
    if before == after:
        return "Answer unchanged; review source/provenance refresh"
    removed, added = [], []
    for line in difflib.ndiff(before.splitlines(), after.splitlines()):
        if line.startswith("- "):
            removed.append(line[2:])
        elif line.startswith("+ "):
            added.append(line[2:])
    return "REMOVED:\n" + "\n".join(removed) + "\n\nADDED:\n" + "\n".join(added)


def csv_safe(value):
    value = text(value)
    # Neutralize formula-looking values when a generated CSV is opened in Excel.
    return "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r")) else value


def write_packet(path, rows):
    if path.suffix.lower() == ".csv":
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(HEADERS)
            writer.writerows([[csv_safe(row[h]) for h in HEADERS] for row in rows])
        return
    book = Workbook()
    ws = book.active
    ws.title = "KB change review"
    ws.append(HEADERS)
    for row in rows:
        ws.append([None] * len(HEADERS))
        for col, header in enumerate(HEADERS, 1):
            cell = ws.cell(ws.max_row, col)
            literal(cell, row[header])
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            if header in EDITABLE:
                cell.fill = PatternFill("solid", fgColor="FFF2CC")
        ws.row_dimensions[ws.max_row].height = 180
    widths = {"A": 52, "B": 66, "C": 66, "D": 66, "E": 20, "F": 25, "G": 48, "H": 20,
              "I": 48, "J": 48, "K": 20, "L": 52, "M": 23, "N": 66, "O": 22,
              "P": 20, "Q": 16, "R": 35}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width
    for cell in ws[1]:
        editable = cell.value in EDITABLE
        cell.fill = PatternFill("solid", fgColor="166568" if editable else "17365D")
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = ws.dimensions
    ws.print_title_rows = "1:1"
    validation = DataValidation(type="list", formula1='"Pending,Approved,Rejected,Needs review"')
    validation.errorTitle = "Choose a review status"
    validation.error = "Use Pending, Approved, Rejected or Needs review"
    validation.showErrorMessage = True
    validation.errorStyle = "stop"
    ws.add_data_validation(validation)
    validation.add(f"E2:E{max(2,ws.max_row)}")
    instructions = book.create_sheet("Instructions", 0)
    for line in INSTRUCTIONS:
        instructions.append([line])
        instructions.cell(instructions.max_row, 1).alignment = Alignment(wrap_text=True, vertical="top")
        instructions.row_dimensions[instructions.max_row].height = 52
    instructions.column_dimensions["A"].width = 120
    book.active = 1
    book.save(path)
    book.close()


def export_changes(store, proposal_ids=None, scope=None, output=None, file_format="xlsx"):
    if file_format not in {"xlsx", "csv"}:
        raise ValueError("Change-review format must be xlsx or csv")
    selected = set(proposal_ids) if proposal_ids is not None else None
    if selected == set():
        return None
    review_id = uuid.uuid4().hex
    path = Path(output).expanduser().resolve() if output else store.root / "reviews" / review_id / ("kb-change-review." + file_format)
    if path.suffix.lower() != "." + file_format or path.exists():
        raise ValueError("Review output must be a new file with the selected format extension")
    path.parent.mkdir(parents=True, exist_ok=True)
    with store.transaction():
        proposals = store.db.execute("SELECT * FROM proposals WHERE status='pending' ORDER BY id").fetchall()
        proposals = [p for p in proposals if (selected is None or p["id"] in selected) and (scope is None or p["scope"] == scope)]
        if selected is not None:
            mismatched = store.db.execute("SELECT id,scope FROM proposals WHERE id IN (" + ','.join('?' for _ in selected) + ")", tuple(selected)).fetchall()
            if scope is not None and any(p["scope"] != scope for p in mismatched):
                raise ValueError("Selected proposals belong to another scope")
        if not proposals:
            return None
        snapshots, rows = [], []
        for proposal in proposals:
            target, current = current_target(store, proposal)
            old_answer = current["answer"] if current else ""
            meta = json.loads(proposal["provenance"])
            kind = "question_variant" if proposal["kind"] == "variant" else (
                "new_answer" if target is None else "source_refresh" if old_answer == proposal["answer"] else "update_answer")
            row = dict(zip(HEADERS, [proposal["question"], old_answer, proposal["answer"], proposal["answer"],
                "Pending", "", "", "", reference(current["provenance"]) if current else "",
                reference(meta), meta.get("evidence_status", ""), meta.get("review_gap", ""), kind,
                summary(old_answer, proposal["answer"]), proposal["scope"], str(current["revision"]) if current else "",
                str(proposal["id"]), review_id]))
            snapshots.append({"proposal": proposal_state(proposal), "review_target": target,
                              "review_base": current["revision"] if current else None, "row": row})
            rows.append(row)
        store.db.execute("INSERT INTO change_reviews VALUES(?,?,?,?)", (review_id, now(), scope, str(path)))
        for snap in snapshots:
            store.db.execute("INSERT INTO change_review_rows(review_id,proposal_id,snapshot) VALUES(?,?,?)",
                             (review_id, snap["proposal"]["id"], json.dumps(snap)))
        write_packet(path, rows)
        store.audit("rfp-agent", "change_review_exported", {"review_id": review_id, "rows": len(rows), "path": str(path)})
    return {"review_id": review_id, "path": str(path), "rows": len(rows), "format": file_format}


def read_packet(path):
    if path.suffix.lower() == ".csv":
        rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
        if not rows or rows[0] != HEADERS:
            raise ValueError("Change-review headers were changed")
        if any(len(row) != len(HEADERS) for row in rows[1:] if any(row)):
            raise ValueError("Change-review row has an incorrect number of columns")
        return [dict(zip(HEADERS, [text(v) for v in row])) for row in rows[1:] if any(row)]
    if path.suffix.lower() != ".xlsx":
        raise ValueError("Returned change review must be XLSX or CSV")
    book = load_workbook(path, data_only=False)
    try:
        ws = book["KB change review"]
        if [cell.value for cell in ws[1]] != HEADERS:
            raise ValueError("Change-review headers were changed")
        rows = []
        for cells in ws.iter_rows(min_row=2):
            if not any(cell.value is not None for cell in cells):
                continue
            if any(cell.data_type == "f" for cell in cells):
                raise ValueError("Formula cells are not permitted in returned reviews")
            rows.append({header: (cell.value.isoformat() if isinstance(cell.value, (date, datetime)) else text(cell.value))
                         for header, cell in zip(HEADERS, cells)})
        return rows
    finally:
        book.close()


def looks_like_review(source):
    path = Path(source)
    if not path.is_file():
        return False
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as stream:
            headers = next(csv.reader(stream), [])
        return {"review_id", "proposal_id", "review_status"}.issubset(headers)
    if path.suffix.lower() == ".xlsx":
        book = load_workbook(path, read_only=True, data_only=False)
        try:
            return "KB change review" in book.sheetnames
        finally:
            book.close()
    return False


def apply_review(store, source):
    path = Path(source).expanduser().resolve()
    content = path.read_bytes()
    rows = read_packet(path)
    if path.read_bytes() != content:
        raise ValueError("Review changed while it was being read")
    review_ids = {r["review_id"] for r in rows}
    if len(review_ids) != 1:
        raise ValueError("Return a nonempty packet from one change review only")
    review_id = next(iter(review_ids))
    seen, decisions, replayed, deferred = set(), [], [], 0
    snapshot_path = store.root / "sources" / (digest(content) + path.suffix.lower())
    with store.transaction():
        if not store.db.execute("SELECT 1 FROM change_reviews WHERE id=?", (review_id,)).fetchone():
            raise ValueError("Unknown review ID: use the workspace that generated this review")
        if any(json.loads(r[0]).get("review_id") == review_id for r in store.db.execute(
                "SELECT payload FROM audit WHERE event='change_review_withdrawn'")):
            raise ValueError("Withdrawn review: use a current collision review")
        approved_targets = set()
        for row in rows:
            pid = int(row["proposal_id"])
            if pid in seen:
                raise ValueError("Duplicate proposal row in returned review")
            seen.add(pid)
            saved = store.db.execute("SELECT * FROM change_review_rows WHERE review_id=? AND proposal_id=?", (review_id, pid)).fetchone()
            if not saved:
                raise ValueError("Proposal is not part of this change review")
            snap = json.loads(saved["snapshot"])
            expected = snap["row"]
            for key in IMMUTABLE:
                actual = row[key]
                if path.suffix.lower() == ".csv" and actual == csv_safe(expected[key]):
                    actual = expected[key]
                if actual != expected[key]:
                    raise ValueError(f"Review context was changed in {key} for proposal {pid}")
            if path.suffix.lower() == ".csv" and row["final_answer"] == csv_safe(expected["final_answer"]):
                row["final_answer"] = expected["final_answer"]
            decision = row["review_status"].casefold().replace("-", " ")
            if decision in {"", "pending", "needs review"}:
                deferred += 1
                continue
            if decision not in {"approved", "rejected"}:
                raise ValueError("Review status must be Pending, Approved, Rejected or Needs review")
            actor, final = row["sme_name"].strip(), row["final_answer"].strip()
            if not actor:
                raise ValueError("Approved/Rejected decisions require sme_name")
            if actor.casefold() == snap["proposal"]["submitted_by"].strip().casefold():
                raise ValueError("Proposal submitter cannot approve or reject their own proposal")
            if decision == "approved" and not final:
                raise ValueError("Approved final_answer cannot be blank")
            key = digest(json.dumps([review_id, pid, decision, final, actor, row["review_note"], row["reviewed_on"]], ensure_ascii=False).encode())
            if saved["applied_fingerprint"]:
                if key != saved["applied_fingerprint"]:
                    raise ValueError("This review row was already applied with a different decision; generate a new review")
                replayed.append(json.loads(saved["application"]))
                continue
            proposal = store.db.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
            if not proposal or proposal_state(proposal) != snap["proposal"]:
                raise ValueError("Proposal changed or was resolved since export; generate a fresh review")
            if decision == "approved":
                target, current = current_target(store, proposal)
                if target != snap["review_target"] or (current["revision"] if current else None) != snap["review_base"]:
                    raise ValueError("Stale review: the approved KB changed; generate a fresh review")
                identity = (proposal["scope"], "entry", target) if target is not None else (proposal["scope"], "question", norm(proposal["question"]))
                if identity in approved_targets:
                    raise ValueError("Multiple Approved rows affect the same canonical answer; approve one and refresh related reviews")
                approved_targets.add(identity)
            decisions.append((row, snap, key, decision, actor, final))
        # Complete all validation before any approved answer is changed.
        if not snapshot_path.exists():
            snapshot_path.write_bytes(content)
        applied = []
        for row, snap, key, decision, actor, final in decisions:
            pid = snap["proposal"]["id"]
            reason = row["review_note"] or f"SME {decision} returned change-review row"
            if decision == "approved":
                provenance = json.loads(snap["proposal"]["provenance"])
                provenance["sme_change_review"] = {"review_id": review_id, "source": str(path),
                    "sha256": digest(content), "snapshot": str(snapshot_path), "sme_name": actor,
                    "decision": decision, "review_note": row["review_note"], "reviewed_on": row["reviewed_on"],
                    "imported_at": now(), "original_proposed_answer": snap["proposal"]["answer"], "final_answer": final}
                # The SME reviewed the displayed current revision, including a
                # refreshed packet for a proposal whose original base was older.
                store.db.execute("UPDATE proposals SET answer=?,target=?,base=?,provenance=? WHERE id=?",
                                 (final, snap["review_target"], snap["review_base"], json.dumps(provenance), pid))
                result = store.resolve([pid], actor, reason)[0]
            else:
                store.resolve([pid], actor, reason, approve=False)
                result = {"proposal": pid}
            result["decision"] = decision
            store.db.execute("UPDATE change_review_rows SET applied_fingerprint=?,application=?,applied_at=? WHERE review_id=? AND proposal_id=?",
                             (key, json.dumps(result), now(), review_id, pid))
            store.audit(actor, "change_review_applied", {"review_id": review_id, **result, "review_file_sha256": digest(content)})
            applied.append(result)
    return {"review_id": review_id, "approved": sum(r["decision"] == "approved" for r in applied),
            "rejected": sum(r["decision"] == "rejected" for r in applied), "deferred": deferred,
            "replayed": len(replayed), "changes": applied, "archived_review": str(snapshot_path)}
