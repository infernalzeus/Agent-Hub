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


# Exactly the shape windows_mcp/tree/views.py renders (window header, then
# "<connector> (x,y) <control> "<name>"  [action: ...]" per element).
SNAP_A = """window "Untitled - Notepad"
├── (120,40) button "Save"  [action: click]
├── (300,40) button "Open"  [action: click]
└── (400,300) edit "Text Editor"  [action: type]

window "Program Manager"
└── (10,1050) button "Start"  [action: click]"""

# Same controls, window dragged 500px right: coordinates differ, identities do not.
SNAP_MOVED = """window "Untitled - Notepad"
├── (620,140) button "Save"  [action: click]
├── (800,140) button "Open"  [action: click]
└── (900,400) edit "Text Editor"  [action: type]"""

# A different dialog: the screen genuinely changed.
SNAP_CHANGED = """window "Untitled - Notepad"
├── (120,40) button "Save As"  [action: click]
└── (400,300) edit "Text Editor"  [action: type]"""


class SnapshotParsingTests(unittest.TestCase):
    def test_parses_windows_controls_and_centres(self):
        els = P.parse_snapshot(SNAP_A)
        self.assertEqual(len(els), 4)
        save = els[0]
        self.assertEqual((save["window"], save["control"], save["name"]),
                         ("Untitled - Notepad", "button", "Save"))
        self.assertEqual((save["x"], save["y"]), (120, 40))
        self.assertEqual(els[3]["window"], "Program Manager")

    def test_empty_and_garbage_do_not_raise(self):
        self.assertEqual(P.parse_snapshot(""), [])
        self.assertEqual(P.parse_snapshot("No interactive elements"), [])

    def test_signature_ignores_position_but_not_content(self):
        """Dragging a window must not invalidate a routine; changing it must."""
        a = P.ui_signature(P.parse_snapshot(SNAP_A), "Untitled - Notepad")
        moved = P.ui_signature(P.parse_snapshot(SNAP_MOVED), "Untitled - Notepad")
        changed = P.ui_signature(P.parse_snapshot(SNAP_CHANGED), "Untitled - Notepad")
        self.assertEqual(a["fingerprint"], moved["fingerprint"])
        self.assertNotEqual(a["fingerprint"], changed["fingerprint"])
        self.assertEqual(a["controls"], 3)      # the other window is not mixed in

    def test_signature_is_per_window(self):
        els = P.parse_snapshot(SNAP_A)
        self.assertNotEqual(P.ui_signature(els, "Untitled - Notepad")["fingerprint"],
                            P.ui_signature(els, "Program Manager")["fingerprint"])


class UiRoutineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = P.DB_PATH
        P.DB_PATH = Path(self.tmp.name) / "pc.sqlite"

    def tearDown(self):
        P.DB_PATH = self.old
        self.tmp.cleanup()

    def _save(self):
        els = P.parse_snapshot(SNAP_A)
        return P.save_ui_routine(
            "notepad:save", "Save in Notepad", "Untitled - Notepad",
            [{"tool": "Click", "args": {"button": "left"},
              "target": {"window": "Untitled - Notepad", "control": "button", "name": "Save"}}],
            P.ui_signature(els, "Untitled - Notepad"))

    async def test_replays_when_the_screen_matches_and_resolves_live_coordinates(self):
        routine = self._save()
        calls = []

        async def fake(server, tool, args, timeout=90):
            calls.append((tool, args))
            return {"text": [SNAP_A] if tool == "Snapshot" else ["ok"]}

        with patch.object(P.MCP, "call_tool", side_effect=fake):
            out = await P.replay_ui_routine(routine)
        self.assertTrue(out["ok"], out)
        click = [a for t, a in calls if t == "Click"]
        self.assertEqual(len(click), 1)
        self.assertEqual(click[0]["loc"], [120, 40])

    async def test_moved_window_still_replays_at_the_new_coordinates(self):
        """The whole point of resolving by identity rather than storing a position."""
        routine = self._save()
        calls = []

        async def fake(server, tool, args, timeout=90):
            calls.append((tool, args))
            return {"text": [SNAP_MOVED] if tool == "Snapshot" else ["ok"]}

        with patch.object(P.MCP, "call_tool", side_effect=fake):
            out = await P.replay_ui_routine(routine)
        self.assertTrue(out["ok"], out)
        self.assertEqual([a for t, a in calls if t == "Click"][0]["loc"], [620, 140])

    async def test_changed_screen_refuses_and_clicks_nothing(self):
        routine = self._save()
        calls = []

        async def fake(server, tool, args, timeout=90):
            calls.append(tool)
            return {"text": [SNAP_CHANGED] if tool == "Snapshot" else ["ok"]}

        with patch.object(P.MCP, "call_tool", side_effect=fake):
            out = await P.replay_ui_routine(routine)
        self.assertFalse(out["ok"])
        self.assertEqual(out["route"], "fall-through")
        self.assertNotIn("Click", calls)        # the only assertion that really matters

    async def test_missing_control_mid_sequence_stops_instead_of_guessing(self):
        els = P.parse_snapshot(SNAP_A)
        routine = P.save_ui_routine(
            "notepad:two", "Two steps", "Untitled - Notepad",
            [{"tool": "Click", "args": {},
              "target": {"window": "Untitled - Notepad", "control": "button", "name": "Save"}},
             {"tool": "Click", "args": {},
              "target": {"window": "Untitled - Notepad", "control": "button", "name": "Gone"}}],
            P.ui_signature(els, "Untitled - Notepad"))
        clicks = []

        async def fake(server, tool, args, timeout=90):
            if tool == "Snapshot":
                return {"text": [SNAP_A]}
            clicks.append(args)
            return {"text": ["ok"]}

        with patch.object(P.MCP, "call_tool", side_effect=fake):
            out = await P.replay_ui_routine(routine)
        self.assertFalse(out["ok"])
        self.assertEqual(len(clicks), 1)        # the first ran, the second refused

    async def test_two_clean_runs_promote_to_trusted(self):
        routine = self._save()

        async def fake(server, tool, args, timeout=90):
            return {"text": [SNAP_A] if tool == "Snapshot" else ["ok"]}

        with patch.object(P.MCP, "call_tool", side_effect=fake):
            await P.replay_ui_routine(routine)
            second = await P.replay_ui_routine(routine)
        self.assertEqual(second["routine"]["status"], "trusted")
        self.assertEqual(second["routine"]["successes"], 2)

    def test_saving_twice_replaces_steps_rather_than_appending(self):
        self._save()
        self._save()
        self.assertEqual(len(P._steps(self._save()["id"])), 1)

    def test_launch_routines_still_report_their_kind(self):
        with P._db() as db:
            cols = {c[1] for c in db.execute("PRAGMA table_info(pc_routines)")}
        self.assertIn("kind", cols)

if __name__ == '__main__': unittest.main(verbosity=2)
