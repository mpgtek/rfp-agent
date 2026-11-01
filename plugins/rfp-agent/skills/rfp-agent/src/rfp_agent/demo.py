"""Reproducible fictional corpus and a real end-to-end approval/learning exercise."""
import json
from pathlib import Path
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from .adapters import ingest
from .db import Store
from .excel import REVIEW_HEADERS, literal
from .workflow import answer_rfp, ingest_feedback
from .corpus import GROUPS, LEARNED_ANSWER, REFERENCE_URLS, knowledge_records, rfp_cases


def fixtures(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    records, cases = knowledge_records(), rfp_cases()
    sources = directory / "scenario-documents"
    sources.mkdir(exist_ok=True)
    for category, owner, _ in GROUPS:
        selected = [r for r in records if r["category"] == category]
        lines = ["# " + selected[0]["evidence_document"], "",
                 "SIMULATED INTERNAL EVIDENCE. All facts describe an invented company and have no external attestation.",
                 "", "Product: MeridianDesk Enterprise SaaS", "", "Owner: " + owner,
                 "", "Version: 2026.10-demo", "", "Reviewed: 2026-10-29", ""]
        for r in selected:
            lines.extend(["## " + r["evidence_section"] + " — " + r["question"], "", r["answer"], ""])
        (sources / ("MD-" + str(records.index(selected[0]) // 5 + 1).zfill(2) + ".md")).write_text("\n".join(lines))
    (directory / "scenario.json").write_text(json.dumps({"product": "MeridianDesk", "synthetic": True,
        "version": "realistic-v2", "coverage_references": REFERENCE_URLS, "records": records}, indent=2))
    (directory / "rfp-gold.json").write_text(json.dumps(cases, indent=2))
    kb = Workbook()
    ws = kb.active
    ws.title = "MeridianDesk demo KB"
    ws.append(["Question", "Answer", "Category", "Owner", "Capability", "Evidence document",
               "Evidence section", "Document version", "Reviewed on", "Evidence kind"])
    for r in records:
        ws.append([r[k] for k in ("question", "answer", "category", "owner", "capability", "evidence_document",
                                  "evidence_section", "document_version", "reviewed_on")] + ["SIMULATED INTERNAL EVIDENCE"])
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions
    for col, width in {"A": 65, "B": 110, "C": 28, "D": 30, "E": 24, "F": 60, "G": 20, "H": 24, "I": 20, "J": 35}.items():
        ws.column_dimensions[col].width = width
    from openpyxl.styles import Alignment
    for row in ws.iter_rows(min_row=2):
        ws.row_dimensions[row[0].row].height = 105
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for cell in ws[1]:
        cell.fill = PatternFill("solid", fgColor="17365D")
        cell.font = Font(color="FFFFFF", bold=True)
    note = kb.create_sheet("Scenario and sources")
    for line in ["Fictional MeridianDesk case-management SaaS. All company answers and evidence documents are authored synthetic data.",
                 "100 distinct requirements across 20 domains; no numbered service clones.",
                 "Public resources guide question coverage only. No vendor's controls or attestations have been imported as company facts.",
                 *REFERENCE_URLS,
                 "Simulated internal evidence documents are in scenario-documents/ beside this workbook."]:
        note.append([line])
        note.cell(note.max_row, 1).alignment = Alignment(wrap_text=True, vertical="top")
        note.row_dimensions[note.max_row].height = 45
    note.column_dimensions["A"].width = 110
    kb.save(directory / "knowledge.xlsx")
    kb.close()
    rfp = Workbook()
    ws = rfp.active
    ws.title = "CAIQ demo"
    ws.append(["SYNTHETIC CAIQ-like fixture; not an official CSA questionnaire"])
    ws.append(["Control ID", "Question", "Supplier Response", "Reviewer notes", "Count"])
    rfp_questions = [c["question"] for c in cases]
    for n, q in enumerate(rfp_questions, 1):
        ws.append([f"AIS-{n:02}.1", q, None, "Template note", n])
        ws.cell(n + 2, 3).fill = PatternFill("solid", fgColor="FFF2CC")
        ws.cell(n + 2, 2).font = Font(name="Calibri", size=11)
        ws.row_dimensions[n + 2].height = 32
    ws.freeze_panes = "C3"
    ws.column_dimensions["B"].width = 70
    ws.column_dimensions["C"].width = 90
    ws.auto_filter.ref = "A2:E32"
    extra = rfp.create_sheet("Template calculations")
    extra.append(["Metric", "Value"])
    extra.append(["Questions", "=COUNTA('CAIQ demo'!B3:B32)"])
    extra.append(["Expected", 30])
    extra.append(["Other", 4])
    extra.merge_cells("D1:E1")
    extra["D1"] = "Keep this merged title"
    chart = BarChart()
    chart.add_data(Reference(extra, min_col=2, min_row=3, max_row=4))
    extra.add_chart(chart, "G2")
    dv = DataValidation(type="list", formula1='"Yes,No,NA"')
    extra.add_data_validation(dv)
    dv.add("D3")
    rfp.save(directory / "rfp.xlsx")
    rfp.close()
    (directory / "explicit.md").write_text("Q: What is the fictional support window?\nA: Synthetic support runs Monday to Friday.\n")
    (directory / "explicit.txt").write_text("Q: Where is the fictional help desk?\nA: The fictional help desk is online.\n")
    (directory / "explicit.csv").write_text("Question,Answer\nWhat is the fictional region?,Synthetic region alpha\n")
    for provider in ("confluence", "notion"):
        (directory / f"{provider}.json").write_text(json.dumps({"provider": provider, "records": [{
            "question": f"What is the fictional {provider} process?", "answer": "An explicitly reviewed fictional process.",
            "page_id": "demo-1", "url": f"https://example.invalid/{provider}/demo-1", "version": "1"}]}))
    from docx import Document
    doc = Document()
    table = doc.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text, table.rows[0].cells[1].text = "Question", "Answer"
    cells = table.add_row().cells
    cells[0].text, cells[1].text = "Who owns fictional operations?", "The synthetic operations team."
    doc.save(directory / "explicit.docx")
    return directory


def run_demo(workspace):
    store = Store(workspace)
    try:
        if store.db.execute("SELECT 1 FROM proposals LIMIT 1").fetchone():
            raise ValueError("Demo requires a fresh workspace")
        inputs = fixtures(store.root / "demo-inputs")
        ids = ingest(store, inputs / "knowledge.xlsx", "synthetic-saas")
        store.resolve(ids, "demo-approver", "Synthetic source accepted for demonstration")
        first = answer_rfp(store, inputs / "rfp.xlsx", "synthetic-saas",known_only=False)
        feedback = Path(first["output"]) / "sme-feedback.xlsx"
        book = load_workbook(Path(first["output"]) / "sme-review.xlsx")
        ws = book["SME review"]
        for n in (14, 26):  # RFP case 13: audit export paraphrase; case 25: VPAT gap
            vals = {h: ws.cell(n, i + 1).value for i, h in enumerate(REVIEW_HEADERS)}
            evidence = json.loads(vals["evidence"])
            action = "variant" if n == 14 else "canonical"
            updates = {"action": action, "reviewer": "demo-sme", "review_note": "Explicit synthetic SME review"}
            if action == "variant":
                expected = 54
                if expected not in {e["id"] for e in evidence}:
                    raise AssertionError("Audit-export retrieval missed its labeled canonical evidence")
                updates["target_entry"] = expected
            else:
                updates["corrected_answer"] = LEARNED_ANSWER
            for key, value in updates.items():
                literal(ws.cell(n, REVIEW_HEADERS.index(key) + 1), value)
        book.save(feedback)
        book.close()
        proposed = ingest_feedback(store, feedback)
        # Proposals alone must not alter approved answers.
        pending = answer_rfp(store, inputs / "rfp.xlsx", "synthetic-saas",known_only=False)
        store.resolve(proposed, "demo-approver", "Reviewed SME equivalence and new canonical knowledge")
        second = answer_rfp(store, inputs / "rfp.xlsx", "synthetic-saas",known_only=False)
        with ZipFile(inputs / "rfp.xlsx") as original, ZipFile(Path(first["output"]) / "completed.xlsx") as completed:
            unchanged = [name for name in original.namelist() if original.read(name) == completed.read(name)]
            changed = [name for name in original.namelist() if name not in unchanged]
        first_drafts = json.loads((Path(first["output"]) / "drafts.json").read_text())
        second_drafts = json.loads((Path(second["output"]) / "drafts.json").read_text())
        gold = rfp_cases()
        labeled = [dict(case, observed_status=d["status"],
            retrieved_entry_ids=[e["id"] for e in d["evidence"]],
            expected_evidence_retrieved=bool(set(case["expected_evidence"]) & {e["id"] for e in d["evidence"]}))
            for case, d in zip(gold, first_drafts)]
        unsafe = [c["case_id"] for c in labeled if c["kind"] not in {"exact"} and c["observed_status"] == "high-confidence"]
        known = [c for c in labeled if c["expected_evidence"]]
        result = {"scenario_version": "realistic-v2", "product": "MeridianDesk (fictional)",
            "coverage_domains": len(GROUPS), "knowledge_records": len(ids), "rfp_questions": 30, "first": first,
            "pending_feedback": pending, "second": second, "feedback_proposals": proposed,
            "workbook_parts_changed": changed, "workbook_parts_preserved": len(unchanged),
            "high_confidence_improvement": second["counts"].get("high-confidence", 0) - first["counts"].get("high-confidence", 0),
            "retrieval_benchmark": {"labeled_questions_with_evidence": len(known),
                "expected_evidence_in_top5": sum(c["expected_evidence_retrieved"] for c in known),
                "incorrect_high_confidence_case_ids": unsafe}, "cases": labeled}
        if (unsafe or result["high_confidence_improvement"] != 1 or pending["counts"] != first["counts"]
                or second_drafts[12]["status"] != "high-confidence"
                or second_drafts[24]["answer"] != LEARNED_ANSWER or second_drafts[24]["status"] != "needs-review"):
            raise AssertionError("Learning/approval demonstration did not meet expected outcome")
        (store.root / "demo-result.json").write_text(json.dumps(result, indent=2))
        return result
    finally:
        store.close()
