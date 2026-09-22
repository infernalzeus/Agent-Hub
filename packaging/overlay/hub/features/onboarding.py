"""Installer-only first-run and deferred capability setup.

Status reads never install software. Explicit requests start one serialized job;
the job survives browser navigation and reports failures without marking ready.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import threading
from urllib.parse import urlsplit

from aiohttp import web
from .. import locations as LOC, runtime as RT

routes = web.RouteTableDef()
FILE = RT.STATE / 'onboarding.json'
_task = None
_state_lock = threading.RLock()
_busy = asyncio.Lock()
CAPABILITIES = {
    'tailscale': ('Private device access', 'Install Tailscale, then sign in on this PC and every device using the same tailnet.'),
    'speech': ('TALK speech', 'Install isolated speech tools. Download only the model you select below.'),
    'mcp': ('PC control', 'Install CursorTouch Windows MCP and verify its tools. Control stays off until you enable it.'),
    'files': ('File Browser', 'Use the included read-only browser with a folder you choose.'),
    'media': ('Media Vault', 'Create media folders and install yt-dlp and ffmpeg in an isolated runtime.'),
    'smb': ('Shared drive', 'Connect through Windows so Agent Hub never receives or stores a password.'),
    'agents': ('Agents and ingested apps', 'Install Node.js, Git and OpenCode plus an isolated Python runtime for app ingestion.'),
    'projects': ('Project discovery', 'Scan a folder you select, review the results, then add only the repositories you want.'),
}


def state() -> dict:
    try:
        result = json.loads(FILE.read_text(encoding='utf-8'))
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def update(**values):
    with _state_lock:
        data = state()
        data.update(values)
        RT.write_json(FILE, data)
        return data


def result(capability, status, detail):
    with _state_lock:
        data = state()
        statuses = data.get('capabilities', {})
        statuses[capability] = {'status': status, 'detail': str(detail)[-5000:], 'at': time.time()}
        update(capabilities=statuses)


def install_media() -> tuple[bool, str]:
    ok, log = RT.install('media', ['yt-dlp', 'mutagen', 'imageio-ffmpeg', 'google-api-python-client',
                                 'google-auth-oauthlib', 'google-auth-httplib2'])
    if not ok:
        return ok, log
    if not shutil.which('node'):
        from .setup_actions import _run_winget
        ok, log = _run_winget('OpenJS.NodeJS.LTS')
        node_dir = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'nodejs'
        os.environ['PATH'] = str(node_dir) + os.pathsep + os.environ.get('PATH', '')
        if not shutil.which('node'):
            return False, 'Node.js is needed for YouTube signature checks. ' + log
    check = RT.run([str(RT.python_for('media')), '-c',
                    'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())'])
    if check.returncode:
        return False, check.stderr[-4000:]
    target = RT.STATE / 'runtimes/media/bin'
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(check.stdout.strip(), target / 'ffmpeg.exe')
    probe = RT.run([str(target / 'ffmpeg.exe'), '-version'], 20)
    if probe.returncode or not RT.modules_ready('media', ['yt_dlp', 'mutagen', 'googleapiclient', 'google_auth_oauthlib']):
        return False, 'Media runtime verification failed. Retry setup.'
    errors = LOC.save({k: LOC.get(k) for k in ('inbox', 'dl_audio', 'dl_video', 'outputs')})
    return not errors, str(errors) if errors else 'Media folders, yt-dlp and ffmpeg are ready.'


def install_mcp() -> tuple[bool, str]:
    from . import mcp
    ok, log = RT.install('mcp', ['windows-mcp'])
    if not ok:
        return ok, log
    cfg = mcp._read()
    # Preserve a deliberately configured provider on subsequent installer runs.
    cfg.setdefault('mcp', {}).setdefault('windows', {
        'type': 'local', 'enabled': False,
        'command': [str(RT.python_for('mcp').parent / 'windows-mcp.exe'), 'serve',
                    '--exclude-tools', 'PowerShell,Registry,FileSystem,Process'],
    })
    RT.write_json(mcp._cfg_path(), cfg)
    report = asyncio.run(mcp.probe('windows'))
    if not report.get('tools'):
        return False, 'Windows MCP started but returned no tools.'
    if set(report['tools']) & {'PowerShell', 'Registry', 'FileSystem', 'Process'}:
        return False, 'Provider did not respect the tool exclusions. PC control has not been enabled.'
    return True, 'Windows MCP answered: ' + ', '.join(report['tools']) + '. Enable control when needed in Locations.'


def _tailscale() -> str | None:
    path = LOC.get('tailscale_exe')
    return path if Path(path).is_file() else shutil.which('tailscale')


def connected() -> bool:
    exe = _tailscale()
    if not exe:
        return False
    try:
        status = json.loads(RT.run([exe, 'status', '--json'], 15).stdout)
        return status.get('BackendState') == 'Running'
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def install_one(capability: str, options: dict) -> tuple[str, str]:
    if capability == 'tailscale':
        if not _tailscale():
            from .setup_actions import _install_tailscale
            ok, log = _install_tailscale()
            if not ok and not _tailscale():
                return 'failed', log + '\nOfficial installer: https://tailscale.com/download/windows'
        return ('ready', 'Tailscale is connected. Use Enable private HTTPS for phone access.') if connected() else (
            'needs-input', 'Tailscale is installed. Open Tailscale from Start and sign in. Join the same tailnet on your phone, then Check connection.')
    if capability == 'speech':
        model = options.get('model', '')
        if model not in ('', 'tiny', 'base', 'small'):
            return 'failed', 'Choose tiny, base or small.'
        ok, log = RT.install('speech', ['faster-whisper', 'edge-tts'])
        if not ok:
            return 'failed', log
        if model:
            run = RT.run([str(RT.python_for('speech')), str(RT.ASSETS / 'packaging/speech_worker.py'),
                          'download', model, str(RT.STATE / 'models')], 1800)
            if run.returncode:
                return 'failed', run.stderr[-4000:]
            update(speech_model=model)
            return 'ready', model + ' speech model downloaded and loaded successfully.'
        return 'needs-input', 'Speech runtime installed. Choose a model and press Set up to download it.'
    if capability == 'mcp':
        ok, log = install_mcp()
        return ('ready' if ok else 'failed'), log
    if capability == 'files':
        root = str(options.get('file_root') or LOC.get('file_root')).strip()
        errors = LOC.save({'file_root': root})
        if errors:
            return 'failed', str(errors)
        return 'ready', 'File Browser is ready at ' + root
    if capability == 'media':
        ok, log = install_media()
        return ('ready' if ok else 'failed'), log
    if capability == 'agents':
        from .setup_actions import _run_winget, _install_opencode
        for exe, package in (('git', 'Git.Git'), ('npm', 'OpenJS.NodeJS.LTS')):
            if not shutil.which(exe):
                ok, log = _run_winget(package)
                if not ok:
                    return 'failed', log
        # Installers may update the registry PATH, but not this process environment.
        for folder in (Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'nodejs',
                       Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Git/cmd'):
            if folder.is_dir() and str(folder) not in os.environ.get('PATH', '').split(os.pathsep):
                os.environ['PATH'] += os.pathsep + str(folder)
        ok, log = _install_opencode()
        if not ok:
            return 'failed', log
        ok, log = RT.install('apps', ['aiohttp', 'pytest', 'pillow'])
        return ('ready' if ok else 'failed'), ('Agent runtime and app-ingestion Python ready. Connect your model provider in OpenCode.' if ok else log)
    if capability == 'smb':
        return 'needs-input', 'Enter a share such as \\server\\share, connect through Windows, then test and save it.'
    return 'needs-input', 'Choose a folder to scan, then select the repositories to add.'


async def _run_job(ids, options):
    async with _busy:
        update(job={'running': True, 'current': '', 'queue': ids})
        try:
            for capability in ids:
                update(job={'running': True, 'current': capability, 'queue': ids})
                result(capability, 'running', 'Setting up… You can keep using the Hub.')
                try:
                    status, detail = await asyncio.to_thread(install_one, capability, options)
                    if capability == 'files' and status == 'ready':
                        from .. import config, supervisor
                        running = supervisor.APP_PROCS.get('file-browser')
                        if running and running.running:
                            await supervisor.stop_app(running)
                        config.reload_apps()
                        supervisor.rebuild_app_procs()
                except Exception as exc:
                    status, detail = 'failed', str(exc)
                result(capability, status, detail)
        finally:
            update(job={'running': False, 'current': '', 'queue': []})


def start_job(ids, options):
    global _task
    if _task and not _task.done():
        raise web.HTTPConflict(text='Setup is already running. Wait for the current step to finish.')
    _task = asyncio.create_task(_run_job(ids, options))


async def body(request):
    try:
        value = await request.json()
    except (ValueError, TypeError):
        raise web.HTTPBadRequest(text='Send a JSON object.')
    if not isinstance(value, dict):
        raise web.HTTPBadRequest(text='Send a JSON object.')
    return value


@routes.get('/onboarding')
async def page(request):
    return web.Response(text=(RT.ASSETS / 'hub/static/onboarding.html').read_text(encoding='utf-8'), content_type='text/html')


@routes.get('/api/onboarding')
async def status(request):
    data = state()
    if data.get('job', {}).get('running') and (_task is None or _task.done()):
        data['job'] = {'running': False, 'interrupted': True}
        for item in data.get('capabilities', {}).values():
            if item.get('status') == 'running':
                item.update(status='failed', detail='Setup was interrupted. Retry this capability.')
    return web.json_response({**data, 'catalogue': CAPABILITIES, 'base': str(LOC.BASE), 'file_root': LOC.get('file_root'),
                              'smb_share': LOC.get('smb_share')})


@routes.post('/api/onboarding/choice')
async def choose(request):
    data = await body(request)
    mode = data.get('mode')
    if mode not in ('all', 'deferred'):
        raise web.HTTPBadRequest(text='Choose all or deferred.')
    if _task and not _task.done():
        raise web.HTTPConflict(text='Setup is already running.')
    update(mode=mode)
    if mode == 'all':
        start_job(list(CAPABILITIES), data)
    return web.json_response({'ok': True})


@routes.post('/api/onboarding/install/{capability}')
async def install_route(request):
    capability = request.match_info['capability']
    if capability not in CAPABILITIES:
        raise web.HTTPNotFound()
    data = await body(request)
    start_job([capability], data)
    return web.json_response({'ok': True}, status=202)


async def legacy_install(request):
    aliases = {'install-whisper': 'speech', 'install-mcp': 'mcp', 'install-tailscale': 'tailscale',
               'install-yt-deps': 'media', 'prepare-media': 'media'}
    capability = aliases.get(request.match_info['action_id'])
    if not capability:
        raise web.HTTPBadRequest(text='Open Setup tools to prepare this capability.')
    start_job([capability], {})
    return web.json_response({'ok': True, 'log': 'Setup started. Follow progress in Setup tools.'}, status=202)


@routes.post('/api/onboarding/tailscale/check')
async def check_tailscale(request):
    ok = await asyncio.to_thread(connected)
    result('tailscale', 'ready' if ok else 'needs-input', 'Connected.' if ok else 'Open Tailscale from Start and sign in.')
    return web.json_response({'ok': ok})


@routes.post('/api/onboarding/tailscale/https')
async def enable_https(request):
    if not await asyncio.to_thread(connected):
        raise web.HTTPBadRequest(text='Sign in to Tailscale first.')
    from ..config import PORT
    run = await asyncio.to_thread(RT.run, [_tailscale(), 'serve', '--bg', str(PORT)], 45)
    return web.json_response({'ok': run.returncode == 0, 'detail': (run.stdout + run.stderr)[-3000:]})


def scan(root: str) -> dict:
    path = Path(root)
    if not path.is_absolute() or not path.is_dir() or LOC._forbidden(path):
        raise ValueError('Choose an existing folder inside a drive.')
    found, visited, truncated = [], 0, False
    started = time.monotonic()
    for current, dirs, files in os.walk(path, followlinks=False):
        visited += 1
        if visited > 5000 or time.monotonic() - started > 20:
            truncated = True
            break
        here = Path(current)
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', 'venv', '__pycache__')
                   and not (here / d).is_symlink() and not (hasattr(os.path, 'isjunction') and os.path.isjunction(here / d))]
        if (here / '.git').exists():
            found.append(str(here.resolve()))
            dirs[:] = []
        elif len(here.relative_to(path).parts) >= 6:
            dirs[:] = []
    return {'paths': sorted(found, key=str.casefold), 'truncated': truncated}


@routes.post('/api/onboarding/projects/scan')
async def scan_projects(request):
    data = await body(request)
    try:
        found = await asyncio.to_thread(scan, str(data.get('root', '')))
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))
    return web.json_response(found)


@routes.post('/api/onboarding/projects/save')
async def save_projects(request):
    data = await body(request)
    selected = data.get('paths')
    if not isinstance(selected, list) or not selected or len(selected) > 500:
        raise web.HTTPBadRequest(text='Select 1–500 repositories.')
    existing = LOC.sources()
    seen = {os.path.normcase(str(Path(item['path']).resolve())) for item in existing}
    for value in selected:
        if not isinstance(value, str):
            raise web.HTTPBadRequest(text='Invalid project path.')
        path = Path(value)
        if not path.is_absolute() or not (path / '.git').exists():
            raise web.HTTPBadRequest(text='A selected folder is no longer a Git repository.')
        key = os.path.normcase(str(path.resolve()))
        if key not in seen:
            existing.append({'kind': 'project', 'path': str(path.resolve())})
            seen.add(key)
    errors = await asyncio.to_thread(LOC.save, {'project_sources': existing})
    if errors:
        raise web.HTTPBadRequest(text=str(errors))
    result('projects', 'ready', f'{len(existing)} project sources saved.')
    return web.json_response({'ok': True})


def share_path(value):
    value = str(value or '').strip()
    pieces = value[2:].split('\\') if value.startswith('\\\\') else []
    if len(pieces) < 2 or any(not p or p in ('.', '..') for p in pieces) or any(c in value for c in '\r\n"<>|?*') or ':' in value:
        raise ValueError('Enter a Windows share path such as \\\\server\\share.')
    return value


@routes.post('/api/onboarding/smb/{action}')
async def smb(request):
    data = await body(request)
    try:
        path = share_path(data.get('path'))
    except ValueError as exc:
        raise web.HTTPBadRequest(text=str(exc))
    action = request.match_info['action']
    if action == 'connect':
        # Native Explorer handles credentials. Nothing secret traverses this API.
        subprocess.Popen(['explorer.exe', path])
        return web.json_response({'ok': True, 'detail': 'Complete the connection in Windows, then Test and save.'})
    if action != 'save':
        raise web.HTTPNotFound()
    def test():
        with os.scandir(path) as entries:
            next(entries, None)
    try:
        await asyncio.wait_for(asyncio.to_thread(test), 12)
    except (OSError, asyncio.TimeoutError):
        raise web.HTTPBadRequest(text='Cannot read that share. Connect in Windows, then retry.')
    errors = await asyncio.to_thread(LOC.save, {'smb_share': path})
    if errors:
        raise web.HTTPBadRequest(text=str(errors))
    result('smb', 'ready', 'Shared drive is readable. Only its path was saved.')
    return web.json_response({'ok': True})


@web.middleware
async def middleware(request, handler):
    # Installer-only same-origin check for setup writes (including Explorer launches).
    if request.path.startswith('/api/onboarding') and request.method != 'GET':
        origin = request.headers.get('Origin')
        if origin and urlsplit(origin).netloc != request.host:
            raise web.HTTPForbidden(text='Open setup from Agent Hub itself.')
    if request.path == '/' and not state().get('mode'):
        raise web.HTTPFound('/onboarding')
    gates = {'/api/start/file-browser': 'files', '/api/voice/transcribe': 'speech',
             '/api/youtube-dl/download': 'media', '/api/youtube/upload': 'media', '/api/apps/ingest': 'agents', '/api/opencode/sessions': 'agents', '/api/missions': 'agents'}
    if request.path.startswith('/app/file-browser/') and state().get('capabilities', {}).get('files', {}).get('status') != 'ready':
        raise web.HTTPFound('/onboarding#files')
    capability = gates.get(request.path) if request.method == 'POST' else None
    if capability and state().get('capabilities', {}).get(capability, {}).get('status') != 'ready':
        return web.json_response({'error': 'Set up this tool first.', 'setup_url': '/onboarding#' + capability}, status=428)
    response = await handler(request)
    if isinstance(response, web.Response) and response.content_type == 'text/html' and request.path != '/onboarding':
        snippet = """<script>(()=>{const f=window.fetch;window.fetch=async(...a)=>{const r=await f(...a);if(r.status===428){try{const d=await r.clone().json();if(d.setup_url)location.href=d.setup_url}catch(e){}}return r}})();</script>"""
        response.text = response.text.replace('<head>', '<head>'+snippet, 1)
    return response
