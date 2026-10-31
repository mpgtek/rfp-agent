"""Read with openpyxl; write customer files by surgical OOXML ZIP patching."""
from __future__ import annotations

import re
import posixpath
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

Q_HEADERS = {"question", "questions", "control question", "consensus assessment question", "requirement"}
A_HEADERS = {"answer", "response", "responses", "supplier response", "vendor response", "implementation description"}
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def text(value):
    return "" if value is None else str(value).strip()


def literal(cell, value):
    value = text(value)
    if len(value) > 32767 or re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", value):
        raise ValueError("Invalid Excel string (length or control characters)")
    cell.value = value
    cell.data_type = "s"  # Never execute model/source text as an Excel formula.


def layouts(book, *, sheet=None, header_row=None, question_column=None, response_column=None):
    if bool(question_column) != bool(response_column):
        raise ValueError("Specify both question and response columns")
    if sheet and sheet not in book.sheetnames:
        raise ValueError(f"Unknown sheet {sheet}")
    found = []
    for ws in book:
        if sheet and ws.title != sheet:
            continue
        matches = []
        for row in ([header_row] if header_row else range(1, min(ws.max_row, 40) + 1)):
            if question_column:
                qc, ac = (column_index_from_string(x.upper()) for x in (question_column, response_column))
                if not header_row:
                    raise ValueError("Explicit columns require --header-row")
                if qc == ac or not ws.cell(row, qc).value or not ws.cell(row, ac).value:
                    raise ValueError("Distinct columns with existing headers required")
                matches.append((row, qc, ac))
                break
            headers = {c.column: text(c.value).casefold() for c in ws[row]}
            qs = [c for c, h in headers.items() if h in Q_HEADERS]
            answers = [c for c, h in headers.items() if h in A_HEADERS]
            if qs and answers:
                if len(qs) != 1 or len(answers) != 1:
                    raise ValueError(f"Ambiguous columns in {ws.title}; supply explicit mapping")
                matches.append((row, qs[0], answers[0]))
        if len(matches) > 1:
            raise ValueError(f"Multiple header rows in {ws.title}; supply explicit mapping")
        if matches:
            row, qc, ac = matches[0]
            sample = " ".join(text(c.value) for line in ws.iter_rows(min_row=1, max_row=min(ws.max_row, row + 5)) for c in line)
            caiq = "caiq" in (ws.title + " " + sample).casefold() or bool(re.search(r"\b[A-Z]{2,4}-\d{2}(?:\.\d+)?\b", sample))
            found.append({"sheet": ws.title, "header_row": row, "question_column": qc,
                          "response_column": ac, "format": "caiq-like" if caiq else "generic"})
    if not found:
        raise ValueError("No question/response layout found; supply sheet/header/column mapping")
    return found


def extract(path, **mapping):
    if Path(path).suffix.lower() != ".xlsx":
        raise ValueError("Only .xlsx questionnaires supported in this MVP")
    book = load_workbook(path, data_only=False)
    try:
        detected = layouts(book, **mapping)
        rows = []
        for layout in detected:
            ws = book[layout["sheet"]]
            for row in range(layout["header_row"] + 1, ws.max_row + 1):
                q = ws.cell(row, layout["question_column"])
                if not text(q.value):
                    continue
                if q.data_type == "f":
                    raise ValueError(f"Formula question at {ws.title}!{q.coordinate}; use literal questions")
                a = ws.cell(row, layout["response_column"])
                validations = [v for v in ws.data_validations.dataValidation if a.coordinate in v]
                rows.append({"sheet": ws.title, "row": row, "question": text(q.value),
                    "question_cell": q.coordinate, "response_cell": a.coordinate,
                    "existing": text(a.value), "validated": bool(validations),
                    "merged": any(a.coordinate in span for span in ws.merged_cells.ranges),
                    "protected": bool(ws.protection.sheet and a.protection.locked),
                    "format": layout["format"]})
        return detected, rows
    finally:
        book.close()


