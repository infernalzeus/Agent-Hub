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
PRIVATE = {'choices.jsonl', 'choices.jsonl.1', 'local_settings.py', 'locations.json', 'apps.json', 'onboarding.json', 'provider_keys.json', 'cookies.txt', 'client_secrets.json', 'credentials', 'data', '__pycache__', '.git', 'ingested_apps', 'skills_compiled', 'skills_installed', 'logs',
           # state the hub writes beside itself when run from source: a
           # developer's own theme, automations and run history are theirs,
           # not something to ship to everyone who installs a build.
           'theme.json', 'support_missions.json', 'agent_events.json', 'model_outcomes.json', 'transition_selftest_result.json', 'update.json', 'automations.json', 'automation_runs.json',
           'integration_tokens.json', 'skill_topics_user.json', 'pending_move.json',
           'action_apps.json', 'proposals.json', 'user_facts.json', 'info_routines.json', 'decision_settings.json', 'commands_user.json', 'rea.json', 'app_evidence', 'models', 'utterance_decisions.jsonl', 'recording_draft.json'}
ROOT_FILES = ('app.py', 'favicon.png', 'favicon-64.png', 'favicon-256.png', 'favicon.ico', 'requirements-youtube.txt')
# Nothing is listed by hand for a NEW feature in hub/: if it is a file of a shipped kind it ships. But a file of a kind nobody has decided about, or a new top-level folder, used to be
# dropped without a word (a sound, a font, a model, a folder next to hub/). These two lists are the decisions already made; anything outside them stops the build with its name,
# so the choice (ship it: add it to EXTENSIONS or ROOT_FILES; leave it out: add it here) is made by a person, once, on purpose.
PRIVATE_CODE = {'skills_installed', 'skills_compiled', 'ingested_apps', 'local_settings.py'}      # code that is private on purpose: what a user installs or writes on their own machine
LEFT_OUT_KINDS = {'.ogg', '.wav', '.mp3', '.ttf', '.onnx', '.wasm', '.task', '.log', '.jsonl', '.sqlite', '.db', '.canvas', '.lock', '.toml', '.xml', '.pyc', '.pickle', ''}
KNOWN_TOP_LEVEL = {'hub', 'file-browser', 'youtube', 'packaging', 'tools', 'docs', 'release', 'data', 'logs', '__pycache__', 'app.py', 'conftest.py', 'requirements.txt', 'requirements-youtube.txt',
                   'favicon.png', 'favicon-64.png', 'favicon-256.png', 'favicon.ico', 'desktop.ini', 'Build-Release.cmd', 'release-evidence.json', 'README.md', 'SETUP.md', 'PLAN.md', 'STATE.md',
                   'PLAN_AND_STATE.md', 'hub-arch.canvas', 'hub-overview.canvas', 'hub-overview.svg', 'register-agenthub-protocol.reg', 'register-agenthub-protocol.reg.example',
                   'Agent Hub.vbs', 'Agent Hub.local.vbs', 'Agent Hub.local.vbs.example'}


def git_ignored(root: Path) -> "set[str]":
    """Files the repository itself ignores (the Hub writes its own state beside its code when run from source: dashboard layout, agent settings, generated skills).
    What the repo ignores the release ignores, so a new piece of personal state can never ride into an installer just because nobody added its name to PRIVATE.
    Empty when this is not a git checkout (the CI builds are clean checkouts, with nothing ignored to find)."""
    import subprocess
    try:
        out = subprocess.run(['git', 'ls-files', '--others', '--ignored', '--exclude-standard'], cwd=root, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return set()
    return {line.strip().replace(chr(92), '/') for line in out.stdout.splitlines() if line.strip()} if out.returncode == 0 else set()


def unshipped_surprises(root: Path) -> "list[str]":
    """What the staging above would leave out that nobody has decided about yet."""
    root = root.resolve()
    ignored_now = git_ignored(root)
    found = [f'top-level {p.name!r}: not shipped, and not on the list of things that are left out on purpose' for p in sorted(root.iterdir())
             if not p.name.startswith('.') and p.name not in KNOWN_TOP_LEVEL]
    for directory in ('hub', 'file-browser'):
        for source in sorted((root / directory).rglob('*')):
            relative = source.relative_to(root)
            if not source.is_file() or source.is_symlink() or '__pycache__' in relative.parts or relative.as_posix() in ignored_now:
                continue
            if any(part in PRIVATE or part.startswith('.') for part in relative.parts):
                if source.suffix.lower() == '.py' and not any(part in PRIVATE_CODE for part in relative.parts):
                    found.append(f'{relative.as_posix()}: Python code inside a folder or file name that is treated as private, so it would not ship')
                continue
            if source.suffix.lower() not in EXTENSIONS and source.suffix.lower() not in LEFT_OUT_KINDS:
                found.append(f'{relative.as_posix()}: a {source.suffix.lower() or "no-extension"} file; its kind is neither shipped nor on the left-out list')
    return found


def stage(root: Path, destination: Path, packaging: Path | None = None):
    root, destination = root.resolve(), destination.resolve()
    packaging = packaging or root / 'packaging'
    if destination == root or destination in root.parents:
        raise ValueError('Stage must not be the source tree or its parent.')
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Use a new, empty staging directory; existing data is never deleted.')
    ignored = git_ignored(root)
    surprises = unshipped_surprises(root)
    if surprises:
        raise ValueError('The release would silently leave these out. Decide for each: ship it (EXTENSIONS / ROOT_FILES in stage_release.py) or leave it out on purpose '
                         '(LEFT_OUT_KINDS / KNOWN_TOP_LEVEL).\n  ' + '\n  '.join(surprises[:40]))
    destination.mkdir(parents=True, exist_ok=True)
    for name in ROOT_FILES:
        shutil.copy2(root / name, destination / name)
    for directory in ('hub', 'file-browser'):
        for source in (root / directory).rglob('*'):
            relative = source.relative_to(root)
            if not source.is_file() or source.is_symlink() or source.suffix.lower() not in EXTENSIONS:
                continue
            if any(part in PRIVATE or part.startswith('.') for part in relative.parts) or relative.as_posix() in ignored:
                continue
            # Local Python settings examples are documentation, not release config.
            if source.name.startswith('local_settings'):
                continue
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    # Record the skills THIS build ships, so an installed Hub can tell them from the
    # ones its user wrote and move the user's somewhere an uninstall cannot reach.
    shipped = destination / 'hub' / 'agent_knowledge' / 'skills'
    if shipped.is_dir():
        names = sorted(p.name for p in shipped.iterdir() if p.is_dir())
        (shipped / '.shipped').write_text('\n'.join(names) + '\n', encoding='utf-8')
    (destination / 'youtube').mkdir()
    for name in ('ytdl.py', 'yt_upload.py'):
        shutil.copy2(root / 'youtube' / name, destination / 'youtube' / name)
    # Packaging scripts the frozen app runs as children, outside the app allowlist.
    (destination / 'packaging').mkdir(parents=True, exist_ok=True)
    for name in ('agenthub_launcher.py', 'speech_worker.py', 'vision_worker.py'):
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
