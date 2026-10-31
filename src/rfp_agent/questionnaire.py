"""Questionnaire dispatch; source-Q&A adapters remain separate."""
from pathlib import Path
from . import excel,word


def adapter(path):
    suffix=Path(path).suffix.lower()
    if suffix==".xlsx":
        return excel
    if suffix==".docx":
        return word
    raise ValueError("Questionnaires must be .xlsx or .docx")


def extract(path,**mapping):
    return adapter(path).extract(path,**mapping)


def patch_copy(source,dest,changes,*,mapping=None):
    handler=adapter(source)
    return handler.patch_copy(source,dest,changes,**({"mapping":mapping} if handler is word else {}))
