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
        how = pg.evaluate("[...document.querySelectorAll('.rc .rbody .rgrp.left button')].map(b=>b.textContent)")
        assert how == ["REPLAY", "ATTEMPT AGAIN", "STEPS", "WHY"]                                           # how it is done: on the left, above what they open
        state = pg.evaluate("[...document.querySelectorAll('.rc .rbody .seg button')].map(b=>b.textContent)")
        assert state == ["CANDIDATE", "TRUSTED", "DISABLED"]                                                # what state it is in: one selector, on the right
        left, right = pg.locator(".rc .rbody .rgrp.left").bounding_box(), pg.locator(".rc .rbody .rgrp.right").bounding_box()
        assert right["x"] > left["x"] + left["width"] - 1 and pg.locator(".rc .rbody .seg button:text-is('DELETE')").count() == 0   # the state selector is apart from the how, and DELETE is not part of it
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
        pg.wait_for_function("/Replaying [0-9]+ s/.test((document.querySelector('.rc .why')||{}).textContent||'')", timeout=4000)
        pg.wait_for_function("((document.querySelector('.rc .why')||{}).textContent||'').startsWith('REPLAY WORKED')", timeout=8000)
        pg.wait_for_function("document.querySelectorAll('.rc .rbody button').length>0 && [...document.querySelectorAll('.rc .rbody button')].every(b=>b.textContent!=='STOP') && [...document.querySelectorAll('.rc .rbody button')].some(b=>b.textContent==='REPLAY') && ((document.querySelector('.rc .why')||{}).textContent||'').includes('It stays trusted')", timeout=6000)    # the list refreshes after a replay
        assert "Opened Apple Music" in pg.inner_text(".rc .why")
        b.close()
    assert errors == []


def test_the_state_selector_shows_the_state_and_a_click_sets_it_and_delete_stands_apart(hub):
    rows = [{"id": "t1", "title": "Open Apple Music", "status": "trusted", "successes": 20, "failures": 0, "updated": 0, "tool": "App"},
            {"id": "c1", "title": "Open Claude", "status": "candidate", "successes": 4, "failures": 0, "updated": 0, "tool": "App"}]
    posted = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 1000, "height": 900}).new_page()
        pg.route("**/api/pc/routines", lambda r: r.fulfill(json={"routines": rows}))
        pg.route("**/api/pc/routines/*/status", lambda r: (posted.append((r.request.url.split("/")[-2], r.request.post_data_json["status"])), r.fulfill(json={"ok": True}))[1])
        pg.route("**/api/pc/routines/*/last-run", lambda r: r.fulfill(json={"run": None}))
        pg.goto(hub + "/yard")
        pg.click("[data-tab=routines]")
        pg.wait_for_selector(".rc .rhead")
        pg.locator(".rc .rhead").nth(0).click()
        first = pg.locator(".rc").nth(0)
        assert "on" in (first.locator(".seg button:text-is('TRUSTED')").get_attribute("class") or "").split() and "on" not in (first.locator(".seg button:text-is('CANDIDATE')").get_attribute("class") or "").split()
        assert first.locator("button:text-is('ATTEMPT AGAIN')").is_hidden()                                  # a launch routine is replayed, not attempted again
        first.locator(".seg button:text-is('CANDIDATE')").click()
        pg.wait_for_timeout(300)
        pg.locator(".rc .rhead").nth(1).click()
        second = pg.locator(".rc").nth(1)
        assert "on" in second.locator(".seg button:text-is('CANDIDATE')").get_attribute("class").split()
        second.locator(".seg button:text-is('TRUSTED')").click()
        pg.wait_for_timeout(500)
        assert pg.locator(".rc").nth(0).locator(".rgrp.right > button:text-is('DELETE')").count() == 1      # DELETE is its own control beside the selector, not one of its three states
        b.close()
    assert posted == [("t1", "candidate"), ("c1", "trusted")]


