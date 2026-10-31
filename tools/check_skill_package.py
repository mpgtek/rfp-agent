#!/usr/bin/env python3
"""Exercise the actual installation ZIP in an isolated workspace without examples."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
archive = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'dist/rfp-agent-skill.zip'
with tempfile.TemporaryDirectory(prefix='rfp-skill-package-') as temporary:
    root = Path(temporary)
    with ZipFile(archive) as zipped:
        assert zipped.testzip() is None
        assert all(name.startswith('rfp-agent/') and '..' not in Path(name).parts for name in zipped.namelist())
        zipped.extractall(root)
    skill = root / 'rfp-agent'
    assert not (skill / 'examples').exists() and not (skill / 'tests').exists()
    env = dict(os.environ, HOME=str(root / 'home'), USERPROFILE=str(root / 'home'),
               RFP_AGENT_STATE_DIR=str(root / 'state'), PYTHONPATH=str(skill / 'src'))
    def run(*args):
        result = subprocess.run([sys.executable, *args], cwd=root, env=env,
                                capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    discovery = run('-S', str(skill / 'scripts/discover_workspace.py'))
    run(str(skill / 'scripts/bootstrap.py'), '--offline', '--state-dir', str(root / 'state'))
    run('-m', 'rfp_agent', 'fixtures', str(root / 'generated-fixtures'))
    assert (root / 'generated-fixtures/knowledge.xlsx').is_file()
    run('-m', 'rfp_agent', '--workspace', str(root / 'demo-workspace'), 'demo')
    assert (root / 'demo-workspace/demo-result.json').is_file()
    assert not list(skill.rglob('*.sqlite3'))
    print('Installation ZIP passed: isolated discovery, offline setup, generated fixtures and full synthetic workflow; no examples folder needed.')
