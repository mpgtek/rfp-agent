"""Normalized Q&A source adapters. No implicit network calls or prose-to-fact inference."""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Iterable

from .db import digest
from .excel import extract, text


@dataclass
class QA:
    question: str
    answer: str
    provenance: dict


class SourceAdapter(Protocol):
    def read(self, path: Path) -> Iterable[QA]: ...


class ExcelSource:
    def __init__(self, **mapping):
        self.mapping = mapping

    def read(self, path):
        from openpyxl import load_workbook
        detected, rows = extract(path, **self.mapping)
        book = load_workbook(path, data_only=False)
        try:
            metadata = {"category", "owner", "capability", "evidence document", "evidence section",
                        "document version", "reviewed on", "evidence kind"}
            headers = {layout["sheet"]: {c.column: text(c.value).casefold()
                for c in book[layout["sheet"]][layout["header_row"]] if text(c.value).casefold() in metadata}
                for layout in detected}
            for r in rows:
                if r["existing"] and not r["existing"].startswith("="):
                    provenance = {"location": f'{r["sheet"]}!{r["question_cell"]}:{r["response_cell"]}'}
                    details = {name: text(book[r["sheet"]].cell(r["row"], col).value)
                               for col, name in headers[r["sheet"]].items()}
                    if details:
                        provenance["source_metadata"] = details
                    yield QA(r["question"], r["existing"], provenance)
        finally:
            book.close()


class CSVSource:
    def read(self, path):
        from .excel import Q_HEADERS, A_HEADERS
        rows = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig")))
        qs = [h for h in rows.fieldnames or [] if h.strip().casefold() in Q_HEADERS]
        answers = [h for h in rows.fieldnames or [] if h.strip().casefold() in A_HEADERS]
        if len(qs) != 1 or len(answers) != 1:
            raise ValueError("CSV requires unambiguous Question and Answer headers")
        for n, row in enumerate(rows, 2):
            if text(row[qs[0]]) and text(row[answers[0]]):
                yield QA(text(row[qs[0]]), text(row[answers[0]]), {"location": f"record:{n}"})


class TextSource:
    def read(self, path):
        # Explicit Q:/A: only. Arbitrary prose requires a future reviewed extraction stage.
        content = path.read_text(encoding="utf-8")
        for match in re.finditer(r"(?ms)^Q:\s*(.+?)\nA:\s*(.+?)(?=\nQ:|\Z)", content):
            yield QA(match[1].strip(), match[2].strip(),
                     {"location": f"line:{content[:match.start()].count(chr(10)) + 1}"})


class DocxSource:
    def read(self, path):
        from docx import Document
        doc = Document(path)
        for ti, table in enumerate(doc.tables, 1):
            from .excel import Q_HEADERS, A_HEADERS
            headers = [text(c.text).casefold() for c in table.rows[0].cells]
            qs = [i for i, h in enumerate(headers) if h in Q_HEADERS]
            ans = [i for i, h in enumerate(headers) if h in A_HEADERS]
            if len(qs) == len(ans) == 1:
                for ri, row in enumerate(table.rows[1:], 2):
                    q, a = row.cells[qs[0]].text.strip(), row.cells[ans[0]].text.strip()
                    if q and a:
                        yield QA(q, a, {"location": f"table:{ti}/row:{ri}"})
        yield from paragraph_qa(doc.paragraphs)


