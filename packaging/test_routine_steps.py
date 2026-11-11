"""A routine recorded from an agent run can carry detours: the Apple Music ADHD one had 6 steps where 3 are needed. The person reading it can drop a step, move one, rename the control a
step presses, and replay it as a test that counts for nothing. Backend against a throwaway database; the panel against stubbed answers."""
import asyncio
import json

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from playwright.sync_api import sync_playwright

from hub.features import pc_control as PC
from test_ui_lifecycle import hub  # noqa: F401  (an isolated Hub on its own state folder)

NAMES = ["Playlists", "Lose yourself in millions of songs", "Playlists", "Playlists", "ADHD", "Play"]


@pytest.fixture
def routine(tmp_path, monkeypatch):
    monkeypatch.setattr(PC, "DB_PATH", tmp_path / "pc_control.sqlite")
    steps = [{"tool": "Click", "args": {"button": "left", "clicks": 1}, "target": {"name": n, "control": "list item", "window": "Apple Music", "path": ""}} for n in NAMES]
    PC.save_ui_routine("do:apple music:play:adhd", "Apple Music: play something from the adhd playlist", "Apple Music", steps, {"window": "Apple Music", "fingerprint": "x"})
    with PC._db() as db:
        rid = db.execute("SELECT id FROM pc_routines").fetchone()["id"]
        db.execute("UPDATE pc_routines SET status='trusted', successes=3 WHERE id=?", (rid,))
    return rid


def _names(rid):
    return [json.loads(s["target_json"])["name"] for s in PC._steps(rid)]


def test_six_steps_become_the_three_that_are_needed(routine):
    for ordinal in (0, 0, 0):                                  # drop the first three, one at a time (the list renumbers after each)
        assert PC.delete_step(routine, ordinal)
    assert _names(routine) == ["Playlists", "ADHD", "Play"] or _names(routine) == ["Playlists", "ADHD", "Play"][:3]
    assert [s["ordinal"] for s in PC._steps(routine)] == [0, 1, 2]
    with PC._db() as db:
        assert db.execute("SELECT status FROM pc_routines WHERE id=?", (routine,)).fetchone()["status"] == "candidate"     # no longer the routine that was approved


def test_a_step_can_be_moved_and_a_control_renamed(routine):
    assert PC.move_step(routine, 5, 0) and _names(routine)[0] == "Play"
    assert PC.edit_step(routine, 0, "  Play   now ") and _names(routine)[0] == "Play now"
    assert not PC.edit_step(routine, 0, "   ") and not PC.delete_step(routine, 99) and not PC.move_step(routine, 0, 99)


def test_the_endpoints_and_a_test_replay_that_counts_for_nothing(routine, monkeypatch):
    async def fake_run(rid, request="manual run"):
        PC._remember_outcome(rid, False)                        # a failed replay would normally disable a candidate
        return {"ok": False, "say": "it stopped at step 2"}
    monkeypatch.setattr(PC, "run_routine", fake_run)

    async def go():
        app = web.Application()
        app.add_routes(PC.routes)
        async with TestClient(TestServer(app)) as c:
            assert (await c.delete(f"/api/pc/routines/{routine}/steps/0")).status == 200
            assert (await c.post(f"/api/pc/routines/{routine}/steps/0", json={"to": 1})).status == 200
            assert (await c.post(f"/api/pc/routines/{routine}/steps/0", json={"name": "Everything"})).status == 200
            assert (await c.post(f"/api/pc/routines/{routine}/steps/0", json={"name": ""})).status == 400
            before = (await (await c.get("/api/pc/routines")).json())["routines"][0]
            r = await c.post(f"/api/pc/routines/{routine}/run?test=1")
            assert r.status == 200 and (await r.json())["ok"] is False
            after = (await (await c.get("/api/pc/routines")).json())["routines"][0]
            assert (after["status"], after["successes"], after["failures"]) == (before["status"], before["successes"], before["failures"])
    asyncio.new_event_loop().run_until_complete(go())


