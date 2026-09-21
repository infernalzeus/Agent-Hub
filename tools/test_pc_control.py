import asyncio
import os
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
os.environ["HUB_TEST_IMPORT_ROOT"] = str(root)
from hub.features import pc_control as P
from hub.features import voice as V

class PcControlTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "pc.sqlite"
        self.old = P.DB_PATH; P.DB_PATH = self.path
    def tearDown(self):
        P.DB_PATH = self.old; self.tmp.cleanup()
    async def test_first_launch_is_recorded_as_candidate_then_replayed(self):
        with patch.object(P.MCP, "call_tool", AsyncMock(return_value={"text":["Apple Music launched"]})) as call:
            first = await P.launch_app("Apple Music", "Open Apple Music")
            second = await P.launch_app("Apple Music", "Open Apple Music")
        self.assertTrue(first["ok"]); self.assertEqual(first["say"], 'Opened Apple Music.')
        self.assertEqual(second["say"], 'Opened Apple Music.')
        self.assertEqual(first["routine"]["tag"], 'ROUTINE')
        self.assertEqual(call.await_count, 2)
        with P._db() as db:
            row = db.execute("SELECT successes,status FROM pc_routines").fetchone()
            self.assertEqual(row[0], 2); self.assertEqual(row[1], 'trusted')
    async def test_classifier_removes_spoken_filler_before_routine_lookup(self):
        self.assertEqual(P.classify_request('Open Outlook for me'), {'kind':'launch_app','app':'outlook','intent':'open:outlook'})
        self.assertEqual(P.classify_request('Open Outlook'), {'kind':'launch_app','app':'outlook','intent':'open:outlook'})

    async def test_failed_first_discovery_is_not_learned(self):
        with patch.object(P.MCP, "call_tool", AsyncMock(side_effect=RuntimeError('not found'))):
            result = await P.launch_app("Missing Example App", "Open Missing Example App")
        self.assertFalse(result["ok"])
        with P._db() as db:
            self.assertIsNone(db.execute("SELECT * FROM pc_routines").fetchone())

    async def test_voice_routes_named_app_to_pc_pipeline(self):
        with patch('hub.features.mcp.servers', return_value=[{'name':'windows','installed':True,'enabled':True}]):
            result = await V.chat('Open Apple Music')
        self.assertEqual(result['action']['id'], 'pc_app')
        self.assertEqual(result['action']['args']['app'], 'apple music')

if __name__ == '__main__': unittest.main(verbosity=2)