def patch_copy(source, dest, changes):
    """changes: {sheet_name: {A1: literal_string}}. All other ZIP members copied verbatim."""
    source, dest = Path(source), Path(dest)
    if source.resolve() == dest.resolve() or dest.exists():
        raise ValueError("Output must be a new file, different from source")
    with ZipFile(source) as src:
        wb = ET.fromstring(src.read("xl/workbook.xml"))
        rels = ET.fromstring(src.read("xl/_rels/workbook.xml.rels"))
        targets = {r.attrib["Id"]: r.attrib["Target"] for r in rels}
        paths = {}
        for s in wb.find("m:sheets", NS):
            target = targets[s.attrib['{' + NS['r'] + '}id']]
            paths[s.attrib["name"]] = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
        patched = {}
        for sheet, cells in changes.items():
            xml = src.read(paths[sheet]).decode("utf-8")
            for coord, value in cells.items():
                if not re.fullmatch(r"[A-Z]+[1-9]\d*", coord):
                    raise ValueError("Invalid cell coordinate")
                # Validate before XML serialization, including formula-looking strings.
                literal(Workbook().active.cell(1, 1), value)
                body = '<is><t xml:space="preserve">' + escape(value) + '</t></is>'
                pattern = r'<c\b(?=[^>]*\br="' + coord + r'")([^>]*)(?:/>|>.*?</c>)'
                match = re.search(pattern, xml, re.DOTALL)
                if match:
                    attrs = re.sub(r'\s+t="[^"]*"', '', match.group(1)).rstrip("/")
                    replacement = '<c' + attrs + ' t="inlineStr">' + body + '</c>'
                    xml = xml[:match.start()] + replacement + xml[match.end():]
                else:
                    rownum = int(re.search(r"\d+", coord).group())
                    rowmatch = re.search(r'<row\b(?=[^>]*\br="' + str(rownum) + r'")[^>]*>.*?</row>', xml, re.DOTALL)
                    if not rowmatch:
                        raise ValueError(f"Missing XML row for {coord}")
                    cellxml = '<c r="' + coord + '" t="inlineStr">' + body + '</c>'
                    rowxml = rowmatch.group()
                    col = column_index_from_string(re.match(r"[A-Z]+", coord).group())
                    insert = rowxml.rfind('</row>')
                    for other in re.finditer(r'<c\b[^>]*\br="([A-Z]+)\d+"', rowxml):
                        if column_index_from_string(other.group(1)) > col:
                            insert = other.start()
                            break
                    rowxml = rowxml[:insert] + cellxml + rowxml[insert:]
                    xml = xml[:rowmatch.start()] + rowxml + xml[rowmatch.end():]
            patched[paths[sheet]] = xml.encode("utf-8")
        dest.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(dest, "x") as out:
            for member in src.infolist():
                out.writestr(member, patched.get(member.filename, src.read(member.filename)))


REVIEW_HEADERS = ["draft_id", "question", "draft_answer", "status", "reason", "evidence",
                  "write_state", "action", "corrected_answer", "target_entry", "reviewer", "review_note"]