def test_the_panel_opens_a_routine_lists_its_steps_and_lets_you_drop_one(hub):
    steps = [{"ordinal": i, "tool": "Click", "args": {}, "target": {"name": n, "control": "list item", "path": ""}} for i, n in enumerate(NAMES)]
    calls = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 1000, "height": 900}).new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        row = {"id": "r1", "title": "Apple Music: play something from the adhd playlist", "status": "candidate", "successes": 0, "failures": 0, "updated": 0}
        pg.route("**/api/pc/routines", lambda r: r.fulfill(json={"routines": [row]}))
        pg.route("**/api/pc/routines/r1/steps", lambda r: r.fulfill(json={"steps": steps}))

        def drop(route):
            calls.append((route.request.method, route.request.url.rsplit("/", 1)[-1]))
            steps.pop(int(route.request.url.rsplit("/", 1)[-1]))
            route.fulfill(json={"ok": True})
        pg.route("**/api/pc/routines/r1/steps/*", drop)
        pg.goto(hub + "/yard")
        pg.click("[data-tab=routines]")
        pg.wait_for_selector(".rc .rhead")
        assert pg.locator(".rc .rbody").is_hidden()                                              # collapsed until you open it
        pg.click(".rc .rhead")
        assert pg.locator(".rc .rbody").is_visible() and pg.locator(".rc .rbody button:text-is('REPLAY')").count() == 1
        pg.click(".rc button:text-is('STEPS')")
        pg.wait_for_function("document.querySelectorAll('.rc .step').length===6")
        pg.click(".rc .step:first-child button[title='Remove this step']")
        pg.wait_for_function("document.querySelectorAll('.rc .step').length===5")
        assert calls == [("DELETE", "0")]
        buttons = pg.evaluate("[...document.querySelectorAll('.rc .rbody > .row button')].map(b=>b.textContent)")
        assert buttons[:3] == ["REPLAY", "ATTEMPT AGAIN", "STEPS"]                                           # the buttons sit above what they open: nothing to scroll to close it
        pg.click(".rc .rhead")
        assert pg.locator(".rc .rbody").is_hidden()
        b.close()
    assert errors == []


def test_a_replay_counts_its_seconds_ends_with_one_clear_line_and_a_launch_routine_shows_its_command(hub):
    """11 Nov 23:17: REPLAY sat on STOP with no sign of progress and no clear end; the launch routine said it had no steps."""
    step = {"ordinal": 0, "tool": "App", "args": {"mode": "launch", "name": "Apple Music"}, "target": {"name": "Apple Music", "control": "app"}, "fixed": True,
            "command": 'windows.App {"mode": "launch", "name": "Apple Music"}: start “Apple Music” by its Start-menu name, then check that its window came up', "source": "the Start-menu entry “Apple Music”, remembered from 20 earlier successful opens"}
    row = {"id": "l1", "title": "Open Apple Music", "status": "trusted", "successes": 20, "failures": 0, "updated": 0, "tool": "App", "last_replay": None, "replay_failures": 0}
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 1000, "height": 900}).new_page()
        pg.on("dialog", lambda d: d.accept())
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))

        def run(route):
            pg.wait_for_timeout(2600)                                                                # a slow start, as Windows gave Apple Music
            route.fulfill(json={"ok": True, "route": "routine", "say": "Opened Apple Music. Took 1.6 s.", "ms": 1600})
        pg.route("**/api/pc/routines", lambda r: r.fulfill(json={"routines": [row]}))
        pg.route("**/api/pc/routines/l1/steps", lambda r: r.fulfill(json={"steps": [step]}))
        pg.route("**/api/pc/routines/l1/run?test=1", run)
        pg.route("**/api/pc/routines/l1/last-run", lambda r: r.fulfill(json={"run": None}))
        pg.goto(hub + "/yard")
        pg.click("[data-tab=routines]")
        pg.wait_for_selector(".rc .rhead")
        pg.click(".rc .rhead")
        pg.click(".rc button:text-is('STEPS')")
        pg.wait_for_selector(".rc .step")
        txt = pg.inner_text(".rc .step")
        assert "open app" in txt and "Apple Music" in txt and "windows.App" in txt and "Start-menu entry" in txt and "20 earlier successful opens" in txt
        assert pg.locator(".rc .step button").count() == 0                                           # a launch is not edited step by step
        pg.click(".rc .rbody button:text-is('REPLAY')")
        pg.wait_for_selector(".rc .rbody button:text-is('STOP')")
        pg.wait_for_function("/Replaying \d+ s/.test(document.querySelector('.rc .why').textContent)", timeout=4000)
        pg.wait_for_function("document.querySelector('.rc .why').textContent.startsWith('REPLAY WORKED')", timeout=8000)
        assert pg.locator(".rc .rbody button:text-is('REPLAY')").count() == 1 and pg.locator(".rc .rbody button:text-is('STOP')").count() == 0
        assert "It stays trusted" in pg.inner_text(".rc .why") and "Opened Apple Music" in pg.inner_text(".rc .why")
        b.close()
    assert errors == []
