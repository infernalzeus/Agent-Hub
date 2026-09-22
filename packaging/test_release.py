"""Installer behavior tests: isolated state, no downloads or system changes."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'agent-hub'
if '--source' in sys.argv:
    position = sys.argv.index('--source')
    SOURCE = Path(sys.argv[position + 1]).resolve()
    del sys.argv[position:position + 2]
PROFILE = tempfile.TemporaryDirectory(prefix='agenthub-release-')
os.environ['AGENTHUB_STATE_DIR'] = str(Path(PROFILE.name) / 'state')
os.environ['AGENTHUB_WORK_ROOT'] = str(Path(PROFILE.name) / 'data')
os.environ['USERPROFILE'] = PROFILE.name
sys.path.insert(0, str(SOURCE))
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from hub.features import onboarding as O, voice
from hub import runtime as RT, locations as LOC, app_registry


def _payload_manifest() -> Path:
    """payloads.json as the staged/frozen tree sees it, else the repo's copy."""
    staged = RT.payloads()
    if staged and (staged / 'payloads.json').is_file():
        return staged / 'payloads.json'
    return ROOT / 'payloads.json'


class SetupTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        RT.write_json(O.FILE, {})
        LOC.FILE.unlink(missing_ok=True)
        LOC._CACHE['stamp'] = None
        app = web.Application(middlewares=[O.middleware])
        app.add_routes(O.routes)
        async def home(request):
            return web.Response(text='<html><head></head><body>Hub</body></html>', content_type='text/html')
        app.router.add_get('/', home)
        app.router.add_get('/app/file-browser/{tail:.*}', home)
        app.router.add_post('/api/youtube-dl/download', home)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self):
        if O._task and not O._task.done():
            await O._task
        await self.client.close()

    async def test_first_launch_redirects_to_choice(self):
        res = await self.client.get('/', allow_redirects=False)
        self.assertEqual((res.status, res.headers['Location']), (302, '/onboarding'))

    async def test_deferred_choice_opens_core_without_installing(self):
        with patch.object(RT, 'install', side_effect=AssertionError('Unexpected install')):
            res = await self.client.post('/api/onboarding/choice', json={'mode': 'deferred'})
            self.assertEqual(res.status, 200)
            res = await self.client.get('/')
            self.assertEqual(res.status, 200)

    async def test_readiness_status_does_not_spawn_or_install(self):
        with patch.object(subprocess, 'run', side_effect=AssertionError('Unexpected subprocess')):
            res = await self.client.get('/api/onboarding')
            self.assertEqual(res.status, 200)

    async def test_unprepared_tool_points_to_its_setup(self):
        res = await self.client.post('/api/youtube-dl/download', json={})
        self.assertEqual((res.status, (await res.json())['setup_url']), (428, '/onboarding#media'))
        res = await self.client.get('/app/file-browser/', allow_redirects=False)
        self.assertEqual(res.headers['Location'], '/onboarding#files')

    async def test_file_setup_creates_selected_folder(self):
        selected = str(Path(PROFILE.name) / 'selected files')
        res = await self.client.post('/api/onboarding/install/files', json={'file_root': selected})
        self.assertEqual(res.status, 202)
        await O._task
        self.assertTrue(Path(selected).is_dir())
        self.assertEqual(LOC.get('file_root'), selected)
        self.assertEqual(O.state()['capabilities']['files']['status'], 'ready')

    async def test_cross_origin_setup_rejected(self):
        res = await self.client.post('/api/onboarding/choice', json={'mode': 'all'}, headers={'Origin': 'https://attacker.invalid'})
        self.assertEqual(res.status, 403)

    async def test_scan_requires_selection_before_saving(self):
        folder = Path(PROFILE.name) / 'repos'; repo = folder / 'example'; (repo / '.git').mkdir(parents=True, exist_ok=True)
        (repo / 'nested' / '.git').mkdir(parents=True, exist_ok=True)
        res = await self.client.post('/api/onboarding/projects/scan', json={'root': str(folder)})
        paths = (await res.json())['paths']
        self.assertEqual(paths, [str(repo.resolve())])
        self.assertEqual(LOC.sources(), [])
        res = await self.client.post('/api/onboarding/projects/save', json={'paths': paths})
        self.assertEqual(res.status, 200)
        self.assertEqual(len(LOC.sources()), 1)

    async def test_invalid_share_is_not_launched_or_saved(self):
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('Unexpected launch')):
            res = await self.client.post('/api/onboarding/smb/connect', json={'path': 'C:\\Windows'})
            self.assertEqual(res.status, 400)
        self.assertEqual(LOC.get('smb_share'), '')

    async def test_interrupted_install_is_retryable(self):
        O.update(job={'running': True}, capabilities={'media': {'status': 'running'}})
        res = await self.client.get('/api/onboarding')
        data = await res.json()
        self.assertEqual(data['capabilities']['media']['status'], 'failed')
        self.assertFalse(data['job']['running'])

    async def test_failed_download_never_marks_speech_ready(self):
        failed = subprocess.CompletedProcess([], 1, '', 'download unavailable')
        with patch.object(RT, 'install', return_value=(True, 'installed')), patch.object(RT, 'run', return_value=failed):
            await self.client.post('/api/onboarding/install/speech', json={'model': 'tiny'})
            await O._task
        self.assertEqual(O.state()['capabilities']['speech']['status'], 'failed')
        self.assertFalse(voice.whisper_status()['whisper'])

    async def test_concurrent_setup_is_rejected(self):
        block = asyncio.Event()
        async def pending():
            await block.wait()
        O._task = asyncio.create_task(pending())
        try:
            res = await self.client.post('/api/onboarding/install/media', json={})
            self.assertEqual(res.status, 409)
        finally:
            block.set()
            await O._task

    async def test_queue_continues_after_failed_optional_install(self):
        with patch.object(RT, 'install', return_value=(False, 'offline')):
            O.start_job(['media', 'speech', 'files'], {})
            await O._task
        statuses = O.state()['capabilities']
        self.assertEqual([statuses[key]['status'] for key in ('media', 'speech', 'files')],
                         ['failed', 'failed', 'ready'])
        self.assertFalse(O.state()['job']['running'])

    async def test_speech_without_model_does_not_download_one(self):
        with patch.object(RT, 'install', return_value=(True, 'installed')), patch.object(RT, 'run', side_effect=AssertionError('Unexpected model download')):
            await self.client.post('/api/onboarding/install/speech', json={'model': ''})
            await O._task
        self.assertEqual(O.state()['capabilities']['speech']['status'], 'needs-input')
        self.assertNotIn('speech_model', O.state())


