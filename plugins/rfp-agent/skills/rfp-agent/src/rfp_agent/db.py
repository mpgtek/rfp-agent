from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def norm(text):
    # Preserve words, digits and negation. No synonym or polarity collapsing.
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold()))


def digest(data):
    return hashlib.sha256(data).hexdigest()


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(version INTEGER NOT NULL);
INSERT INTO meta SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM meta);
CREATE TABLE IF NOT EXISTS entries(
 id INTEGER PRIMARY KEY, question TEXT NOT NULL, normalized TEXT NOT NULL,
 scope TEXT NOT NULL, head INTEGER, UNIQUE(normalized,scope));
CREATE TABLE IF NOT EXISTS revisions(
 id INTEGER PRIMARY KEY, entry_id INTEGER NOT NULL REFERENCES entries(id),
 answer TEXT NOT NULL, provenance TEXT NOT NULL, approved_by TEXT NOT NULL,
 approved_at TEXT NOT NULL, reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS variants(
 normalized TEXT NOT NULL, scope TEXT NOT NULL, entry_id INTEGER NOT NULL REFERENCES entries(id),
 revision_id INTEGER NOT NULL REFERENCES revisions(id), question TEXT NOT NULL,
 PRIMARY KEY(normalized,scope));
CREATE TABLE IF NOT EXISTS proposals(
 id INTEGER PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE,
 kind TEXT NOT NULL, question TEXT NOT NULL, answer TEXT NOT NULL, scope TEXT NOT NULL,
 target INTEGER REFERENCES entries(id), base INTEGER, provenance TEXT NOT NULL,
 submitted_by TEXT NOT NULL, created_at TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', resolved_by TEXT, reason TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(question,answer,entry_id UNINDEXED);
CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, manifest TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS drafts(
 id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id), payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit(
 id INTEGER PRIMARY KEY, at TEXT NOT NULL, actor TEXT NOT NULL, event TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_observations(
 fingerprint TEXT PRIMARY KEY, proposal_id INTEGER NOT NULL REFERENCES proposals(id), provenance TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS change_reviews(
 id TEXT PRIMARY KEY, created_at TEXT NOT NULL, scope TEXT, output_path TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS change_review_rows(
 review_id TEXT NOT NULL REFERENCES change_reviews(id),
 proposal_id INTEGER NOT NULL REFERENCES proposals(id), snapshot TEXT NOT NULL,
 applied_fingerprint TEXT, application TEXT, applied_at TEXT,
 PRIMARY KEY(review_id,proposal_id));
CREATE TABLE IF NOT EXISTS sme_review_packets(
 id TEXT PRIMARY KEY, created_at TEXT NOT NULL, output_path TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sme_review_items(
 packet_id TEXT NOT NULL REFERENCES sme_review_packets(id),
 row_id TEXT NOT NULL, payload TEXT NOT NULL,
 decision_fingerprint TEXT, application TEXT,
 PRIMARY KEY(packet_id,row_id));
"""


class Store:
    def __init__(self, workspace):
        self.root = Path(workspace).expanduser().resolve()
        code = Path(__file__).resolve().parents[2]
        protected = code.parent.parent if code.parent.name == "skills" and (code.parent.parent / ".claude-plugin").is_dir() else code
        if protected.parent.name == "plugins" and (protected.parent.parent / ".git").exists():
            protected = protected.parent.parent
        if self.root == protected or protected in self.root.parents:
            raise ValueError("Persistent workspace must be outside the code repository")
        self.root.mkdir(parents=True, exist_ok=True)
        for child in ("sources", "runs"):
            (self.root / child).mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.root / "knowledge.sqlite3", timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        if self.db.execute("SELECT version FROM meta").fetchone()[0] != 1:
            raise ValueError("Unsupported database schema version")

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        """Join an existing caller-owned transaction, or create an atomic write batch."""
        if self.db.in_transaction:
            yield
        else:
            with self.db:
                self.db.execute("BEGIN IMMEDIATE")
                yield

    def audit(self, actor, event, payload):
        self.db.execute("INSERT INTO audit(at,actor,event,payload) VALUES(?,?,?,?)",
                        (now(), actor, event, json.dumps(payload)))

    def stage(self, *, question, answer, scope, provenance, submitter,
              kind="canonical", target=None, fingerprint=None, deduplicate=False):
        if not question.strip() or not answer.strip() or not scope.strip() or not submitter.strip():
            raise ValueError("Question, answer, scope and submitter are required")
        if kind not in {"canonical", "variant"}:
            raise ValueError("Unknown proposal kind")
        if target is None:
            row = self.db.execute("SELECT id FROM entries WHERE normalized=? AND scope=?",
                                  (norm(question), scope)).fetchone()
            target = row[0] if row else None
        base = None
        if target is not None:
            entry = self.db.execute("SELECT * FROM entries WHERE id=? AND scope=?", (target, scope)).fetchone()
            if not entry:
                raise ValueError("Target is absent or belongs to another scope")
            base = entry["head"]
        if kind == "variant" and base is None:
            raise ValueError("Variant requires an approved target")
        fingerprint = fingerprint or digest(json.dumps(
            [question, answer, scope, provenance, kind, target], sort_keys=True).encode())
        existing = self.db.execute("SELECT id FROM proposals WHERE fingerprint=? UNION SELECT proposal_id FROM source_observations WHERE fingerprint=?",
                                  (fingerprint, fingerprint)).fetchone()
        if existing:
            return existing[0]
        if deduplicate:
            for candidate in self.db.execute("SELECT * FROM proposals WHERE status='pending' AND kind=? AND scope=? AND answer=?",
                                              (kind, scope, answer.strip())):
                if norm(candidate["question"]) == norm(question) and candidate["target"] == target and candidate["base"] == base:
                    self.db.execute("INSERT INTO source_observations VALUES(?,?,?)",
                                    (fingerprint, candidate["id"], json.dumps(provenance)))
                    self.audit(submitter, "duplicate_source_observed", {"proposal": candidate["id"], "provenance": provenance})
                    return candidate["id"]
        cur = self.db.execute("""INSERT INTO proposals(fingerprint,kind,question,answer,scope,
            target,base,provenance,submitted_by,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (fingerprint, kind, question.strip(), answer.strip(), scope, target, base,
             json.dumps(provenance), submitter, now()))
        self.audit(submitter, "proposal_created", {"proposal": cur.lastrowid})
        if deduplicate:
            self.db.execute("INSERT INTO source_observations VALUES(?,?,?)", (fingerprint, cur.lastrowid, json.dumps(provenance)))
        return cur.lastrowid

    def resolve(self, ids, actor, reason, approve=True, *, direct_import=False, approved_sme_import=False):
        if not actor.strip() or not reason.strip():
            raise ValueError("Approver and reason are required")
        results = []
        with self.transaction():
            for pid in ids:
                p = self.db.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
                if not p or p["status"] != "pending":
                    raise ValueError(f"Proposal {pid} is absent or already resolved")
                if direct_import and (not approve or p["kind"] != "canonical" or p["target"] is not None or p["base"] is not None):
                    raise ValueError("Direct source import may only create new canonical answers")
                if approved_sme_import and (not approve or p["kind"] != "canonical" or p["target"] is not None or p["base"] is not None):
                    raise ValueError("SME-approved import may only create new canonical answers")
                if not direct_import and not approved_sme_import and actor.casefold().strip() == p["submitted_by"].casefold().strip():
                    raise ValueError("Submitter cannot approve or reject their own proposal")
                eid = p["target"]
                if approve:
                    if eid is None:
                        if self.db.execute("SELECT 1 FROM entries WHERE normalized=? AND scope=?",
                                           (norm(p["question"]), p["scope"])).fetchone():
                            raise ValueError("Concurrent canonical creation; restage against current entry")
                        eid = self.db.execute("INSERT INTO entries(question,normalized,scope) VALUES(?,?,?)",
                            (p["question"], norm(p["question"]), p["scope"])).lastrowid
                    entry = self.db.execute("SELECT * FROM entries WHERE id=?", (eid,)).fetchone()
                    if entry["head"] != p["base"]:
                        raise ValueError("Stale proposal: canonical revision changed; restage after review")
                    collision = self.db.execute("SELECT id FROM entries WHERE normalized=? AND scope=?",
                                                (norm(p["question"]), p["scope"])).fetchone()
                    if collision and collision[0] != eid:
                        raise ValueError("Question already belongs to a different canonical entry")
                    variant = self.db.execute("SELECT entry_id FROM variants WHERE normalized=? AND scope=?",
                                              (norm(p["question"]), p["scope"])).fetchone()
                    if variant and variant[0] != eid:
                        raise ValueError("Variant already maps to a different canonical entry")
                    if p["kind"] == "canonical":
                        provenance = json.loads(p["provenance"])
                        if direct_import:
                            provenance["acceptance"] = {"method": "direct-source-import", "actor": actor,
                                                        "sme_approval": False}
                        if approved_sme_import:
                            provenance["acceptance"] = {"method":"explicit-sme-review", "actor":actor,
                                                        "sme_approval":True}
                        observations = [json.loads(r[0]) for r in self.db.execute(
                            "SELECT provenance FROM source_observations WHERE proposal_id=?", (pid,))]
                        if observations:
                            provenance["source_observations"] = observations
                        rid = self.db.execute("""INSERT INTO revisions(entry_id,answer,provenance,
                            approved_by,approved_at,reason) VALUES(?,?,?,?,?,?)""",
                            (eid, p["answer"], json.dumps(provenance), actor, now(), reason)).lastrowid
                        self.db.execute("UPDATE entries SET head=? WHERE id=?", (rid, eid))
                        self.db.execute("DELETE FROM kb_fts WHERE entry_id=?", (eid,))
                        self.db.execute("INSERT INTO kb_fts(question,answer,entry_id) VALUES(?,?,?)",
                                        (entry["question"], p["answer"], eid))
                    else:
                        rid = entry["head"]
                        answer = self.db.execute("SELECT answer FROM revisions WHERE id=?", (rid,)).fetchone()[0]
                        if p["answer"] != answer:
                            raise ValueError("Variant answer differs from canonical; use a canonical proposal")
                    self.db.execute("INSERT OR REPLACE INTO variants VALUES(?,?,?,?,?)",
                                    (norm(p["question"]), p["scope"], eid, rid, p["question"]))
                    results.append({"proposal": pid, "entry": eid, "revision": rid})
                self.db.execute("UPDATE proposals SET status=?,resolved_by=?,reason=? WHERE id=?",
                                ("approved" if approve else "rejected", actor, reason, pid))
                self.audit(actor, "source_imported" if direct_import else "approved" if approve else "rejected",
                           {"proposal": pid, "reason": reason})
        return results

    def evidence(self, eid):
        row = self.db.execute("""SELECT e.id,e.question,e.normalized,e.scope,r.id revision,
            r.answer,r.provenance,r.approved_at,r.approved_by FROM entries e
            JOIN revisions r ON e.head=r.id WHERE e.id=?""", (eid,)).fetchone()
        return dict(row) if row else None

    def retrieve(self, question, scope, limit=5):
        exact = self.db.execute("""SELECT e.id FROM entries e LEFT JOIN variants v ON
            v.entry_id=e.id AND v.revision_id=e.head AND v.scope=e.scope
            WHERE e.scope=? AND (e.normalized=? OR v.normalized=?) LIMIT 1""",
            (scope, norm(question), norm(question))).fetchone()
        if exact:
            return [dict(self.evidence(exact[0]), exact=True, score=1.0)]
        stop = {"do", "you", "your", "the", "a", "an", "is", "are", "and", "or", "of", "for", "to", "in", "does", "how", "what", "can", "with", "describe", "explain", "provide"}
        terms = list(dict.fromkeys(t for t in norm(question).split() if t not in stop))[:40]
        if not terms:
            return []
        query = " OR ".join('"' + t.replace('"', '""') + '"' for t in terms)
        rows = self.db.execute("""SELECT e.id FROM kb_fts JOIN entries e ON e.id=kb_fts.entry_id
            WHERE kb_fts MATCH ? AND e.scope=? ORDER BY bm25(kb_fts) LIMIT ?""",
            (query, scope, limit)).fetchall()
        evidence = []
        for row in rows:
            item = self.evidence(row[0])
            words = set(norm(item["question"] + " " + item["answer"]).split())
            score = len(set(terms) & words) / len(set(terms))
            if score >= 0.2:
                evidence.append(dict(item, exact=False, score=round(score, 4)))
        return sorted(evidence, key=lambda e: e["score"], reverse=True)
