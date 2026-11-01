#!/usr/bin/env python3
"""Check the assembled marketplace ZIP without touching a company workspace."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
version = json.loads((ROOT / 'marketplace/plugin.json').read_text())['version']
archive = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / f'dist/rfp-agent-plugin-{version}.zip'
with tempfile.TemporaryDirectory(prefix='rfp-marketplace-check-') as temporary:
    root = Path(temporary)
    with ZipFile(archive) as zipped:
        assert zipped.testzip() is None
        assert all(not name.startswith('/') and '..' not in Path(name).parts for name in zipped.namelist())
        zipped.extractall(root / 'plugin')
    plugin = root / 'plugin'
    skill = plugin / 'skills/rfp-agent'
    assert not (skill / 'examples').exists() and not (skill / 'tests').exists()
    env = dict(os.environ, HOME=str(root / 'home'), USERPROFILE=str(root / 'home'),
               RFP_AGENT_STATE_DIR=str(root / 'state'), PYTHONPATH=str(skill / 'src'))
    def run(*args):
        result = subprocess.run([sys.executable, *map(str, args)], cwd=root, env=env,
                                capture_output=True, text=True, check=True, timeout=60)
        return result.stdout
    run('-S', skill / 'scripts/discover_workspace.py')
    run(skill / 'scripts/bootstrap.py', '--offline', '--state-dir', root / 'state')
    run('-c', '''from pathlib import Path
import sys
from rfp_agent.db import Store
for location in [Path(sys.argv[1]),Path(sys.argv[1])/'bad-kb']:
    try: Store(location)
    except ValueError: pass
    else: raise AssertionError('KB permitted inside plugin')
''', plugin)
    rejected = subprocess.run([sys.executable, str(skill / 'scripts/bootstrap.py'), '--offline',
                               '--state-dir', str(plugin / 'bad-runtime')], cwd=root, env=env,
                              capture_output=True, text=True, timeout=60)
    assert rejected.returncode != 0 and 'outside' in rejected.stdout + rejected.stderr
    run('-m', 'rfp_agent', '--workspace', root / 'demo', 'demo')
    assert (root / 'demo/demo-result.json').is_file()
    assert not list(plugin.rglob('*.sqlite3'))
print('Marketplace ZIP passed: isolated setup, synthetic workflow and plugin-root data/runtime protection.')
