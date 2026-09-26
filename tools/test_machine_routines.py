"""Backend B: the matcher, the profiles, and the refusal rule.

Everything runs on synthetic frames — no screen is captured and no click is ever
sent, because every MCP call is mocked. What is under test is whether the anchor
is found where it really is, and whether a weak match is refused.
"""
import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
os.environ["HUB_TEST_IMPORT_ROOT"] = str(root)

from hub.features import machine_routines as M  # noqa: E402
from hub.features import pc_control as P  # noqa: E402

np = __import__("numpy")
from PIL import Image  # noqa: E402

# Production ceilings are measured in minutes on purpose (an installer decides
# when it is ready). Tests pin them short so a refusal is quick, not a hang.
FAST = {"ceiling_s": 0.4, "poll_s": 0.05}


def frame_with(patch_img, at, size=(400, 300), seed=7):
    """A reproducible noisy frame with `patch_img` pasted at `at` (left, top)."""
    rng = np.random.default_rng(seed)
    bg = rng.integers(40, 90, size=(size[1], size[0]), dtype=np.uint8)
    img = Image.fromarray(bg, mode="L").convert("RGB")
    img.paste(patch_img, at)
    return img


def button(seed=3, size=(48, 24)):
    """A distinctive patch — structure, not a flat block, so NCC has something to lock onto."""
    rng = np.random.default_rng(seed)
    return Image.fromarray(rng.integers(140, 255, size=(size[1], size[0]), dtype=np.uint8),
                           mode="L").convert("RGB")


class MatcherTests(unittest.TestCase):
    def test_finds_the_anchor_at_its_true_centre(self):
        b = button()
        frame = frame_with(b, (120, 80))
        x, y, score = M.match_anchor(M.to_gray(frame), M.to_gray(b))
        self.assertAlmostEqual(x, 120 + 24, delta=1)      # centre, not corner
        self.assertAlmostEqual(y, 80 + 12, delta=1)
        self.assertGreater(score, 0.99)

    def test_absent_anchor_scores_low(self):
        frame = frame_with(button(seed=3), (50, 50))
        _, _, score = M.match_anchor(M.to_gray(frame), M.to_gray(button(seed=99)))
        self.assertLess(score, 0.7)

    def test_brightness_shift_does_not_move_the_match(self):
        """Normalised correlation is the reason a different monitor or gamma
        setting does not invalidate every recorded routine."""
        b = button()
        frame = frame_with(b, (200, 150))
        brighter = Image.fromarray(np.clip(M.to_gray(frame) * 0.6 + 60, 0, 255).astype(np.uint8), "L")
        x, y, score = M.match_anchor(M.to_gray(brighter.convert("RGB")), M.to_gray(b))
        self.assertAlmostEqual(x, 224, delta=1)
        self.assertAlmostEqual(y, 162, delta=1)
        self.assertGreater(score, 0.99)

    def test_anchor_larger_than_frame_returns_none(self):
        self.assertIsNone(M.match_anchor(M.to_gray(button(size=(20, 20))),
                                         M.to_gray(button(size=(80, 80)))))

    def test_flat_anchor_is_refused_rather_than_matched_everywhere(self):
        flat = Image.new("RGB", (30, 30), (128, 128, 128))
        self.assertIsNone(M.match_anchor(M.to_gray(frame_with(flat, (10, 10))), M.to_gray(flat)))


class ProfileTests(unittest.IsolatedAsyncioTestCase):
    async def test_gameplay_picks_reflex_and_installs_pick_patient(self):
        self.assertEqual((await M.choose_profile("start a ranked match in the game"))["profile"], "reflex")
        self.assertEqual((await M.choose_profile("run the installer and click through setup"))["profile"], "patient")

    async def test_unclear_wording_falls_back_to_balanced_rather_than_guessing(self):
        out = await M.choose_profile("do the thing with the window")
        self.assertEqual(out["profile"], "balanced")
        self.assertEqual(out["p"], 0.0)          # honest: it abstained, it did not decide

    def test_reflex_replays_timing_and_patient_waits(self):
        self.assertEqual(M.profile_for("reflex")["timing"], "recorded")
        self.assertEqual(M.profile_for("patient")["timing"], "wait")
        self.assertGreater(M.profile_for("patient")["ceiling_s"], M.profile_for("reflex")["ceiling_s"])
        self.assertGreater(M.profile_for("reflex")["floor"], M.profile_for("patient")["floor"])


class ReplayTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db, self.old_anchors = P.DB_PATH, M.ANCHORS
        P.DB_PATH = Path(self.tmp.name) / "pc.sqlite"
        M.ANCHORS = Path(self.tmp.name) / "anchors"

    def tearDown(self):
        P.DB_PATH, M.ANCHORS = self.old_db, self.old_anchors
        self.tmp.cleanup()

    def _routine(self, profile="balanced", seed=3):
        b = button(seed=seed)
        buf = __import__("io").BytesIO()
        b.save(buf, format="PNG")
        return M.save_machine_routine(
            "game:start-match", "Start a ranked match", "NEON WARFARE", profile,
            [{"tool": "Click", "args": {"button": "left"}, "frac": [0.5, 0.5],
              "delay_ms": 0, "anchor_png": buf.getvalue(), "note": "PLAY button"}])

    async def test_clicks_where_the_anchor_actually_is_now(self):
        routine = self._routine()
        frame = frame_with(button(seed=3), (260, 190))
        calls = []

        async def fake(server, tool, args, timeout=90):
            calls.append((tool, args))
            return {"text": ["ok"]}

        with patch.object(MCPTarget := M.MCP, "call_tool", side_effect=fake):
            out = await M.replay_machine_routine(routine, grab=lambda: frame, policy_override=FAST)
        self.assertTrue(out["ok"], out)
        self.assertEqual(len(calls), 1)
        x, y = calls[0][1]["loc"]
        self.assertAlmostEqual(x, 284, delta=2)
        self.assertAlmostEqual(y, 202, delta=2)
        self.assertGreater(min(out["scores"]), 0.99)

    async def test_a_weak_match_refuses_and_clicks_nothing(self):
        """The rule the whole module exists to keep: never click on a guess."""
        routine = self._routine()
        wrong = frame_with(button(seed=99), (100, 100))      # the button is not on this screen
        calls = []

        async def fake(server, tool, args, timeout=90):
            calls.append(tool)
            return {"text": ["ok"]}

        with patch.object(M.MCP, "call_tool", side_effect=fake):
            out = await M.replay_machine_routine(routine, grab=lambda: wrong, policy_override=FAST)
        self.assertFalse(out["ok"])
        self.assertEqual(out["route"], "fall-through")
        self.assertEqual(calls, [])
        self.assertIn("stopped rather than", out["say"])

    async def test_reflex_floor_is_stricter_than_balanced(self):
        """A frame good enough for an installer is not good enough for gameplay.

        Sigma 20 lands the match at ~0.85 — deliberately between patient's 0.80
        floor and reflex's 0.90, which is the whole point of separate profiles.
        """
        blurred = frame_with(button(seed=3), (260, 190))
        arr = M.to_gray(blurred)
        noisy = np.clip(arr + np.random.default_rng(1).normal(0, 20, arr.shape), 0, 255)
        frame = Image.fromarray(noisy.astype(np.uint8), "L").convert("RGB")

        async def fake(server, tool, args, timeout=90):
            return {"text": ["ok"]}

        with patch.object(M.MCP, "call_tool", side_effect=fake):
            lenient = await M.replay_machine_routine(self._routine(profile="patient"),
                                                     grab=lambda: frame, policy_override=FAST)
        P.DB_PATH.unlink(missing_ok=True)
        with patch.object(M.MCP, "call_tool", side_effect=fake):
            strict = await M.replay_machine_routine(self._routine(profile="reflex"),
                                                    grab=lambda: frame, policy_override=FAST)
        self.assertTrue(lenient["ok"], lenient)
        self.assertFalse(strict["ok"], strict)

    async def test_missing_anchor_file_says_re_record_instead_of_crashing(self):
        routine = self._routine()
        for p in (M.ANCHORS / routine["id"]).glob("*.png"):
            p.unlink()
        with patch.object(M.MCP, "call_tool", AsyncMock()):
            out = await M.replay_machine_routine(routine, grab=lambda: frame_with(button(), (10, 10)),
                                                 policy_override=FAST)
        self.assertFalse(out["ok"])
        self.assertIn("re-record", out["say"])

    async def test_confidence_is_stored_per_step_for_drift(self):
        routine = self._routine()
        frame = frame_with(button(seed=3), (260, 190))
        with patch.object(M.MCP, "call_tool", AsyncMock(return_value={"text": ["ok"]})):
            await M.replay_machine_routine(routine, grab=lambda: frame, policy_override=FAST)
        step = P._steps(routine["id"])[0]
        target = __import__("json").loads(step["target_json"])
        self.assertGreater(target["last_score"], 0.99)
        self.assertIn("last_ms", target)

    def test_it_is_stored_as_a_machine_routine_with_its_profile(self):
        routine = self._routine(profile="reflex")
        self.assertEqual(routine["kind"], "machine")
        self.assertEqual(routine["tool"], "surface")
        self.assertEqual(__import__("json").loads(routine["args_json"])["profile"], "reflex")



class WorkerParityTests(unittest.TestCase):
    """A routine recorded on one backend must replay identically on the other.

    The worker exists because a frozen build has no numpy in-process; if the two
    disagreed, a routine's floor would mean different things in dev and in the
    shipped app.
    """

    def test_worker_and_inprocess_agree_on_the_same_frame(self):
        import json as _json
        import subprocess

        worker = root / "packaging" / "vision_worker.py"
        self.assertTrue(worker.is_file(), "vision_worker.py is missing from packaging/")
        with tempfile.TemporaryDirectory() as tmp:
            b = button(seed=5)
            frame = frame_with(b, (150, 110))
            apath, fpath = Path(tmp) / "a.png", Path(tmp) / "f.png"
            b.save(apath)
            frame.save(fpath)

            here = M.match_anchor(M.to_gray(frame), M.to_gray(b))
            run = subprocess.run([sys.executable, str(worker), str(apath), str(fpath)],
                                 capture_output=True, text=True, timeout=180)
            self.assertEqual(run.returncode, 0, run.stderr)
            there = _json.loads(run.stdout.strip().splitlines()[-1])

        self.assertTrue(there["ok"], there)
        self.assertEqual((there["x"], there["y"]), (here[0], here[1]))
        self.assertAlmostEqual(there["score"], here[2], places=5)

    def test_worker_reports_a_featureless_anchor_rather_than_a_false_hit(self):
        import json as _json
        import subprocess

        with tempfile.TemporaryDirectory() as tmp:
            flat = Image.new("RGB", (30, 30), (128, 128, 128))
            apath, fpath = Path(tmp) / "a.png", Path(tmp) / "f.png"
            flat.save(apath)
            frame_with(flat, (10, 10)).save(fpath)
            run = subprocess.run([sys.executable, str(root / "packaging" / "vision_worker.py"),
                                  str(apath), str(fpath)],
                                 capture_output=True, text=True, timeout=180)
        out = _json.loads(run.stdout.strip().splitlines()[-1])
        self.assertFalse(out["ok"])
        self.assertIn("featureless", out["error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