class PackageTests(unittest.TestCase):
    def test_registry_contains_no_movie_clipper_or_frozen_python_command(self):
        manifests = json.loads(app_registry.DEFAULT.read_text(encoding='utf-8'))
        self.assertEqual([m['id'] for m in manifests], ['file-browser'])
        self.assertEqual(manifests[0]['cmd'], ['$HUB_EXE', '--file-browser'])

    def test_frozen_executable_is_never_a_python_candidate(self):
        with patch.object(RT, 'FROZEN', True), patch.object(RT, 'run', side_effect=AssertionError('Frozen executable spawned')):
            self.assertFalse(RT.usable_python(sys.executable))

    def test_no_legacy_projects_are_discovered(self):
        self.assertEqual(LOC._legacy('project_sources'), None)

    def test_startup_accepts_missing_ingested_apps(self):
        import app
        with patch.dict(app.config.APPS, {}, clear=True):
            app._selfcheck()
            self.assertGreater(len(list(app.create_app().router.routes())), 100)


class PayloadTests(unittest.TestCase):
    """The installed Hub must be able to set its bundled tools up with no network."""

    def test_wheelhouse_is_found_for_every_bundled_capability(self):
        manifest = json.loads(_payload_manifest().read_text(encoding='utf-8'))
        for capability in manifest['bundled']['wheels']:
            if capability.startswith('_'):
                continue
            self.assertIsNotNone(RT.wheelhouse(capability),
                                 capability + ' has no bundled wheels')

    def test_offline_install_uses_no_index(self):
        """pip must be told --no-index, or a 'bundled' setup silently hits PyPI."""
        captured = {}

        def fake_run(cmd, timeout=900):
            captured['cmd'] = cmd
            return SimpleNamespace(returncode=0, stdout='', stderr='')

        with patch.object(RT, 'python_for', return_value=Path(sys.executable)), \
             patch.object(RT, 'run', side_effect=fake_run):
            RT.install('media', ['yt-dlp'])
        self.assertIn('--no-index', captured['cmd'])
        self.assertIn('--find-links', captured['cmd'])

    def test_bundled_python_is_only_used_when_none_is_present(self):
        """Never install a second Python over one that already works."""
        calls = []

        with patch.object(RT, 'python_for', return_value=Path(sys.executable)), \
             patch.object(RT, 'run', side_effect=lambda cmd, timeout=900: (
                 calls.append(cmd) or SimpleNamespace(returncode=0, stdout='', stderr=''))):
            RT.install('media', ['yt-dlp'])
        self.assertFalse([c for c in calls if any('python-3' in str(a) for a in c)],
                         'bundled Python installer ran although an interpreter was available')

    def test_manifest_records_measured_hashes(self):
        manifest = json.loads(_payload_manifest().read_text(encoding='utf-8'))
        python_entry = manifest['bundled']['python']
        self.assertTrue(python_entry.get('sha256'), 'python payload has no recorded hash')
        self.assertTrue(python_entry.get('size'), 'python payload has no recorded size')
        local = RT.bundled_python_installer()
        if local and local.is_file():
            self.assertEqual(local.stat().st_size, python_entry['size'])


if __name__ == '__main__':
    try:
        unittest.main(verbosity=2)
    finally:
        PROFILE.cleanup()
