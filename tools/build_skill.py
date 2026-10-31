#!/usr/bin/env python3
"""Build the small installable skill; leave development files in the repository."""
import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = ('agents', 'scripts', 'src', 'references')
FILES = ('SKILL.md', 'pyproject.toml', 'LICENSE', 'PRIVACY.md', 'TERMS.md', 'BRIDGE.md')
EXCLUDED = {'__pycache__', '.venv', '.pytest_cache'}


def build(output):
    output = Path(output).resolve()
    paths = [ROOT / name for name in FILES]
    for name in DIRECTORIES:
        paths.extend(p for p in (ROOT / name).rglob('*') if p.is_file()
                     and not any(part in EXCLUDED or part.endswith('.egg-info') for part in p.parts)
                     and p.suffix not in {'.pyc', '.pyo'} and p.name != '.DS_Store')
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for path in sorted(paths):
            if path.is_symlink():
                raise ValueError(f'Symlinks are not allowed: {path}')
            archive.write(path, 'rfp-agent/' + path.relative_to(ROOT).as_posix())
        archive.write(ROOT / 'INSTALL.md', 'rfp-agent/README.md')
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        names = archive.namelist()
        assert all(name.startswith('rfp-agent/') and '..' not in Path(name).parts for name in names)
        assert not any(part in {'tests', 'examples', '.git', '.github', 'tools'} for name in names for part in Path(name).parts)
    print(f'{output}: {len(names)} files, {output.stat().st_size:,} bytes')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default=str(ROOT / 'dist/rfp-agent-skill.zip'))
    build(parser.parse_args().output)