def paragraph_qa(paragraphs):
    """Explicit Q:/Q1:/Question 1: blocks, with section-aware paragraph provenance."""
    question_marker = re.compile(r"^(?:Q|Question)\s*(\d+)?\s*:\s*(.*)$", re.I)
    answer_marker = re.compile(r"^(?:A|Answer)\s*(\d+)?\s*:\s*(.*)$", re.I)
    blocks = [(i, p.text.strip(), p.style.name if p.style else "") for i, p in enumerate(paragraphs, 1)]
    section, question, answer, question_at, answer_at, label = "", [], [], None, [], ""
    reading_answer = False

    def emit():
        if question and answer and "\n".join(answer).strip():
            end = answer_at[-1]
            return QA("\n".join(question).strip(), "\n".join(answer).strip(), {
                "location": f"paragraph:{question_at}/answer:{answer_at[0]}-{end}",
                "section": section, "question_label": label, "question_paragraph": question_at,
                "answer_paragraphs": list(answer_at)})
        return None

    for index, (number, value, style) in enumerate(blocks):
        if not value:
            continue
        q = question_marker.match(value)
        a = answer_marker.match(value)
        if q:
            item = emit()
            if item:
                yield item
            question, answer, answer_at = [q[2]], [], []
            question_at, label, reading_answer = number, "Q" + (q[1] or ""), False
            continue
        if a:
            if question_at is not None:
                reading_answer = True
                answer.append(a[2])
                answer_at.append(number)
            continue
        following = next((v for _, v, _ in blocks[index + 1:] if v), "")
        next_question = question_marker.match(following)
        previous_blank = index == 0 or not blocks[index - 1][1]
        # Plain exported Word documents often lose Heading styles. A short
        # blank-separated title before a restarted Q1 is a section boundary.
        plain_heading = (previous_blank and next_question and next_question[1] == "1"
                         and len(value) <= 100 and not value.endswith((".", "?", "!", ";", ":"))
                         and not re.match(r"^\d+[.)]", value))
        if style.casefold().startswith("heading") or plain_heading:
            item = emit()
            if item:
                yield item
            section = value
            question, answer, answer_at = [], [], []
            question_at, reading_answer = None, False
            continue
        if question_at is not None:
            if reading_answer:
                answer.append(value)
                answer_at.append(number)
            else:
                question.append(value)
    item = emit()
    if item:
        yield item


class ExportSource:
    """Normalized Confluence/Notion JSON export boundary; live fetch intentionally absent."""
    def read(self, path):
        data = json.loads(path.read_text())
        if data.get("provider") not in {"confluence", "notion"}:
            raise ValueError("JSON export provider must be confluence or notion")
        for record in data["records"]:
            required = ("question", "answer", "page_id", "url", "version")
            if any(not text(record.get(k)) for k in required):
                raise ValueError("Export record missing question/answer/page_id/url/version")
            yield QA(record["question"], record["answer"], {
                "location": f'page:{record["page_id"]}', "provider": data["provider"],
                "url": record["url"], "upstream_version": record["version"]})


ADAPTERS = {".xlsx": ExcelSource, ".csv": CSVSource, ".docx": DocxSource,
            ".md": TextSource, ".txt": TextSource, ".json": ExportSource}


def ingest(store, source, scope, submitter="source-import", **mapping):
    """Low-level staging primitive. User-facing imports use importing.import_source."""
    source = Path(source).resolve()
    if source.is_dir():
        if source == store.root or store.root in source.parents or source in store.root.parents:
            raise ValueError("Source directory must not contain or be inside persistent workspace")
        files = sorted(p for p in source.rglob("*") if p.is_file() and not p.is_symlink() and p.suffix.lower() in ADAPTERS)
    else:
        files = [source]
    if not files:
        raise ValueError("No supported source files")
    staged = []
    # Parse every input before changing the KB; malformed batches fail atomically.
    parsed = []
    for path in files:
        adapter = ADAPTERS.get(path.suffix.lower())
        if not adapter:
            raise ValueError(f"Unsupported source: {path.suffix}")
        content = path.read_bytes()
        sha = digest(content)
        snapshot = store.root / "sources" / (sha + path.suffix.lower())
        qa = list((adapter(**mapping) if adapter is ExcelSource else adapter()).read(path))
        if path.read_bytes() != content:
            raise ValueError("Source changed during ingestion; retry from a stable copy")
        if not qa:
            raise ValueError(f"No explicit Q&A records in {path.name}")
        parsed.append((path, content, sha, snapshot, qa))
    with store.transaction():
        for path, content, sha, snapshot, qa in parsed:
            if not snapshot.exists():
                snapshot.write_bytes(content)
            for item in qa:
                provenance = dict(item.provenance, source=str(path), sha256=sha, snapshot=str(snapshot))
                staged.append(store.stage(question=item.question, answer=item.answer, scope=scope,
                    provenance=provenance, submitter=submitter, deduplicate=True, fingerprint=digest(json.dumps(
                        [str(path), sha, item.provenance, item.question, item.answer, scope], sort_keys=True).encode())))
    return list(dict.fromkeys(staged))
