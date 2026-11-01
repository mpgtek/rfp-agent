#!/usr/bin/env python3
"""Package the maintained shared plugin directory."""
import argparse
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins/rfp-agent'
EXCLUDED = {'__pycache__', '.venv', '.pytest_cache'}


def marketplace(output=None):
    manifest = json.loads((PLUGIN / 'plugin.json').read_text(encoding='utf-8'))
    claude = json.loads((PLUGIN / '.claude-plugin/plugin.json').read_text(encoding='utf-8'))
    assert (manifest['name'], manifest['version']) == (claude['name'], claude['version'])
    for name in ('LICENSE', 'PRIVACY.md', 'TERMS.md'):
        assert (ROOT / name).read_bytes() == (PLUGIN / name).read_bytes() == (PLUGIN / 'skills/rfp-agent' / name).read_bytes(), f'{name} copies differ'
    output = Path(output or ROOT / f'dist/rfp-agent-plugin-{manifest["version"]}.zip').resolve()
    interface = manifest['extensions']['com.openai']['interface']
    assert len(interface['shortDescription']) <= 30
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for path in sorted(PLUGIN.rglob('*')):
            if path.is_symlink():
                raise ValueError(f'Symlinks are not allowed: {path}')
            if path.is_file() and not any(p in EXCLUDED or p.endswith('.egg-info') for p in path.parts) and path.suffix not in {'.pyc', '.pyo'} and path.name != '.DS_Store':
                archive.write(path, path.relative_to(PLUGIN).as_posix())
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert {'plugin.json', '.claude-plugin/plugin.json', 'skills/rfp-agent/SKILL.md'} <= set(archive.namelist())
        assert not any(part in {'tests', 'examples', '.git', '.github', 'tools'} for name in archive.namelist() for part in Path(name).parts)
    print(f'{output}: {output.stat().st_size:,} bytes')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output')
    marketplace(parser.parse_args().output)
