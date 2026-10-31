#!/usr/bin/env python3
"""Read saved company/KB metadata before optional libraries or runtime setup."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from rfp_agent.onboarding import state_directory, status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", help="Explicit saved workspace, if its registry was moved")
    args = parser.parse_args()
    try:
        result = {"state_dir": str(state_directory()), "onboarding": status(args.workspace)}
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({"configured": None, "next_step": "restore_workspace_access",
                          "error": str(exc), "create_new_workspace": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
