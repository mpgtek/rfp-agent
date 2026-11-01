"""Detect Word questionnaire tables and patch only empty response cells."""
from copy import deepcopy
from pathlib import Path
from zipfile import ZipFile

from lxml import etree as ET
from openpyxl.utils import column_index_from_string

from .excel import A_HEADERS, Q_HEADERS

NS = {"w":"http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
W = "{" + NS["w"] + "}"


def parse(data):
    return ET.fromstring(data, ET.XMLParser(resolve_entities=False, no_network=True))


def cell_text(cell):
    paragraphs=[]
    for p in cell.findall("w:p",NS):
        paragraphs.append("".join("\n" if e.tag==W+"br" else "\t" if e.tag==W+"tab" else e.text or ""
                                  for e in p.iter() if e.tag in {W+"t",W+"br",W+"tab"}))
    return "\n".join(paragraphs).strip()


def coordinate(table,row,column):
    return f"T{table}:R{row}:C{column}"


def extract(path, *, sheet=None, header_row=None, question_column=None, response_column=None):
    if bool(question_column)!=bool(response_column):
        raise ValueError("Specify both question and response columns")
    layouts,records=[],[]
    with ZipFile(path) as archive:
        if any(name.startswith("_xmlsignatures/") for name in archive.namelist()):
            raise ValueError("Signed Word packages are not supported; use an unsigned questionnaire copy")
        root=parse(archive.read("word/document.xml"))
        protected=False
        if "word/settings.xml" in archive.namelist():
            protection=parse(archive.read("word/settings.xml")).find("w:documentProtection",NS)
            protected=protection is not None and protection.get(W+"enforcement","").lower() in {"1","true","on"}
        tables=root.findall("w:body/w:tbl",NS)
        if sheet and sheet not in {f"Table {n}" for n in range(1,len(tables)+1)}:
            raise ValueError("DOCX --sheet must identify an existing table, e.g. 'Table 4'")
        for ti,table in enumerate(tables,1):
            label=f"Table {ti}"
            if sheet and sheet!=label:
                continue
            rows=table.findall("w:tr",NS)
            candidates=[]
            indices=[header_row] if header_row else range(1,min(40,len(rows))+1)
            for ri in indices:
                if ri<1 or ri>len(rows):
                    raise ValueError("Invalid Word table header row")
                cells=rows[ri-1].findall("w:tc",NS)
                headers=[cell_text(c).casefold() for c in cells]
                if question_column:
                    if not header_row:
                        raise ValueError("Explicit columns require --header-row")
                    qc,ac=[column_index_from_string(v.upper())-1 for v in (question_column,response_column)]
                    if qc==ac or max(qc,ac)>=len(cells):
                        raise ValueError("Distinct existing Word table columns required")
                    candidates.append((ri,qc,ac,len(cells)))
                    break
                qs=[i for i,h in enumerate(headers) if h in Q_HEADERS]
                answers=[i for i,h in enumerate(headers) if h in A_HEADERS]
                if qs and answers:
                    if len(qs)!=1 or len(answers)!=1:
                        raise ValueError(f"Ambiguous Word columns in {label}; supply explicit mapping")
                    candidates.append((ri,qs[0],answers[0],len(cells)))
            if len(candidates)>1:
                raise ValueError(f"Multiple Word header rows in {label}; supply explicit mapping")
            if not candidates:
                continue
            header,qc,ac,width=candidates[0]
            id_columns=[i for i,c in enumerate(rows[header-1].findall("w:tc",NS)) if cell_text(c).casefold() in {"id","control id","requirement id"}]
            layouts.append({"sheet":label,"table":ti,"header_row":header,"question_column":qc+1,
                            "response_column":ac+1,"format":"docx-table"})
            for ri,row in enumerate(rows[header:],header+1):
                cells=row.findall("w:tc",NS)
                if max(qc,ac)>=len(cells):
                    continue
                q,a=cells[qc],cells[ac]
                question=cell_text(q)
                if not question:
                    continue
                spans=q.findall("w:tcPr/w:gridSpan",NS)+a.findall("w:tcPr/w:gridSpan",NS)
                merged=(len(cells)!=width or any(int(s.get(W+"val","1"))!=1 for s in spans)
                        or q.find("w:tcPr/w:vMerge",NS) is not None or a.find("w:tcPr/w:vMerge",NS) is not None
                        or row.find("w:trPr/w:gridBefore",NS) is not None)
                complex_cell=any(a.find(".//w:"+tag,NS) is not None for tag in
                                 ("sdt","fldChar","instrText","drawing","object","tbl","ins","del","hyperlink"))
                records.append({"sheet":label,"table":ti,"row":ri,"column":ac+1,"question":question,
                    "question_cell":coordinate(ti,ri,qc+1),"response_cell":coordinate(ti,ri,ac+1),
                    "requirement_id":cell_text(cells[id_columns[0]]) if len(id_columns)==1 and id_columns[0]<len(cells) else "",
                    "existing":cell_text(a),"merged":merged,"protected":protected,
                    "validated":complex_cell,"format":"docx-table"})
    if not layouts:
        raise ValueError("No Word question/response table found; paragraph-only questionnaires require an explicit response layout")
    return layouts,records


def patch_copy(source,dest,changes,*,mapping=None):
    source,dest=Path(source),Path(dest)
    if source.resolve()==dest.resolve() or dest.exists():
        raise ValueError("Output must be a new file, different from source")
    # Re-detect writable cells; callers cannot use arbitrary coordinates to
    # replace nonempty, protected, merged or complex content.
    allowed={r["response_cell"]:r for r in extract(source,**(mapping or {}))[1] if not any(
        r[k] for k in ("existing","merged","protected","validated"))}
    with ZipFile(source) as original:
        root=parse(original.read("word/document.xml"))
        tables=root.findall("w:body/w:tbl",NS)
        changed=False
        for sheet,cells in changes.items():
            for coord,value in cells.items():
                row=allowed.get(coord)
                if row is None or row["sheet"]!=sheet:
                    raise ValueError("Word response cell is not writable")
                if not isinstance(value,str) or not value.strip():
                    raise ValueError("Word responses must be nonempty literal text")
                cell=tables[row["table"]-1].findall("w:tr",NS)[row["row"]-1].findall("w:tc",NS)[row["column"]-1]
                p=cell.find("w:p",NS)
                if p is None:
                    p=ET.SubElement(cell,W+"p")
                run=ET.SubElement(p,W+"r")
                old_style=p.find("w:r/w:rPr",NS)
                if old_style is not None:
                    run.append(deepcopy(old_style))
                for i,line in enumerate(value.split("\n")):
                    if i:
                        ET.SubElement(run,W+"br")
                    t=ET.SubElement(run,W+"t")
                    t.set("{http://www.w3.org/XML/1998/namespace}space","preserve")
                    t.text=line
                changed=True
        xml=ET.tostring(root,encoding="UTF-8",xml_declaration=True,standalone=True) if changed else original.read("word/document.xml")
        dest.parent.mkdir(parents=True,exist_ok=True)
        with ZipFile(dest,"x") as output:
            output.comment=original.comment
            for item in original.infolist():
                output.writestr(item,xml if item.filename=="word/document.xml" else original.read(item.filename))
