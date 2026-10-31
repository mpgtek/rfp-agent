import argparse
import json
import sqlite3
import sys

from .importing import import_source
from .db import Store
from .demo import fixtures, run_demo
from .questionnaire import extract
from .workflow import answer_rfp, ingest_feedback
from .onboarding import active_workspace, configure, status as onboarding_status
from .change_review import apply_review, export_changes, looks_like_review
from .retrieval import prepare
from .sme_review import apply_sme_review,looks_like_sme_review


def mapping_options(parser):
    parser.add_argument("--sheet")
    parser.add_argument("--header-row", type=int)
    parser.add_argument("--question-column", help="Excel column letter")
    parser.add_argument("--response-column", help="Existing Excel column letter")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evidence-backed RFP drafts and approved learning")
    parser.add_argument("--workspace", help="Persistent data directory outside the code repository")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("setup", help="Save company/workspace and source selection for guided onboarding")
    p.add_argument("--company")
    p.add_argument("--scope")
    p.add_argument("--source", action="append", help="Select an original source file or directory; does not ingest it yet")
    p.add_argument("--defer-sources", action="store_true", help="Build a company profile conversationally before source ingestion")
    sub.add_parser("onboarding-status", help="Resume the saved company workflow and show its next step")
    sub.add_parser("init")
    p = sub.add_parser("ingest")
    p.add_argument("source")
    p.add_argument("--scope", help="Product/environment scope; defaults to saved company setup")
    p.add_argument("--submitter", default="source-import")
    p.add_argument("--review-format", choices=["xlsx", "csv"], default="xlsx")
    mapping_options(p)
    p = sub.add_parser("change-review", help="Export an editable old/new answer comparison for SME review")
    p.add_argument("--ids", type=int, nargs="+")
    p.add_argument("--scope")
    p.add_argument("--output")
    p.add_argument("--format", choices=["xlsx", "csv"], default="xlsx")
    p = sub.add_parser("apply-review", help="Validate and apply explicit SME Approved/Rejected decisions")
    p.add_argument("source")
    p = sub.add_parser("apply-sme-review",help="Apply Approved answers from a plain-language SME workbook")
    p.add_argument("source")
    p = sub.add_parser("detect")
    p.add_argument("source")
    mapping_options(p)
    p = sub.add_parser("proposals")
    p.add_argument("--status", choices=["pending", "approved", "rejected"], default="pending")
    for cmd in ("approve", "reject"):
        p = sub.add_parser(cmd)
        p.add_argument("ids", type=int, nargs="+")
        p.add_argument("--actor", required=True)
        p.add_argument("--reason", required=True)
    p = sub.add_parser("search")
    p.add_argument("question")
    p.add_argument("--scope", help="Product/environment scope; defaults to saved company setup")
    p = sub.add_parser("prepare",help="Prepare scoped evidence for semantic, item-by-item host-agent review")
    p.add_argument("source")
    p.add_argument("--scope")
    p.add_argument("--kb-offset",type=int,default=0)
    p.add_argument("--kb-limit",type=int,default=200)
    p.add_argument("--max-age-days",type=int,default=365)
    mapping_options(p)
    p = sub.add_parser("answer")
    p.add_argument("source")
    p.add_argument("--scope", help="Product/environment scope; defaults to saved company setup")
    p.add_argument("--config", help="Task model routing TOML")
    p.add_argument("--max-age-days", type=int, default=365)
    p.add_argument("--evidence-map",help="Source-bound claim-cited compositions, item coverage and SME gaps")
    mapping_options(p)
    p = sub.add_parser("feedback")
    p.add_argument("source")
    p = sub.add_parser("history")
    p.add_argument("entry", type=int)
    p = sub.add_parser("fixtures")
    p.add_argument("directory")
    sub.add_parser("demo")
    args = parser.parse_args(argv)
    mapping = {key: getattr(args, key) for key in ("sheet", "header_row", "question_column", "response_column") if getattr(args, key, None) is not None}
    store = None
    try:
        if args.command == "onboarding-status":
            result = onboarding_status(args.workspace)
        elif args.command == "setup":
            workspace = args.workspace or active_workspace()
            if not workspace:
                result = onboarding_status()
            else:
                result = configure(workspace, args.company, args.scope, args.source, args.defer_sources)
        elif args.command == "fixtures":
            result = {"fixtures": str(fixtures(args.directory))}
        elif args.command == "detect":
            detected, rows = extract(args.source, **mapping)
            result = {"layouts": detected, "question_count": len(rows)}
        else:
            workspace = args.workspace or active_workspace()
            if not workspace:
                parser.error("No company workspace selected; run the guided setup or pass --workspace")
            if not args.workspace and not onboarding_status(workspace).get("configured"):
                raise ValueError("Saved company setup is incomplete; resume setup before using this workspace")
            if args.command == "demo":
                if not args.workspace:
                    raise ValueError("Demo requires an explicit fresh --workspace; it never uses the saved company workspace")
                result = run_demo(workspace)
            else:
                store = Store(workspace)
                friendly_return=args.command in {"ingest","feedback","apply-review","apply-sme-review"} and looks_like_sme_review(args.source)
                returned_review = friendly_return or (args.command == "ingest" and looks_like_review(args.source))
                selected_scope = getattr(args, "scope", None)
                if selected_scope is None and args.command in {"ingest", "search", "prepare", "answer", "change-review"}:
                    selected_scope = onboarding_status(workspace).get("scope")
                if args.command in {"ingest", "search", "prepare", "answer"} and not selected_scope and not returned_review:
                    raise ValueError("Supply --scope or configure a company/product scope during setup")
                if args.command == "init":
                    result = {"workspace": str(store.root), "schema": 1, "fts5": True}
                elif args.command == "ingest":
                    if friendly_return:
                        result={"sme_review_applied":apply_sme_review(store,args.source)}
                    elif returned_review:
                        result = {"review_applied": apply_review(store, args.source)}
                    else:
                        result = import_source(store, args.source, selected_scope, args.submitter,
                                               review_format=args.review_format, **mapping)
                elif args.command == "change-review":
                    result = export_changes(store, args.ids, selected_scope, args.output, args.format)
                elif args.command == "apply-review":
                    result = apply_sme_review(store,args.source) if friendly_return else apply_review(store, args.source)
                elif args.command == "apply-sme-review":
                    result = apply_sme_review(store,args.source)
                elif args.command == "proposals":
                    result = [dict(r) for r in store.db.execute("SELECT * FROM proposals WHERE status=? ORDER BY id", (args.status,))]
                elif args.command in {"approve", "reject"}:
                    result = store.resolve(args.ids, args.actor, args.reason, args.command == "approve")
                elif args.command == "search":
                    result = store.retrieve(args.question, selected_scope)
                elif args.command == "prepare":
                    result = prepare(store,args.source,selected_scope,kb_offset=args.kb_offset,
                                     kb_limit=args.kb_limit,max_age_days=args.max_age_days,**mapping)
                elif args.command == "answer":
                    result = answer_rfp(store, args.source, selected_scope, args.config, args.max_age_days,
                                        evidence_map=args.evidence_map, **mapping)
                elif args.command == "feedback":
                    result = {"sme_review_applied":apply_sme_review(store,args.source)} if friendly_return else {"proposal_ids": ingest_feedback(store, args.source), "approved": False}
                elif args.command == "history":
                    result = [dict(r) for r in store.db.execute("SELECT * FROM revisions WHERE entry_id=? ORDER BY id", (args.entry,))]
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, sqlite3.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        if store:
            store.close()


if __name__ == "__main__":
    sys.exit(main())
