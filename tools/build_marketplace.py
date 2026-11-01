#!/usr/bin/env python3
"""Build the OpenAI marketplace bundle from the same small installation package."""
import argparse
import json
from pathlib import Path
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED
from build_skill import build

ROOT = Path(__file__).resolve().parents[1]


def marketplace(output=None):
    manifest = json.loads((ROOT / 'marketplace/plugin.json').read_text())
    output = Path(output or ROOT / f'dist/rfp-agent-plugin-{manifest["version"]}.zip').resolve()
    interface = manifest['extensions']['com.openai']['interface']
    assert manifest['extensions']['com.openai']['requires_local_executor'] is True
    assert 'apps' not in manifest and 'apps' not in manifest['extensions']['com.openai']
    assert len(interface['displayName']) <= 30 and len(interface['shortDescription']) <= 30
    assert len(interface['longDescription']) <= 4000
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='rfp-marketplace-build-') as temporary:
        skill_zip = build(Path(temporary) / 'skill.zip')
        with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
            archive.write(ROOT / 'marketplace/plugin.json', 'plugin.json')
            for field in {'logo', 'composerIcon'}:
                relative = interface[field].removeprefix('./')
                source = (ROOT / 'marketplace' / relative).resolve()
                assert source.is_relative_to((ROOT / 'marketplace').resolve()) and source.is_file()
                if relative not in archive.namelist():
                    archive.write(source, relative)
            with ZipFile(skill_zip) as skill:
                for entry in skill.infolist():
                    archive.writestr('skills/' + entry.filename, skill.read(entry.filename))
            for name in ['LICENSE', 'PRIVACY.md', 'TERMS.md']:
                archive.write(ROOT / name, name)
            archive.writestr('README.md', '# RFP Agent marketplace package\n\n'
                             'Source and documentation: https://github.com/mpgtek/rfp-agent\n'
                             'Local desktop execution; company data stays outside the plugin.\n'
                             'See the included skill instructions, privacy policy, terms and MIT License.\n')
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert archive.read('plugin.json') == (ROOT / 'marketplace/plugin.json').read_bytes()
        assert all(not entry.startswith('/') and '..' not in Path(entry).parts for entry in archive.namelist())
        assert not any(part in {'tests', 'examples', '.git', '.github', '__pycache__', 'tools'}
                       for name in archive.namelist() for part in Path(name).parts)
    print(f'{output}: {len(archive.namelist())} files, {output.stat().st_size:,} bytes')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output')
    marketplace(parser.parse_args().output)
