"""Stage an allowlisted release tree; never edit live Hub files.

The Hub itself decides how to behave when installed (see hub/runtime.py:
PACKAGED/STATE/python_for), so staging is a straight copy plus a privacy
audit. Nothing here patches source, so editing the Hub cannot stale the
build, and new modules or skills are picked up with no manifest to update.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
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
    # Packaging scripts the frozen app runs as children, outside the app allowlist.
    (destination / 'packaging').mkdir(parents=True, exist_ok=True)
    for name in ('agenthub_launcher.py', 'speech_worker.py'):
        shutil.copy2(packaging / name, destination / 'packaging' / name)
    # Bundled payloads (wheels, the Python installer). Copied in rather than
    # referenced, so the staged tree is exactly what gets frozen and the tests
    # exercise the same lookup the installed Hub will do.
    if (packaging / 'payloads').is_dir():
        shutil.copytree(packaging / 'payloads', destination / 'payloads',
                        ignore=shutil.ignore_patterns('*.part'))
        shutil.copy2(packaging / 'payloads.json', destination / 'payloads' / 'payloads.json')
    audit(destination)
    return destination


# A user profile, or any drive other than the system one, is this machine's layout.
# C:\Program Files and C:\Windows are legitimate defaults and stay allowed.
# The lookbehind keeps URL schemes out of it: the "s:/" inside "https://" is not a drive.
_MACHINE_PATH = re.compile(r'(?<![A-Za-z])(?:[D-Zd-z]:[\\/]|[Cc]:[\\/]Users[\\/])')


def _denied_values() -> list[str]:
    """Machine-specific strings to reject — a PIN, an account tag, a hostname.

    Deliberately NOT literals in this file: it is public, so a denylist written
    here would publish exactly what it exists to keep out. One value per line in
    packaging/release-deny.local.txt (gitignored), and/or AGENTHUB_RELEASE_DENY
    as a ';'-separated list.
    """
    values = []
    local = Path(__file__).resolve().parent / 'release-deny.local.txt'
    if local.is_file():
        values += [line.strip() for line in local.read_text(encoding='utf-8').splitlines()
                   if line.strip() and not line.startswith('#')]
    values += [v.strip() for v in os.environ.get('AGENTHUB_RELEASE_DENY', '').split(';') if v.strip()]
    return values


def audit(destination: Path):
    for path in destination.rglob('*'):
        if path.is_file() and (any(part in PRIVATE for part in path.relative_to(destination).parts)
                               or path.suffix.lower() in {'.pickle', '.sqlite', '.db', '.log', '.pyc'}):
            raise ValueError('Private/generated file in release: ' + str(path))
    manifests = json.loads((destination / 'hub/apps.default.json').read_text(encoding='utf-8'))
    if [item['id'] for item in manifests] != ['file-browser']:
        raise ValueError('Release must start with only the packaged File Browser.')
    denied = _denied_values()
    for name in ('hub/config.py', 'hub/locations.py', 'hub/apps.default.json'):
        contents = (destination / name).read_text(encoding='utf-8')
        found = _MACHINE_PATH.search(contents)
        if found:
            raise ValueError('Absolute machine path in release configuration: ' + name
                             + ' (' + found.group(0) + ')')
        # Never name the offending value: this runs into build logs.
        if any(value in contents for value in denied):
            raise ValueError('Denied machine-specific value in release configuration: ' + name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--packaging', type=Path)
    args = parser.parse_args()
    print(stage(args.root, args.destination, args.packaging))
