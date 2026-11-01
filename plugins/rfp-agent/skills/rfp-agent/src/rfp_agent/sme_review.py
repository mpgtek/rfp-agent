"""Plain-language SME forms, with server-side context and explicit decisions."""
import json
import textwrap
import uuid
from pathlib import Path
from openpyxl import Workbook,load_workbook
from openpyxl.styles import Alignment,Font,PatternFill,Protection
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import CellIsRule
from .db import digest,norm,now
from .excel import literal,text
from .gap_review import make_gaps

FORMAT="rfp-agent.sme-review.v1"
HEADERS=["Requirement ID","Original Requirement","Current Response","Information Needed",
         "SME Response","Review Status","Reviewed By","Comments"]
KEY_HEADER="Review reference"
WIDTHS=[16,47,47,44,47,24,25,38]
LEGEND=[
    ("How to complete this review","Each row asks for one missing item. Existing supported answers appear in Current Response. Edit the green cells only."),
    ("1. Answer","Enter only the answer to Information Needed in SME Response. Use confirmed company facts; leave unknown answers Pending."),
    ("2. Approve","Choose Approved and enter your name in Reviewed By when the answer is ready to use. Comments are optional."),
    ("3. Return","Save this Excel workbook, upload it to the skill, and ask it to apply the SME review. Keep the original workbook format."),
    ("What happens next","Approved new answers are added to the KB with your name and source history. Different existing answers go to comparison review. Pending rows remain open. Regenerate the RFP after application."),
    ("Requirement ID","The identifier supplied by the customer. It may be blank when the original questionnaire has no identifier. Read-only."),
    ("Original Requirement","The customer's full question, included for context. Read-only."),
    ("Current Response","The supported response already drafted or retained in the RFP. Blank means no answer is established. Read-only."),
    ("Information Needed","The specific remaining item and question for the SME. Supply only this missing information. Read-only."),
    ("SME Response","Your confirmed answer to the missing item, written in customer-facing language. Required for Approved."),
    ("Review Status","Pending: no KB change. Approved: the named SME approves this answer. Not Applicable: explain why this item does not apply; it is recorded for this review and does not become a KB answer or a No."),
    ("Reviewed By","Your name, recorded in the review history. Required for Approved and Not Applicable."),
    ("Comments","Optional explanation or evidence reference. Required for Not Applicable."),
    ("Supporting Evidence","Optional reading: drafted answers, known shortfalls, missing items, KB excerpts and original source references. Supported facts do not automatically meet every requested target."),
    ("Editing","Gray cells are for reference. Edit only the green cells. Use the column filters to find Pending items. Keep the column names and original context unchanged."),
    ("If information has changed","If the skill reports an outdated review, request a fresh workbook. Reuploading the same file does not duplicate answers. Do not mix rows from different workbooks."),
]


def target_for(store,question,scope):
    row=store.db.execute("""SELECT e.id FROM entries e LEFT JOIN variants v ON
        v.entry_id=e.id AND v.revision_id=e.head AND v.scope=e.scope
        WHERE e.scope=? AND (e.normalized=? OR v.normalized=?) LIMIT 1""",
        (scope,norm(question),norm(question))).fetchone()
    return store.evidence(row[0]) if row else None


def style_sheet(ws,widths,editable=()):
    for index,width in enumerate(widths,1):
        from openpyxl.utils import get_column_letter
        ws.column_dimensions[get_column_letter(index)].width=width
    for row in ws:
        height=28 if row[0].row==1 else 54
        for index,cell in enumerate(row,1):
            if index>len(widths):continue
            literal(cell,cell.value)
            cell.alignment=Alignment(wrap_text=True,vertical="top")
            cell.font=Font(name="Calibri",size=11,color="17324D")
            if cell.row==1:
                cell.font=Font(name="Calibri",size=11,bold=True,color="FFFFFF")
                cell.fill=PatternFill("solid",fgColor="17365D")
            else:
                cell.protection=Protection(locked=index not in editable)
                cell.fill=PatternFill("solid",fgColor="EAF5EE" if index in editable else "F3F5F7")
                lines=sum(max(1,len(textwrap.wrap(s,width=max(12,int(widths[index-1]*0.8))))) for s in text(cell.value).split('\n'))
                height=max(height,lines*15+12)
        ws.row_dimensions[row[0].row].height=min(409,height)
    ws.sheet_view.showGridLines=False
    ws.sheet_view.zoomScale=85
    ws.freeze_panes="A2"
    ws.protection.sheet=True
    ws.protection.autoFilter=False
    ws.protection.sort=False
    ws.protection.selectLockedCells=False
    ws.protection.selectUnlockedCells=False
    ws.auto_filter.ref=ws.dimensions