def review_book(path, drafts):
    """Legacy technical feedback format. Customer runs use sme_review.export_sme_review."""
    book = Workbook()
    ws = book.active
    ws.title = "SME review"
    ws.append(REVIEW_HEADERS)
    for draft in drafts:
        evidence = json_evidence(draft["evidence"])
        values = [draft["id"], draft["question"], draft["answer"], draft["status"], draft["reason"],
                  evidence, draft["write_state"], "", "", "", "", ""]
        ws.append([None] * len(values))
        for c, value in zip(ws[ws.max_row], values):
            literal(c, value)
            c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[ws.max_row].height = 100
    for c in ws[1]:
        c.fill = PatternFill("solid", fgColor="17365D")
        c.font = Font(color="FFFFFF", bold=True)
    for i in range(1, len(REVIEW_HEADERS) + 1):
        ws.column_dimensions[get_column_letter(i)].width = 42 if i in {2, 3, 5, 6, 9, 12} else 22
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = ws.dimensions
    dv = DataValidation(type="list", formula1='"skip,canonical,variant,reject"')
    dv.errorTitle, dv.error, dv.showErrorMessage = "Invalid action", "Choose a listed action", True
    ws.add_data_validation(dv)
    dv.add(f"H2:H{max(2, ws.max_row)}")
    instructions = book.create_sheet("Instructions")
    for line in [
        "Review complete/partial KB-backed responses before customer delivery. Responses with no supported items stay blank.",
        "SME gaps lists only unanswered items. Fill action=propose, sme_answer, reviewer and review_note; preserve the context columns.",
        "Return the workbook via feedback. Gap answers stage individual canonical Q&A proposals; a different authorized approver must approve them.",
        "Coverage shows support and unmet requirements. Supported means evidence exists, not that the vendor meets the requested threshold.",
        "Edit action, corrected_answer, target_entry, reviewer and review_note only.",
        "canonical: propose a new canonical answer or correction. Blank target creates a new question unless exact match exists.",
        "variant: approve equivalence to target_entry from this row's evidence. Leave corrected_answer blank or exactly canonical.",
        "reject: record a rejected draft. No KB mutation. Blank action or skip leaves the row untouched.",
        "feedback stages proposals only. A different actor must approve them via the CLI with a reason.",
        "target_entry must come from this row's evidence. Evidence includes immutable revision and original source location.",
        "Validated, protected, merged and prefilled response cells are preserved. See write_state.",
    ]:
        instructions.append([line])
        instructions.cell(instructions.max_row, 1).alignment = Alignment(wrap_text=True, vertical="top")
        instructions.row_dimensions[instructions.max_row].height = 45
    instructions.column_dimensions["A"].width = 110
    coverage=book.create_sheet("Coverage")
    coverage.append(["Requirement ID","Question","Requested item","Coverage","Meets requirement","Assessment"])
    for d in drafts:
        for item in d.get("requirements",[]):
            meets=item.get("meets_requirement")
            coverage.append([d.get("requirement_id",""),d["question"],item["text"],item["state"],
                             "Unknown" if meets is None else "Yes" if meets else "No",item["note"]])
    from .gap_review import GAP_HEADERS
    gaps=book.create_sheet("SME gaps")
    gaps.append(GAP_HEADERS)
    for d in drafts:
        for gap in d.get("sme_gaps",[]):
            gaps.append([gap.get(h,"") for h in GAP_HEADERS])
    for sheet,widths in [(coverage,[18,65,50,20,23,85]),(gaps,[22,22,18,65,45,65,65,20,65,25,65])]:
        for row in sheet.iter_rows(min_row=2):
            for cell in row:
                literal(cell,cell.value)
                cell.alignment=Alignment(wrap_text=True,vertical="top")
            sheet.row_dimensions[row[0].row].height=100
        for cell in sheet[1]:
            cell.font=Font(bold=True,color="FFFFFF")
            cell.fill=PatternFill("solid",fgColor="17365D")
        for i,width in enumerate(widths,1):
            sheet.column_dimensions[get_column_letter(i)].width=width
        sheet.freeze_panes="D2"
        sheet.auto_filter.ref=sheet.dimensions
    gap_action=DataValidation(type="list",formula1='"skip,propose"')
    gaps.add_data_validation(gap_action)
    gap_action.add(f"H2:H{max(2,gaps.max_row)}")
    composed=[d for d in drafts if d.get("composition")]
    if composed:
        claims=book.create_sheet("Claim evidence")
        claims.append(["Requirement ID","Question","Customer claim","KB entry / revision","Source excerpts","Support assessment"])
        for d in composed:
            composition=d["composition"]
            for claim in composition["claims"]:
                parts=[composition["parts"][i] for i in claim["part_indices"]]
                values=[d.get("requirement_id",""),d["question"],claim["text"],
                        ", ".join(f'{p["entry_id"]} / {p["revision"]}' for p in parts),
                        "\n\n".join(p["quote"] for p in parts),claim["support_note"]]
                claims.append([None]*len(values))
                for cell,value in zip(claims[claims.max_row],values):
                    literal(cell,value)
                    cell.alignment=Alignment(wrap_text=True,vertical="top")
                claims.row_dimensions[claims.max_row].height=180
        for cell in claims[1]:
            cell.font=Font(bold=True,color="FFFFFF")
            cell.fill=PatternFill("solid",fgColor="17365D")
        for column,width in zip("ABCDEF",[18,66,70,26,92,75]):
            claims.column_dimensions[column].width=width
        claims.freeze_panes="C2"
        claims.auto_filter.ref=claims.dimensions
    if any(d.get("format")=="docx-table" for d in drafts):
        locations=book.create_sheet("Response locations")
        locations.append(["Requirement ID","Question","Table","Row","Response cell","Write state"])
        for d in drafts:
            locations.append([d.get("requirement_id",""),d["question"],d["sheet"],str(d["row"]),d["response_cell"],d["write_state"]])
        for cell in locations[1]:
            cell.font=Font(bold=True,color="FFFFFF")
            cell.fill=PatternFill("solid",fgColor="17365D")
        for row in locations.iter_rows(min_row=2):
            for cell in row:
                literal(cell,cell.value)
                cell.alignment=Alignment(wrap_text=True,vertical="top")
        for column,width in zip("ABCDEF",[18,76,18,12,24,45]):
            locations.column_dimensions[column].width=width
        locations.freeze_panes="C2"
        locations.auto_filter.ref=locations.dimensions
    book.save(path)
    book.close()


def json_evidence(items):
    import json
    return json.dumps([{k: e[k] for k in ("id", "revision", "question", "answer", "provenance", "approved_at")}
                       for e in items], ensure_ascii=False)
