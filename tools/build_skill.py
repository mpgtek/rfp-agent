#!/usr/bin/env python3
"""Package the maintained skill directory for manual installation."""
import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'plugins/rfp-agent/skills/rfp-agent'
EXCLUDED = {'__pycache__', '.venv', '.pytest_cache'}


def build(output):
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for path in sorted(SKILL.rglob('*')):
            if path.is_symlink():
                raise ValueError(f'Symlinks are not allowed: {path}')
            if path.is_file() and not any(p in EXCLUDED or p.endswith('.egg-info') for p in path.parts) and path.suffix not in {'.pyc', '.pyo'} and path.name != '.DS_Store':
                archive.write(path, 'rfp-agent/' + path.relative_to(SKILL).as_posix())
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert all(name.startswith('rfp-agent/') and '..' not in Path(name).parts for name in archive.namelist())
        assert 'rfp-agent/SKILL.md' in archive.namelist()
    print(f'{output}: {output.stat().st_size:,} bytes')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default=str(ROOT / 'dist/rfp-agent-skill.zip'))
    build(parser.parse_args().output)
