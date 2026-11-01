"""Editable, item-specific SME requests; returned answers stage proposals only."""
import json
from .db import digest
from .excel import text

GAP_HEADERS=["gap_id","draft_id","requirement_id","original_question","missing_item",
             "sme_question","current_response","action","sme_answer","reviewer","review_note"]


def make_gaps(draft):
    return [{"gap_id":digest((draft["id"]+":"+item["id"]).encode()),"draft_id":draft["id"],
             "requirement_id":draft.get("requirement_id",""),"original_question":draft["question"],
             "missing_item":item["text"],"sme_question":item["sme_question"],"current_response":draft["answer"]}
            for item in draft.get("requirements",[]) if item["state"]=="missing"]


def ingest_gaps(store,book,path,content):
    if "SME gaps" not in book.sheetnames:
        return []  # Backward-compatible reviews.
    ws=book["SME gaps"]
    if [c.value for c in ws[1]]!=GAP_HEADERS:
        raise ValueError("SME gap headers were changed")
    staged=[]
    seen=set()
    for cells in ws.iter_rows(min_row=2):
        values={h:text(c.value) for h,c in zip(GAP_HEADERS,cells)}
        action=values["action"].casefold()
        if not action or action=="skip":
            continue
        if action!="propose" or any(c.data_type=="f" for c in cells):
            raise ValueError("SME gap requires a literal propose action")
        if values["gap_id"] in seen:
            raise ValueError("Duplicate SME gap ID")
        seen.add(values["gap_id"])
        row=store.db.execute("SELECT payload FROM drafts WHERE id=?",(values["draft_id"],)).fetchone()
        if not row:
            raise ValueError("Unknown SME gap draft")
        original=json.loads(row[0])
        gap=next((g for g in make_gaps(original) if g["gap_id"]==values["gap_id"]),None)
        if gap is None or any(values[h]!=gap[h] for h in GAP_HEADERS[:7]):
            raise ValueError("SME gap context was changed; edit sme_answer only")
        if not all(values[h] for h in ("sme_answer","reviewer","review_note")):
            raise ValueError("SME gap needs an answer, named reviewer and review note")
        fingerprint=digest(json.dumps(["sme-gap",gap["gap_id"],values["sme_answer"],values["reviewer"],values["review_note"]]).encode())
        replay=store.db.execute("SELECT id FROM proposals WHERE fingerprint=?",(fingerprint,)).fetchone()
        if replay:
            staged.append(replay[0]);continue
        for evidence in original["evidence"]:
            current=store.evidence(evidence["id"])
            if not current or current["revision"]!=evidence["revision"]:
                raise ValueError("SME gap evidence is stale; generate a fresh review")
        staged.append(store.stage(question=gap["sme_question"],answer=values["sme_answer"],scope=original["scope"],
            provenance={"source":str(path),"sha256":digest(content),"gap_id":gap["gap_id"],
                        "draft_id":original["id"],"run_id":original["run_id"],
                        "original_question":original["question"],"review_note":values["review_note"],
                        "evidence":original["evidence"]},submitter=values["reviewer"],fingerprint=fingerprint))
    return staged
