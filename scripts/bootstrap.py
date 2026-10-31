#!/usr/bin/env python3
"""First-invocation runtime setup. Standard library only; no company data required."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv


ROOT = Path(__file__).resolve().parents[1]


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


PROBE = r'''
import importlib.metadata, json, sqlite3, sys
result={"python":sys.version.split()[0],"sqlite":sqlite3.sqlite_version,"fts5":False,"dependencies":{},"missing":[]}
try:
 c=sqlite3.connect(":memory:"); c.execute("CREATE VIRTUAL TABLE probe USING fts5(text)"); c.close(); result["fts5"]=True
except sqlite3.Error:
 pass
for dist, module, low, upper in [("openpyxl","openpyxl",(3,1),4),("python-docx","docx",(1,1),2),("lxml","lxml",(4,9),7)]:
 try:
  version=importlib.metadata.version(dist); parts=tuple(int(x) for x in version.split(".")[:2]); __import__(module)
  if parts<low or parts[0]>=upper: raise ValueError("unsupported version")
  result["dependencies"][dist]=version
 except Exception:
  result["missing"].append(dist)
print(json.dumps(result))
'''


def probe(python):
    process = subprocess.run([str(python), "-c", PROBE], capture_output=True, text=True, timeout=60)
    if process.returncode:
        raise RuntimeError("Could not inspect the Python runtime")
    return json.loads(process.stdout)


def bootstrap(state_dir=None, offline=False):
    if sys.version_info < (3, 11):
        raise RuntimeError("Python 3.11 or newer is required to initialize this skill")
    state = Path(state_dir).expanduser().resolve() if state_dir else state_directory().resolve()
    protected = ROOT.parent.parent if ROOT.parent.name == "skills" and (ROOT.parent.parent / "plugin.json").is_file() else ROOT
    if state == protected or protected in state.parents:
        raise ValueError("Runtime/state directory must be outside the skill directory")
    state.mkdir(parents=True, exist_ok=True)
    runtime = state / "runtime"
    python = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        # Reuse already available compatible host libraries; missing/incompatible
        # libraries are installed into this venv, never into the host environment.
        venv.EnvBuilder(with_pip=True, system_site_packages=True).create(runtime)
    inspected = probe(python)
    runtime_mode = "managed-venv"
    # A prior session may have created this venv with a different Python.
    # Reuse an already-compatible current interpreter before trying downloads.
    if (inspected["missing"] or not inspected["fts5"]) and python.resolve() != Path(sys.executable).resolve():
        host = probe(sys.executable)
        if host["fts5"] and not host["missing"]:
            python, inspected, runtime_mode = Path(sys.executable), host, "compatible-host"
    if not inspected["fts5"]:
        raise RuntimeError("This Python lacks SQLite FTS5; choose a Python build that includes FTS5")
    installed = []
    if inspected["missing"]:
        if offline:
            raise RuntimeError("Offline setup needs these libraries preinstalled: " + ", ".join(inspected["missing"]))
        requirements = {"openpyxl": "openpyxl>=3.1,<4", "python-docx": "python-docx>=1.1,<2", "lxml": "lxml>=4.9,<7"}
        wanted = [requirements[name] for name in inspected["missing"]]
        result = subprocess.run([str(python), "-m", "pip", "install", "--disable-pip-version-check", *wanted],
                                capture_output=True, text=True, timeout=300)
        if result.returncode:
            raise RuntimeError("Dependency installation failed. Check package-index/network access and retry setup; no company KB was created")
        installed = wanted
    inspected = probe(python)
    if inspected["missing"] or not inspected["fts5"]:
        raise RuntimeError("Runtime verification failed; setup is incomplete")
    launcher = state / "run.py"
    launcher.write_text("import runpy, sys, os\nos.environ.setdefault('RFP_AGENT_STATE_DIR', " + repr(str(state)) + ")\n"
                        "sys.path.insert(0, " + repr(str(ROOT / "src")) + ")\n"
                        "runpy.run_module('rfp_agent', run_name='__main__')\n", encoding="utf-8")
    runtime_state = {"schema": 1, "ready": True, "state_dir": str(state), "skill_root": str(ROOT),
        "python": str(python), "launcher": str(launcher), "environment": inspected,
        "installed_this_run": installed, "runtime_mode": runtime_mode}
    temp = state / "runtime.json.new"
    temp.write_text(json.dumps(runtime_state, indent=2), encoding="utf-8")
    temp.replace(state / "runtime.json")
    env = dict(os.environ, RFP_AGENT_STATE_DIR=str(state))
    status = subprocess.run([str(python), str(launcher), "onboarding-status"], capture_output=True,
                            text=True, env=env, timeout=60)
    if status.returncode:
        raise RuntimeError("Runtime is ready but onboarding state could not be read; check the saved workspace configuration")
    runtime_state["onboarding"] = json.loads(status.stdout)
    runtime_state["run_command"] = [str(python), str(launcher)]
    return runtime_state


def main():
    parser = argparse.ArgumentParser(description="Automatically prepare the RFP skill runtime")
    parser.add_argument("--state-dir", help="Optional runtime/settings directory outside the installed skill")
    parser.add_argument("--offline", action="store_true", help="Reuse installed dependencies without package downloads")
    args = parser.parse_args()
    try:
        if sys.version_info < (3, 11):
            for name in ("python3.13", "python3.12", "python3.11", "python3"):
                candidate = shutil.which(name)
                if candidate and Path(candidate).resolve() != Path(sys.executable).resolve():
                    check = subprocess.run([candidate, "-c", "import sys; sys.exit(sys.version_info < (3,11))"], capture_output=True)
                    if check.returncode == 0:
                        return subprocess.run([candidate, str(Path(__file__).resolve()), *sys.argv[1:]]).returncode
            raise RuntimeError("Python 3.11+ is not available. Install a supported Python runtime; setup can then install the required libraries automatically")
        print(json.dumps(bootstrap(args.state_dir, args.offline), indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"ready": False, "error": str(exc), "next_step": "resolve_setup_issue"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
