"""Optional hand-tracking assets. Download only after an explicit install request."""
from __future__ import annotations
import asyncio
import base64
import hashlib
import json
import re
import shutil
import tarfile
import tempfile
import threading
import urllib.request
from pathlib import Path
from aiohttp import web
from .runtime import STATE

VERSION = '1.2.2'
ARCHIVE = 'https://registry.npmjs.org/@mediapipe/tasks-vision/-/tasks-vision-1.2.2.tgz'
INTEGRITY = 'Z7BikxnTvlKgc3d/Nw+LV6B0xyAACxYeAHHUu/xUhm1SV7jlExa9M37beiF/wZFoy0H+cs1PlIT2Z4km02UEHQ=='
MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'
MODEL_SIZE = 7_819_105
MODEL_SHA256 = 'fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1'      # pinned from the file the first approved download produced; the model host serves no checksum of its own
DIRECTORY = STATE / 'models' / 'hands' / VERSION
ALLOWED = re.compile(r'(?:vision_bundle\.mjs|wasm/[a-z0-9_]+\.(?:js|wasm)|hand_landmarker\.task|LICENSE|NOTICE)\Z')
_lock = threading.Lock()
routes = web.RouteTableDef()


def status():
    try:
        manifest = json.loads((DIRECTORY / 'manifest.json').read_text(encoding='utf-8'))
        ready = manifest.get('version') == VERSION and all(
            ALLOWED.fullmatch(n) and (DIRECTORY / n).is_file() and (DIRECTORY / n).stat().st_size == size
            for n, size in manifest.get('files', {}).items())
        ready = ready and all(n in manifest.get('files', {}) for n in ['vision_bundle.mjs', 'hand_landmarker.task', 'wasm/vision_wasm_internal.wasm'])
    except (OSError, ValueError):
        manifest, ready = {}, False
    return {'ready': bool(ready), 'version': VERSION, 'model_bytes': MODEL_SIZE,
            'runtime_unpacked_bytes': 31_269_184, 'download_mb_approx': 18,
            'runtime_url': '/api/hands/assets/vision_bundle.mjs', 'wasm_url': '/api/hands/assets/wasm',
            'model_url': '/api/hands/assets/hand_landmarker.task',
            'installed_bytes': sum(manifest.get('files', {}).values()),
            'downloaded_bytes': manifest.get('downloaded_bytes', 0)}


def _fetch(url, path, limit):
    size = 0
    with urllib.request.urlopen(url, timeout=60) as response, path.open('wb') as target:
        while chunk := response.read(65536):
            size += len(chunk)
            if size > limit:
                raise ValueError('Asset exceeded the download limit')
            target.write(chunk)
    return size


def install():
    with _lock:
        if status()['ready']:
            return status()
        DIRECTORY.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=DIRECTORY.parent, prefix='hands-install-') as temp:
            staging = Path(temp)
            archive = staging / 'runtime.tgz'
            downloaded = _fetch(ARCHIVE, archive, 30_000_000)
            if base64.b64encode(hashlib.sha512(archive.read_bytes()).digest()).decode() != INTEGRITY:
                raise ValueError('Runtime integrity check failed')
            target = staging / 'assets'; target.mkdir()
            files = {}; total = 0
            with tarfile.open(archive, 'r:gz') as package:
                for member in package.getmembers():
                    name = member.name.removeprefix('package/')
                    if not member.isfile() or not ALLOWED.fullmatch(name) or name == 'hand_landmarker.task':
                        continue
                    total += member.size
                    if total > 64_000_000:
                        raise ValueError('Runtime exceeded the extraction limit')
                    output = target / name; output.parent.mkdir(parents=True, exist_ok=True)
                    with package.extractfile(member) as source, output.open('wb') as dest:
                        shutil.copyfileobj(source, dest)
                    files[name] = output.stat().st_size
            model = target / 'hand_landmarker.task'
            downloaded += _fetch(MODEL_URL, model, MODEL_SIZE + 1)
            if model.stat().st_size != MODEL_SIZE:
                raise ValueError('Hand model size check failed')
            if hashlib.sha256(model.read_bytes()).hexdigest() != MODEL_SHA256:
                raise ValueError('Hand model checksum check failed')
            files[model.name] = MODEL_SIZE
            for required in ['vision_bundle.mjs', 'wasm/vision_wasm_internal.wasm', 'hand_landmarker.task']:
                if required not in files:
                    raise ValueError('Runtime package is missing a required file')
            (target / 'manifest.json').write_text(json.dumps({'version': VERSION, 'files': files,
                'downloaded_bytes': downloaded}, indent=2), encoding='utf-8')
            DIRECTORY.mkdir(exist_ok=True)
            for name in files:
                dest = DIRECTORY / name; dest.parent.mkdir(parents=True, exist_ok=True)
                (target / name).replace(dest)
            (target / 'manifest.json').replace(DIRECTORY / 'manifest.json')
        return status()


@routes.get('/api/hands/status')
async def api_status(request):
    return web.json_response(status())


@routes.post('/api/hands/install')
async def api_install(request):
    if (await request.json()).get('confirm') is not True:
        raise web.HTTPBadRequest(text='Confirm the hand-tracking download first')
    try:
        result = await asyncio.get_running_loop().run_in_executor(None, install)
    except Exception:
        raise web.HTTPBadGateway(text='Hand-tracking download failed. Nothing was enabled; try again.')
    return web.json_response(result)


@routes.get('/api/hands/assets/{asset:.+}')
async def asset(request):
    name = request.match_info['asset']
    if not ALLOWED.fullmatch(name) or not status()['ready']:
        raise web.HTTPNotFound()
    path = DIRECTORY / name
    if not path.is_file():
        raise web.HTTPNotFound()
    response = web.FileResponse(path)
    response.content_type = 'application/wasm' if name.endswith('.wasm') else 'application/octet-stream' if name.endswith('.task') else 'text/javascript' if name.endswith(('.js', '.mjs')) else 'text/plain'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Cache-Control'] = 'private, max-age=86400'
    return response
