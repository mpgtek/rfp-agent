"""Import new source Q&A directly; reserve change review for existing-answer collisions."""
from .adapters import ingest
from .change_review import export_changes
from .db import norm


def import_source(store, source, scope, submitter="source-import", review_format="xlsx", **mapping):
    imported, unchanged, collisions = [], [], []
    with store.transaction():
        ids = ingest(store, source, scope, submitter, **mapping)
        for pid in ids:
            proposal = store.db.execute("SELECT * FROM proposals WHERE id=?", (pid,)).fetchone()
            if proposal["status"] != "pending":
                unchanged.append(pid)
                continue
            # Exact canonical questions and current, approved variants count as
            # identity. Lexical/semantic similarity alone is not a collision.
            target = store.db.execute("""SELECT e.id FROM entries e LEFT JOIN variants v
                ON v.entry_id=e.id AND v.revision_id=e.head AND v.scope=e.scope
                WHERE e.scope=? AND (e.normalized=? OR v.normalized=?) LIMIT 1""",
                (scope, norm(proposal["question"]), norm(proposal["question"]))).fetchone()
            if target is None:
                store.resolve([pid], submitter, "New Q&A imported from user-supplied source; no existing KB answer",
                              direct_import=True)
                imported.append(pid)
                continue
            current = store.evidence(target[0])
            if current["answer"] == proposal["answer"]:
                store.db.execute("UPDATE proposals SET status='unchanged',resolved_by=?,reason=? WHERE id=?",
                                 (submitter, "Same current answer; source observation retained", pid))
                store.audit(submitter, "unchanged_source_observed", {"proposal":pid,"entry":current["id"]})
                unchanged.append(pid)
                continue
            store.db.execute("UPDATE proposals SET target=?,base=? WHERE id=?",
                             (current["id"], current["revision"], pid))
            collisions.append(pid)
        review = export_changes(store, collisions, scope, file_format=review_format) if collisions else None
    return {"proposal_ids":ids,"imported":len(imported),"unchanged":len(unchanged),
            "collisions":len(collisions),"imported_ids":imported,"collision_ids":collisions,
            "change_review":review}
