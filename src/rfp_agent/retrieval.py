"""Read-only evidence preparation for the host LLM's semantic coverage review.

Keyword ranks discover candidates; they never establish answer equivalence.
Paged scoped KB access prevents the top-five retrieval cutoff hiding facts.
"""
import re
from pathlib import Path
from .db import digest
from .grounding import freshness_problem
from .questionnaire import extract


def prepare(store,source,scope,*,kb_offset=0,kb_limit=200,max_age_days=365,**mapping):
    if kb_offset<0 or not 1<=kb_limit<=1000 or max_age_days<0:
        raise ValueError("Invalid KB page or evidence age limit")
    source=Path(source)
    before=source.read_bytes()
    layouts,rows=extract(source,**mapping)
    if source.read_bytes()!=before:
        raise ValueError("Source changed during evidence preparation")
    with store.db:
        store.db.execute("BEGIN")
        count=store.db.execute("SELECT COUNT(*) FROM entries WHERE scope=?",(scope,)).fetchone()[0]
        ids=[r[0] for r in store.db.execute("SELECT id FROM entries WHERE scope=? ORDER BY id LIMIT ? OFFSET ?",
                                          (scope,kb_limit,kb_offset))]
        def evidence(eid):
            item=store.evidence(eid)
            return dict(item,usability_problem=freshness_problem(store,item,scope,max_age_days))
        scoped=[evidence(eid) for eid in ids]
        contexts=[]
        for row in rows:
            queries=list(dict.fromkeys([row["question"]]+[s.strip() for s in re.split(r"[,;/]|\band\b",row["question"]) if s.strip()]))
            candidates={}
            for query in queries:
                for candidate in store.retrieve(query,scope,limit=20):
                    candidates.setdefault(candidate["id"],evidence(candidate["id"]))
            contexts.append(dict(row,search_queries=queries,candidate_entry_ids=list(candidates)))
            for item in candidates.values():
                if item["id"] not in {e["id"] for e in scoped}:
                    scoped.append(item)
    return {"format":"rfp-agent.evidence-context.v1","source_sha256":digest(before),"scope":scope,
            "layouts":layouts,"rows":contexts,"scoped_kb":scoped,"scoped_entry_count":count,
            "kb_offset":kb_offset,"next_kb_offset":kb_offset+kb_limit if kb_offset+kb_limit<count else None,
            "instructions":"Host agent: interpret every requirement, enumerate requested items, read scoped KB facts semantically, and produce a claim-cited evidence map. Search ranks and source questions are not proof of answer coverage. Use usable answer text only. Write supported portions, list missing portions as SME questions, and leave wholly unsupported responses blank. No embedding service was called."}