def export_sme_review(store,path,drafts):
    path=Path(path)
    if path.exists():
        raise ValueError("Review output must be a new file; preserve the original review")
    packet=uuid.uuid4().hex
    book=Workbook();review=book.active;review.title="SME Review"
    review.append(HEADERS+[KEY_HEADER])
    snapshots=[]
    for draft in drafts:
        for gap in make_gaps(draft):
            row_id=uuid.uuid4().hex
            needed=gap["sme_question"]
            public=[gap["requirement_id"],gap["original_question"],draft.get("existing") or gap["current_response"],needed]
            review.append(public+["","Pending","", "",row_id])
            target=target_for(store,gap["sme_question"],draft["scope"])
            snapshots.append((row_id,{"context":public,"gap":gap,"scope":draft["scope"],
                "evidence":draft["evidence"],"target":target["id"] if target else None,
                "base":target["revision"] if target else None}))
    style_sheet(review,WIDTHS,editable=(5,6,7,8))
    review.freeze_panes="E2"
    review.column_dimensions["I"].hidden=True
    review.column_dimensions["I"].width=2
    status=DataValidation(type="list",formula1='"Pending,Approved,Not Applicable"')
    status.errorTitle="Choose a review status";status.error="Choose Pending, Approved or Not Applicable."
    status.showErrorMessage=True;status.errorStyle="stop"
    review.add_data_validation(status);status.add(f"F2:F{max(2,review.max_row)}")
    for label,color in [("Approved","DDF0DF"),("Pending","FFF2CC"),("Not Applicable","E7E6E6")]:
        review.conditional_formatting.add(f"F2:F{max(2,review.max_row)}",CellIsRule(operator="equal",formula=['"'+label+'"'],fill=PatternFill("solid",fgColor=color)))
    instructions=book.create_sheet("Instructions")
    instructions.append(["Topic or Column","What It Means / What To Do"])
    for row in LEGEND:instructions.append(row)
    instructions.append(["Items awaiting review",str(len(snapshots)) if snapshots else "No missing items. Review the drafted answers in Supporting Evidence before delivery."])
    style_sheet(instructions,[31,115])
    evidence=book.create_sheet("Supporting Evidence")
    evidence.append(["Requirement ID","Original Requirement","Current Response","Review Notes","Supporting Excerpt","Original Source"])
    for draft in drafts:
        notes=[]
        for item in draft.get("requirements",[]):
            label="Information needed" if item["state"]=="missing" else "Known shortfall" if item.get("meets_requirement") is False else "Known"
            note=item["note"].replace("The current scoped KB does not establish this requested item.","No answer is recorded for this item.")
            note=note.replace("Explicitly established by the cited current answer text.","Supported by an existing KB answer.")
            notes.append(label+": "+item["text"]+". "+note)
        if draft.get("existing"):notes.insert(0,"The existing customer response was retained.")
        parts=(draft.get("composition") or {}).get("parts",[])
        if not parts and draft["answer"]:
            parts=[{"entry_id":e["id"],"quote":e["answer"]} for e in draft["evidence"] if e.get("exact")]
        quotes=[];sources=[]
        for part in parts:
            if part["quote"] not in quotes:quotes.append(part["quote"])
            entry=next((e for e in draft["evidence"] if e["id"]==part["entry_id"]),None)
            if entry:
                p=json.loads(entry["provenance"])
                name=str(p.get("source",""))
                if name and not name.startswith(("https://","http://")):name=Path(name).name
                location=str(p.get("location",""))
                location=location.replace("paragraph:","paragraph ").replace("/answer:","; answer paragraphs ")
                source=" — ".join(s for s in (name,location) if s)
                if source and source not in sources:sources.append(source)
        evidence.append([draft.get("requirement_id",""),draft["question"],draft.get("existing") or draft["answer"],
                         '\n'.join(notes) or draft["reason"],'\n\n'.join(quotes),'\n'.join(sources)])
    style_sheet(evidence,[16,48,48,70,90,70])
    meta=book.create_sheet("_Review data");meta.append(["Format",FORMAT]);meta.append(["Review",packet]);meta.sheet_state="veryHidden"
    with store.transaction():
        store.db.execute("INSERT INTO sme_review_packets VALUES(?,?,?)",(packet,now(),str(path)))
        for row_id,payload in snapshots:
            store.db.execute("INSERT INTO sme_review_items(packet_id,row_id,payload) VALUES(?,?,?)",(packet,row_id,json.dumps(payload)))
        path.parent.mkdir(parents=True,exist_ok=True)
        book.save(path)
        store.audit("rfp-agent","sme_review_exported",{"review":packet,"items":len(snapshots)})
    book.close()
    return {"review_id":packet,"items":len(snapshots),"path":str(path)}


