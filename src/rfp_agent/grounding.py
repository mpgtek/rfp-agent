"""Source-bound KB selection and claim-cited response composition."""
import json
import re
from datetime import datetime,timezone
from pathlib import Path
from .db import digest,norm


def load_selections(path,source_bytes,scope,rows):
    if not path:
        return {},None
    raw=Path(path).read_bytes()
    data=json.loads(raw)
    if data.get("format")!="rfp-agent.evidence-map.v1" or data.get("source_sha256")!=digest(source_bytes) or data.get("scope")!=scope:
        raise ValueError("Evidence map format, source checksum or scope does not match")
    allowed={(r["sheet"],r["response_cell"]):r for r in rows}
    selections={}
    for item in data.get("mappings",[]):
        key=(item.get("sheet"),item.get("response_cell"))
        if key not in allowed or key in selections or item.get("question")!=allowed[key]["question"]:
            raise ValueError("Evidence map has unknown, duplicate or changed question/cell")
        if item.get("coverage") not in {"complete","partial","none"} or not item.get("note","").strip():
            raise ValueError("Evidence selection requires coverage and a support rationale")
        selections[key]=item
    return selections,{"sha256":digest(raw),"content":data}


def freshness_problem(store,evidence,scope,max_age_days):
    age=(datetime.now(timezone.utc)-datetime.fromisoformat(evidence["approved_at"])).days
    if age>max_age_days:
        return "KB evidence is stale"
    if any(p["target"]==evidence["id"] or norm(p["question"])==evidence["normalized"]
           for p in store.db.execute("SELECT target,question FROM proposals WHERE status='pending' AND scope=? AND kind='canonical'",(scope,))):
        return "KB answer has an unresolved replacement proposal"
    return None


def known_draft(store,row,scope,router,max_age_days,selection=None):
    # Import lazily to keep the existing retrieval/draft layer independently usable.
    from .workflow import draft
    question=row["question"]
    candidates=store.retrieve(question,scope)
    def blank(reason):
        return {"answer":"","status":"insufficient","reason":reason,"evidence":candidates}
    if selection is None:
        if not candidates or not candidates[0]["exact"]:
            return blank("Skipped: no exact/current approved variant or verified per-run evidence selection")
        problem=freshness_problem(store,candidates[0],scope,max_age_days)
        if problem:
            return blank("Skipped: "+problem)
        result=draft(store,question,scope,router,max_age_days)
        if result["answer"] and result["answer"]!=candidates[0]["answer"]:
            return blank("Skipped: answer is not the exact stored KB response")
        return result
    from .coverage import validate_coverage
    requirements=validate_coverage(selection)
    if selection["coverage"]=="none":
        if requirements is None:
            raise ValueError("No-evidence selections require item-level SME questions")
        return dict(blank("No requested item is supported by usable KB evidence"),
                    requirements=requirements,coverage="none")
    if selection["coverage"]=="partial" and requirements is None:
        return blank("Skipped: selected evidence covers only part of the requirement")
    parts=selection.get("parts",[])
    if not parts:
        raise ValueError("A complete evidence selection must contain KB references")
    evidence,quotes=[],[]
    for part in parts:
        if type(part.get("entry_id")) is not int or type(part.get("revision")) is not int:
            raise ValueError("Evidence selection requires integer entry/revision IDs")
        item=store.evidence(part["entry_id"])
        if not item or item["scope"]!=scope or item["revision"]!=part["revision"]:
            raise ValueError("Selected evidence is missing, stale or outside scope")
        problem=freshness_problem(store,item,scope,max_age_days)
        if problem:
            return blank("Skipped: "+problem)
        quote=part.get("quote","")
        # Full lines/paragraphs preserve qualifiers/negation. Arbitrary substrings
        # such as 'support OIDC' from 'We do not support OIDC' are forbidden.
        blocks={item["answer"].strip(),*(p.strip() for p in item["answer"].split("\n\n")),
                *(p.strip() for p in item["answer"].splitlines()),
                *(p.strip() for p in re.split(r'(?<=[.!?])\s+(?=[A-Z])',item["answer"]))}
        if not isinstance(quote,str) or not quote.strip() or quote!=quote.strip() or quote not in blocks:
            raise ValueError("Response must contain only complete verbatim KB lines/paragraphs")
        if norm(question)!=item["normalized"] and len(norm(quote).split())<3:
            raise ValueError("Bare yes/no or context-free fragments cannot answer a different question")
        quotes.append(quote)
        evidence.append(dict(item,exact=False,score=0.0))
    answer="\n\n".join(dict.fromkeys(quotes))
    composition=None
    if "response" in selection:
        from .composition import compose
        answer,composition=compose(selection,quotes)
        composition["parts"]=selection["parts"]
    return {"answer":answer,"status":"partial" if selection["coverage"]=="partial" else "needs-review",
            "coverage":selection["coverage"],"requirements":requirements or [],
            "reason":("KB-grounded composed response" if composition else "Verbatim KB selection")+"; per-run coverage rationale: "+selection["note"],
            "composition":composition,
            "evidence":list({e["id"]:e for e in evidence}.values())}
