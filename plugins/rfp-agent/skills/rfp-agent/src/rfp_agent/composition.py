"""Bounded, claim-cited response composition authored by the host agent.

These are deterministic reference/anchor checks, not a semantic entailment proof.
The host agent must assess support, relevance and coverage before submission.
"""
import re
from .db import norm

# Connective prose and neutral presentation vocabulary. Capability, protocol,
# vendor, quantity and commitment terms must come from the cited answer text.
GLUE=set("a an the and or of in on at to for from by with as is are was were be been being we our us it its this that these those their them they which who through after into about do does has have can also each platform application service deployment deployments environment customer customers host hosted hosting use uses using available provide provides provided support supports perform performs performed review reviewed management findings finding issues issue go goes".split())
NEGATIVE={"no","not","cannot","never","without","dont","doesnt","isnt","arent"}
FUTURE={"planned","future","roadmap","proposed","upcoming"}


def words(value):
    # Keep contractions as polarity markers rather than losing the n't suffix.
    value=re.sub(r"(?<=\d)(?=[A-Za-z])"," ",value)
    return norm(value.replace("’", "'").replace("'", "")).split()


def forms(word):
    result={word}
    if len(word)>4 and word.endswith("s"):
        result.add(word[:-1])
    if len(word)>5 and word.endswith("ly"):
        result.add(word[:-2])
    for ending in ("ed","ing"):
        if len(word)>len(ending)+3 and word.endswith(ending):
            stem=word[:-len(ending)]
            result.update((stem,stem+"e"))
    return result


def compose(selection,quotes):
    response=selection.get("response")
    claims=selection.get("claims")
    review=selection.get("composition_review",{})
    if not isinstance(response,str) or not response.strip() or len(response)>6000:
        raise ValueError("Composed response must be nonempty and concise (maximum 6000 characters)")
    if not isinstance(claims,list) or not claims:
        raise ValueError("Composed responses require claim-by-claim KB citations")
    if any(review.get(key) is not True for key in ("supported","relevant","appropriate_detail")):
        raise ValueError("Composition review must confirm support, completeness, relevance and appropriate detail")
    if selection.get("coverage")=="partial":
        if review.get("complete") is not False or review.get("coverage_checked") is not True:
            raise ValueError("Partial composition must acknowledge incomplete coverage and reviewed gaps")
    elif review.get("complete") is not True:
        raise ValueError("Composition review must confirm completeness")
    texts=[]
    checked=[]
    for claim in claims:
        if not isinstance(claim,dict) or not isinstance(claim.get("text"),str) or not claim["text"].strip():
            raise ValueError("Each claim requires text")
        indices=claim.get("part_indices",[])
        if not indices or any(type(i) is not int or i<0 or i>=len(quotes) for i in indices):
            raise ValueError("Each claim must cite valid evidence-part indices")
        if claim.get("supported") is not True or not claim.get("support_note","").strip():
            raise ValueError("Each claim requires an explicit support assessment")
        text=claim["text"].strip()
        sources=[quotes[i] for i in indices]
        source="\n".join(sources)
        supported_words=set().union(*(forms(w) for w in words(source)))|GLUE
        unsupported=[w for w in words(text) if forms(w).isdisjoint(supported_words)]
        if unsupported:
            raise ValueError("Composed claim introduces unsupported terminology: "+", ".join(dict.fromkeys(unsupported)))
        # Literal technical numbers (e.g. 99.9%, TLS 1.3) cannot be assembled
        # from unrelated digits appearing in source references.
        numbers=set(re.findall(r"\b\d+(?:\.\d+)?%?",source))
        if any(value not in numbers for value in re.findall(r"\b\d+(?:\.\d+)?%?",text)):
            raise ValueError("Composed claim changes a sourced numeric value")
        target_words=set(words(text))
        source_words=set(words(source))
        if target_words&NEGATIVE and not source_words&NEGATIVE:
            raise ValueError("Composed claim reverses positive source polarity")
        if not target_words&NEGATIVE:
            target_content=set().union(*(forms(w) for w in target_words if w not in GLUE))
            for quote in sources:
                tokens=words(quote)
                for index,token in enumerate(tokens):
                    if token in NEGATIVE:
                        negative_objects=set().union(*(forms(w) for w in tokens[index+1:index+12] if w not in GLUE))
                        if target_content&negative_objects:
                            raise ValueError("Composed claim drops a relevant source negation")
        if source_words&FUTURE and not target_words&FUTURE:
            raise ValueError("Composed claim cannot turn a future capability into a current one")
        if "only" in source_words and "only" not in target_words:
            raise ValueError("Composed claim must retain an explicit source-only restriction")
        texts.append(text)
        checked.append({"text":text,"part_indices":indices,"support_note":claim["support_note"]})
        if "requirement_ids" in claim:
            checked[-1]["requirement_ids"]=claim["requirement_ids"]
    # Everything written to the customer must belong to a cited claim.
    if " ".join(response.split())!=" ".join(" ".join(texts).split()):
        raise ValueError("Response contains uncited text or differs from its claims")
    return response.strip(),{"claims":checked,"review":review,
                             "verification":"Reference, terminology, numeric and polarity checks; semantic review is agent-assessed"}
