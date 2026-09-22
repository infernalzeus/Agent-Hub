"""Stage an allowlisted, hash-checked release tree; never edit live Hub files."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil

EXTENSIONS = {'.py', '.json', '.js', '.css', '.html', '.md', '.txt', '.png', '.svg', '.jpg', '.jpeg', '.ico', '.pdf', '.zip', '.gz', '.yaml', '.yml', '.sh', '.ts', '.tsx', '.cjs', '.mjs'}
PRIVATE = {'local_settings.py', 'locations.json', 'apps.json', 'onboarding.json', 'cookies.txt', 'client_secrets.json', 'credentials', 'data', '__pycache__', '.git', 'ingested_apps', 'skills_compiled', 'logs'}
ROOT_FILES = ('app.py', 'favicon.png', 'favicon-64.png', 'favicon-256.png', 'favicon.ico', 'requirements-youtube.txt')


def stage(root: Path, destination: Path, packaging: Path | None = None):
    root, destination = root.resolve(), destination.resolve()
    packaging = packaging or root / 'packaging'
    if destination == root or destination in root.parents:
        raise ValueError('Stage must not be the source tree or its parent.')
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Use a new, empty staging directory; existing data is never deleted.')
    changes = json.loads((packaging / 'release-changes.json').read_text(encoding='utf-8'))
    for item in changes['files']:
        source = root / item['path']
        if hashlib.sha256(source.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Release overlay is stale: ' + item['path'] + '. Review and refresh it before rebuilding.')
    destination.mkdir(parents=True, exist_ok=True)
    for name in ROOT_FILES:
        shutil.copy2(root / name, destination / name)
    for directory in ('hub', 'file-browser'):
        for source in (root / directory).rglob('*'):
            relative = source.relative_to(root)
            if not source.is_file() or source.is_symlink() or source.suffix.lower() not in EXTENSIONS:
                continue
            if any(part in PRIVATE or part.startswith('.') for part in relative.parts):
                continue
            # Local Python settings examples are documentation, not release config.
            if source.name.startswith('local_settings'):
                continue
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    (destination / 'youtube').mkdir()
    for name in ('ytdl.py', 'yt_upload.py'):
        shutil.copy2(root / 'youtube' / name, destination / 'youtube' / name)
    for item in changes['files']:
        path = destination / item['path']
        # Packaging entrypoint is copied explicitly, outside the application allowlist.
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / item['path'], path)
        lines = path.read_text(encoding='utf-8').splitlines(keepends=True)
        for edit in reversed(item['edits']):
            lines[edit['start']:edit['end']] = edit['replacement'].splitlines(keepends=True)
        path.write_text(''.join(lines), encoding='utf-8')
    for source in (packaging / 'overlay').rglob('*'):
        if source.is_file():
            target = destination / source.relative_to(packaging / 'overlay')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    audit(destination)
    return destination


def audit(destination: Path):
    for path in destination.rglob('*'):
        if path.is_file() and (any(part in PRIVATE for part in path.relative_to(destination).parts)
                               or path.suffix.lower() in {'.pickle', '.sqlite', '.db', '.log', '.pyc'}):
            raise ValueError('Private/generated file in release: ' + str(path))
    manifests = json.loads((destination / 'hub/apps.default.json').read_text(encoding='utf-8'))
    if [item['id'] for item in manifests] != ['file-browser']:
        raise ValueError('Release must start with only the packaged File Browser.')
    for name in ('hub/config.py', 'hub/locations.py', 'hub/apps.default.json'):
        contents = (destination / name).read_text(encoding='utf-8')
        if any(value in contents for value in ('N:\\', 'Z:\\', 'IZ17-G', '9274')):
            raise ValueError('Machine-specific value in release configuration: ' + name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--packaging', type=Path)
    args = parser.parse_args()
    print(stage(args.root, args.destination, args.packaging))
