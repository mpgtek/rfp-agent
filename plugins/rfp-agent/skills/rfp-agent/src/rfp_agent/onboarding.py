"""Persist company/workspace selection; expose the next conversational step."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import uuid

from .db import Store, now


def state_directory():
    override = os.environ.get("RFP_AGENT_STATE_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "rfp-agent"
    if sys.platform == "darwin":
        default = Path.home() / "Library/Application Support/rfp-agent"
    else:
        default = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "rfp-agent"
    fallback = Path.home() / "Documents/Codex/rfp-agent-runtime"
    if (fallback / "settings.json").is_file():
        try:
            if not (default / "settings.json").is_file():
                return fallback
        except PermissionError:
            return fallback
    return default


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".new")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp.replace(path)


def default_workspace():
    """Use the new location, preserving existing installations at the old path."""
    home = Path.home()
    current = home / "Documents" / "rfp-agent" / "rfp-kb-store"
    legacy = home / "Documents" / "Codex" / "rfp-agent" / "rfp-kb-store"
    # A partially present workspace must not be mistaken for a new installation.
    if current.exists():
        return current.resolve()
    if legacy.exists():
        return legacy.resolve()
    return current.resolve()


def active_workspace():
    # Explicit state selection remains an opt-in for isolated tests/deployments.
    # Normal sessions resolve the fixed store without needing a registry first.
    if os.environ.get("RFP_AGENT_STATE_DIR"):
        selected = read_json(state_directory() / "settings.json").get("active_workspace")
        if selected:
            return selected
    return str(default_workspace())


def configure(workspace, company=None, scope=None, sources=None, defer_sources=False):
    workspace = Path(workspace).expanduser().resolve()
    old = read_json(workspace / "onboarding.json")
    company = (company or old.get("company") or "").strip()
    if not company:
        raise ValueError("Company name is required for first-time setup")
    if old.get("company") and company.casefold() != old["company"].casefold():
        raise ValueError("This workspace belongs to another company; choose a separate workspace")
    scope = (scope or old.get("scope") or re.sub(r"[^\w]+", "-", company.casefold()).strip("-")).strip()
    if not scope:
        raise ValueError("A nonempty product/environment scope is required")
    selected = list(old.get("source_paths", []))
    for source in sources or []:
        path = Path(source).expanduser().resolve()
        if not path.exists():
            raise ValueError(f"Source does not exist: {path}")
        inputs = workspace / "inputs"
        in_inputs = path == inputs or inputs in path.parents
        if (path == workspace or workspace in path.parents or (path.is_dir() and path in workspace.parents)) and not in_inputs:
            raise ValueError("Select original source inputs outside the managed workspace, or use its inputs folder")
        if str(path) not in selected:
            selected.append(str(path))
    # Existing unregistered workspaces may be adopted without changing their data,
    # but their current scopes must agree with the explicitly chosen scope.
    existing_db = workspace / "knowledge.sqlite3"
    if existing_db.exists():
        con = sqlite3.connect(existing_db.as_uri() + "?mode=ro", uri=True)
        try:
            scopes = {r[0] for r in con.execute("SELECT scope FROM entries UNION SELECT scope FROM proposals")}
            if scopes and scope not in scopes:
                raise ValueError("Existing KB uses another scope; specify its current scope or a new workspace")
        finally:
            con.close()
    store = Store(workspace)
    store.close()
    for folder in ("inputs", "reviews"):
        (workspace / folder).mkdir(exist_ok=True)
    config = dict(old, schema=1, company=company, scope=scope, workspace=str(workspace),
                  source_paths=selected, profile_needed=bool(defer_sources and not selected), updated_at=now())
    config.setdefault("created_at", now())
    write_json(workspace / "onboarding.json", config)
    settings_path = state_directory() / "settings.json"
    settings = read_json(settings_path)
    known = list(settings.get("workspaces", []))
    if str(workspace) not in known:
        known.append(str(workspace))
    write_json(settings_path, dict(settings, schema=1, active_workspace=str(workspace), workspaces=known))
    return status(workspace)


def status(workspace=None):
    chosen = workspace or active_workspace()
    if not chosen:
        return {"configured": False, "next_step": "choose_company_workspace",
                "prompt": "Which company/product is this for, and where should its persistent workspace be stored?"}
    workspace = Path(chosen).expanduser().resolve()
    config = read_json(workspace / "onboarding.json")
    if not config:
        return {"configured": False, "workspace": str(workspace), "next_step": "choose_company_workspace",
                "prompt": "Confirm the company/product and scope. Its KB uses this known folder; no location selection is needed."}
    db = workspace / "knowledge.sqlite3"
    if not db.exists():
        raise ValueError("Saved workspace database is missing; restore it or explicitly choose a new workspace")
    con = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        approved = con.execute("SELECT COUNT(*) FROM entries WHERE scope=? AND head IS NOT NULL", (config['scope'],)).fetchone()[0]
        pending_rows = con.execute("SELECT provenance FROM proposals WHERE scope=? AND status='pending'", (config['scope'],)).fetchall()
        runs = con.execute("SELECT manifest FROM runs").fetchall()
        run_count = sum(json.loads(r[0]).get('scope') == config['scope'] for r in runs)
        feedback_pending = any(json.loads(r[0]).get('run_id') for r in pending_rows)
    finally:
        con.close()
    if feedback_pending:
        step, prompt = "review_feedback", "Review the staged SME corrections and approve the selected changes before reusing them."
    elif pending_rows:
        step, prompt = "review_kb", "Review pending collisions or complete the unanswered backlog. New source Q&A is already usable; the backlog need not block an RFP."
    elif approved and run_count:
        step, prompt = "review_rfp", "Review the completed RFP and SME workbook; return explicit corrections or provide the next RFP."
    elif approved:
        step, prompt = "provide_rfp", "Provide an XLSX RFP and identify its response column if the layout is ambiguous."
    elif config.get('source_paths'):
        step, prompt = "prepare_and_ingest", "Import the selected source Q&A with provenance; only changed existing answers require review."
    elif config.get('profile_needed'):
        step, prompt = "describe_application", "Describe the application, cloud infrastructure, security and BCDR so we can draft a company profile first."
    else:
        step, prompt = "provide_sources", "Provide existing Q&A files, architecture/security documents or prior RFPs, or choose to describe the application first."
    return {"configured": True, "company": config['company'], "scope": config['scope'],
            "workspace": str(workspace), "database": str(db), "source_paths": config['source_paths'],
            "counts": {"approved_answers": approved, "pending_proposals": len(pending_rows), "rfp_runs": run_count},
            "can_answer_rfp": bool(approved), "next_step": step, "prompt": prompt}