def looks_like_sme_review(path):
    path=Path(path)
    if path.suffix.lower()!=".xlsx":return False
    book=load_workbook(path,read_only=True,data_only=False)
    try:return "_Review data" in book.sheetnames and book["_Review data"]["B1"].value==FORMAT
    finally:book.close()


def apply_sme_review(store,path):
    path=Path(path).resolve();content=path.read_bytes()
    book=load_workbook(path,data_only=False)
    try:
        if "_Review data" not in book.sheetnames or book["_Review data"]["B1"].value!=FORMAT:
            raise ValueError("Not a recognized SME review workbook")
        packet=text(book["_Review data"]["B2"].value)
        if not store.db.execute("SELECT 1 FROM sme_review_packets WHERE id=?",(packet,)).fetchone():
            raise ValueError("Unknown review: use its original company workspace")
        ws=book["SME Review"]
        if [c.value for c in ws[1]]!=HEADERS+[KEY_HEADER]:
            raise ValueError("Review columns were changed; use the original workbook")
        decisions=[];seen=set();answers={};pending=0;replayed=[]
        with store.transaction():
            for cells in ws.iter_rows(min_row=2,max_col=9):
                values=[text(c.value) for c in cells]
                if not any(values):continue
                if any(c.data_type=="f" for c in cells):raise ValueError("Review cells must contain literal text, not formulas")
                row_id=values[8]
                if row_id in seen:raise ValueError("Duplicate review row")
                seen.add(row_id)
                saved=store.db.execute("SELECT * FROM sme_review_items WHERE packet_id=? AND row_id=?",(packet,row_id)).fetchone()
                if not saved:raise ValueError("Unknown review row; do not mix workbooks")
                original=json.loads(saved["payload"])
                if values[:4]!=original["context"]:raise ValueError("Read-only review context was changed")
                answer,status,actor,comments=values[4:8]
                status=status.casefold() or "pending"
                if status not in {"pending","approved","not applicable"}:raise ValueError("Choose Pending, Approved or Not Applicable")
                if status=="pending":
                    if saved["decision_fingerprint"]:raise ValueError("An applied decision cannot be changed to Pending; request a new review")
                    pending+=1;continue
                if not actor:raise ValueError("Reviewed By is required for Approved or Not Applicable")
                if status=="approved" and not answer:raise ValueError("Approved rows require an SME Response")
                if status=="not applicable" and not comments:raise ValueError("Not Applicable requires an explanation in Comments")
                fingerprint=digest(json.dumps([packet,row_id,answer,status,actor,comments],ensure_ascii=False).encode())
                if saved["decision_fingerprint"]:
                    if saved["decision_fingerprint"]!=fingerprint:raise ValueError("This decision was already applied differently; request a new review")
                    replayed.append(json.loads(saved["application"]));continue
                for evidence in original["evidence"]:
                    current=store.evidence(evidence["id"])
                    if not current or current["revision"]!=evidence["revision"]:raise ValueError("Review evidence is stale; request a fresh workbook")
                current=target_for(store,original["gap"]["sme_question"],original["scope"])
                if (current["id"] if current else None)!=original["target"] or (current["revision"] if current else None)!=original["base"]:
                    raise ValueError("The KB answer changed since review export; request a fresh workbook")
                if status=="approved":
                    identity=(original["scope"],norm(original["gap"]["sme_question"]))
                    if identity in answers and answers[identity]!=answer:raise ValueError("Approved rows give different answers to the same question")
                    answers[identity]=answer
                decisions.append((row_id,original,answer,status,actor,comments,fingerprint))
            archived=store.root/"sources"/(digest(content)+".xlsx")
            if not archived.exists():archived.write_bytes(content)
            applied=[];conflicts=[]
            for row_id,original,answer,status,actor,comments,fingerprint in decisions:
                result={"review_row":row_id,"decision":status}
                if status=="not applicable":result["outcome"]="not-applicable"
                else:
                    question=original["gap"]["sme_question"];scope=original["scope"]
                    target=target_for(store,question,scope)
                    provenance={"source":str(path),"snapshot":str(archived),"sha256":digest(content),
                        "sme_review":{"review_id":packet,"row":row_id,"decision":"Approved","reviewed_by":actor,
                                      "comments":comments,"gap":original["gap"],"imported_at":now()},"evidence":original["evidence"]}
                    if target and target["answer"]==answer:
                        result.update(outcome="unchanged",entry=target["id"],revision=target["revision"])
                    else:
                        pid=store.stage(question=question,answer=answer,scope=scope,provenance=provenance,submitter=actor,
                            target=target["id"] if target else None,fingerprint=fingerprint,deduplicate=True)
                        if target:
                            result.update(outcome="needs-comparison",proposal=pid);conflicts.append(pid)
                        else:
                            result.update(store.resolve([pid],actor,comments or "Explicit Approved SME review",approved_sme_import=True)[0],outcome="added")
                store.db.execute("UPDATE sme_review_items SET decision_fingerprint=?,application=? WHERE packet_id=? AND row_id=?",
                                 (fingerprint,json.dumps(result),packet,row_id))
                store.audit(actor,"sme_review_applied",{"review":packet,**result,"file_sha256":digest(content)})
                applied.append(result)
            from .change_review import export_changes
            comparison=export_changes(store,list(set(conflicts))) if conflicts else None
            for result in applied:
                if result["outcome"]=="needs-comparison":
                    result["comparison_review"]=comparison
                    store.db.execute("UPDATE sme_review_items SET application=? WHERE packet_id=? AND row_id=?",
                                     (json.dumps(result),packet,result["review_row"]))
            pending_conflicts=list(conflicts)
            for result in replayed:
                if result["outcome"]=="needs-comparison":
                    proposal=store.db.execute("SELECT status FROM proposals WHERE id=?",(result["proposal"],)).fetchone()
                    if proposal and proposal["status"]=="pending":
                        pending_conflicts.append(result["proposal"])
                        if comparison is None:comparison=result.get("comparison_review")
        return {"review_id":packet,"approved":sum(r["decision"]=="approved" for r in applied),
                "added":sum(r["outcome"]=="added" for r in applied),"unchanged":sum(r["outcome"]=="unchanged" for r in applied),
                "needs_comparison":len(set(pending_conflicts)),"not_applicable":sum(r["outcome"]=="not-applicable" for r in applied),
                "pending":pending,"replayed":len(replayed),"comparison_review":comparison,"results":applied,
                "archived_review":str(archived)}
    finally:book.close()