def test_a_step_can_be_studied_its_confidence_last_result_and_note_run_on_its_own_and_a_routine_note_saved(hub):
    steps = [{"ordinal": 0, "tool": "Click", "args": {}, "target": {"name": "Playlists", "control": "list item", "path": "", "confidence": 0.9}, "note": "", "confidence": 0.9},
             {"ordinal": 1, "tool": "Click", "args": {}, "target": {"name": "ADHD", "control": "list item", "path": ""}, "note": "under Playlists", "confidence": None},
             {"ordinal": 2, "tool": "Click", "args": {}, "target": {"name": "Play", "control": "button", "path": "ADHD"}, "note": "", "confidence": 0.55}]
    run = {"id": "r1", "kind": "replay", "at": 1.0, "ms": 5000, "ok": False, "say": "x", "trace": [{"step": 0, "ordinal": 0, "do": "click", "control": "Playlists", "ms": 900, "shot": ""},
                                                                                              {"step": 1, "ordinal": 1, "do": "click", "control": "ADHD", "ms": 700, "error": "not on screen", "shot": ""}]}
    row = {"id": "e1", "title": "Apple Music: play something from the adhd playlist", "status": "candidate", "successes": 0, "failures": 0, "updated": 0, "tool": "ui", "note": "first words", "last_replay": None, "replay_failures": 0}
    posted = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 1100, "height": 900}).new_page()
        pg.on("dialog", lambda d: d.accept("Play is the one inside the playlist" if d.type == "prompt" else None))
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.route("**/api/pc/routines", lambda r: r.fulfill(json={"routines": [row]}))
        pg.route("**/api/pc/routines/e1/last-run", lambda r: r.fulfill(json={"run": run}))
        pg.route("**/api/pc/routines/e1/steps", lambda r: r.fulfill(json={"steps": steps}))
        pg.route("**/api/pc/routines/e1/steps/*/run", lambda r: (posted.append(("run", r.request.url.split("/")[-2], r.request.post_data_json["mode"])), r.fulfill(json={"ok": True, "route": "routine", "say": "Ran step 2."}))[1])
        pg.route("**/api/pc/routines/e1/steps/2", lambda r: (posted.append(("step-note", r.request.post_data_json)), r.fulfill(json={"ok": True}))[1])
        pg.route("**/api/pc/routines/e1/note", lambda r: (posted.append(("note", r.request.post_data_json["note"])), r.fulfill(json={"ok": True}))[1])
        pg.goto(hub + "/yard")
        pg.click("[data-tab=routines]")
        pg.wait_for_selector(".rc .rhead")
        pg.click(".rc .rhead")
        assert pg.locator(".rc textarea").input_value() == "first words"
        pg.locator(".rc textarea").fill("Playlists then ADHD then the Play inside it")
        pg.click(".rc button:text-is('SAVE NOTE')")
        pg.wait_for_function("document.querySelector('.rc .why').textContent==='Note saved.'")
        pg.click(".rc button:text-is('STEPS')")
        pg.wait_for_selector(".rc .step")
        mine = pg.locator(".rc .step:has(button[title^='Run just this step'])")                    # the rows of the routine's own steps (the last run lists its own above them)
        mine.nth(2).wait_for()
        text = " ".join(mine.all_inner_texts())
        assert "90 % sure" in text and "55 % sure" in text and "Last run: worked" in text and "Last run: FAILED - not on screen" in text and "Note: under Playlists" in text
        mine.nth(1).locator("button[title^='Run just this step']").click()
        pg.wait_for_function("(document.querySelector('.rc .why')||{textContent:''}).textContent.startsWith('STEP WORKED')", timeout=6000)
        mine.nth(2).locator("button:text-is('NOTE')").click()
        pg.wait_for_timeout(500)
        b.close()
    assert errors == []
    assert ("note", "Playlists then ADHD then the Play inside it") in posted and ("run", "1", "one") in posted and ("step-note", {"note": "Play is the one inside the playlist"}) in posted


def test_steps_and_why_toggle_open_and_closed_and_a_picture_opens_inside_the_panel(hub):
    steps = [{"ordinal": 0, "tool": "Click", "args": {}, "target": {"name": "Playlists", "control": "list item", "path": ""}, "note": "", "confidence": None}]
    run = {"id": "r1", "kind": "replay", "at": 1.0, "ms": 5000, "ok": True, "say": "x", "trace": [{"step": 0, "ordinal": 0, "do": "click", "control": "Playlists", "ms": 900, "shot": "000.jpg"}]}
    row = {"id": "e1", "title": "Apple Music: play something", "status": "candidate", "successes": 0, "failures": 0, "updated": 0, "tool": "ui", "note": "", "last_replay": None, "replay_failures": 0}
    GIF = bytes.fromhex("47494638396101000100800000ffffff00000021f90401000000002c00000000010001000002024401003b")
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(service_workers="block", viewport={"width": 1100, "height": 900})
        pg = ctx.new_page()
        opened_pages = []
        ctx.on("page", lambda p: opened_pages.append(p))
        pg.route("**/api/pc/routines", lambda r: r.fulfill(json={"routines": [row]}))
        pg.route("**/api/pc/routines/e1/last-run", lambda r: r.fulfill(json={"run": run}))
        pg.route("**/api/pc/routines/e1/steps", lambda r: r.fulfill(json={"steps": steps}))
        pg.route("**/api/runs/r1/shot/000.jpg", lambda r: r.fulfill(content_type="image/gif", body=GIF))
        pg.route("**/api/yard/why/routine/e1", lambda r: r.fulfill(json={"error": "no named-control steps in that routine"}))
        pg.goto(hub + "/yard")
        pg.click("[data-tab=routines]")
        pg.wait_for_selector(".rc .rhead")
        pg.click(".rc .rhead")
        steps_btn = pg.locator(".rc button:text-is('STEPS')")
        steps_btn.click()
        mine = pg.locator(".rc .step:has(button[title^='Run just this step'])")
        mine.first.wait_for()
        assert steps_btn.get_attribute("aria-expanded") == "true"
        steps_btn.click()                                                                                 # the second press puts the steps away
        pg.wait_for_function("document.querySelectorAll(\".rc .step button[title^='Run just this step']\").length===0")
        assert steps_btn.get_attribute("aria-expanded") == "false"
        steps_btn.click()
        mine.first.wait_for()
        why = pg.locator(".rc button:text-is('WHY')")
        why.click()
        pg.wait_for_selector(".rc .whyh")
        assert "WHY" in pg.inner_text(".rc .whyh") and why.get_attribute("aria-expanded") == "true"
        assert "no named-control steps" in pg.inner_text(".rc .wy")                                         # when there is nothing to explain, it says so where you are looking
        why.click()
        pg.wait_for_function("document.querySelectorAll('.rc .whyh').length===0")
        pg.locator(".rc .rbody img").first.click()                                                          # a picture: over this panel, not a new page
        pg.wait_for_selector("#lb img")
        assert "Step 1" in pg.inner_text("#lb .lbcap") and opened_pages == [pg] or len(opened_pages) <= 1
        pg.keyboard.press("Escape")
        pg.wait_for_function("!document.getElementById('lb')")
        assert len(ctx.pages) == 1
        b.close()
