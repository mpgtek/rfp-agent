"""Item-level coverage metadata, assessed by the host agent against KB evidence."""


def validate_coverage(selection):
    items=selection.get("requirements")
    if items is None:
        return None  # Older maps remain readable; unstructured partial maps stay blank.
    if not isinstance(items,list) or not items:
        raise ValueError("Requirement coverage must list the requested items")
    ids=set()
    supported={}
    missing=[]
    parts=selection.get("parts",[])
    for item in items:
        if not isinstance(item,dict):
            raise ValueError("Invalid requirement item")
        key=item.get("id")
        if not isinstance(key,str) or not key.strip() or key in ids:
            raise ValueError("Requirement IDs must be nonempty and unique")
        ids.add(key)
        if not isinstance(item.get("text"),str) or not item["text"].strip() or not item.get("note","").strip():
            raise ValueError("Each requirement item needs text and a coverage rationale")
        indices=item.get("part_indices",[])
        if not isinstance(indices,list) or any(type(i) is not int or i<0 or i>=len(parts) for i in indices):
            raise ValueError("Requirement item has invalid evidence-part references")
        if item.get("state")=="supported":
            if not indices:
                raise ValueError("Supported requirement items need KB evidence")
            supported[key]=set(indices)
        elif item.get("state")=="missing":
            if indices or not isinstance(item.get("sme_question"),str) or not item["sme_question"].strip():
                raise ValueError("Missing items need a specific SME question and no support citations")
            missing.append(item)
        else:
            raise ValueError("Requirement state must be supported or missing")
        if item.get("meets_requirement") is not None and type(item["meets_requirement"]) is not bool:
            raise ValueError("Requirement compliance must be true, false or unknown")
    expected="none" if not supported else "partial" if missing else "complete"
    if selection["coverage"]!=expected:
        raise ValueError("Coverage label contradicts the item-level coverage")
    if not supported:
        if parts or selection.get("response") or selection.get("claims"):
            raise ValueError("No-evidence requirements cannot contain a customer answer")
        return items
    if selection["coverage"]=="partial" and not selection.get("response"):
        raise ValueError("Partial answers require a claim-cited composition")
    if "response" in selection:
        covered=set()
        for claim in selection.get("claims",[]):
            if not isinstance(claim,dict):
                raise ValueError("Invalid claim coverage")
            refs=claim.get("requirement_ids",[])
            if not isinstance(refs,list) or not refs or any(not isinstance(r,str) or r not in supported for r in refs):
                raise ValueError("Claims must reference supported requirement IDs only")
            allowed=set().union(*(supported[r] for r in refs))
            if not set(claim.get("part_indices",[]))<=allowed:
                raise ValueError("Claim evidence must belong to its supported requirement items")
            covered.update(refs)
        if covered!=set(supported):
            raise ValueError("Every supported requirement item must appear in the response claims")
    return items
