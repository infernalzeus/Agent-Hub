"""The practice yard: the pretend apps are exact, the real agent runs against them, the learner learns, and it never reaches outside itself."""
import asyncio
import json
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from hub.features import desktop_agent as DA
from hub.yard import api, learner as L, practice as P
from hub.yard.world import APP, FAMILIES, World


def _nodes(w):
    return asyncio.run(w.tree())


def test_the_goal_names_a_control_the_agent_lists_even_deep_in_a_long_list():
    # before the fix the list cap ran before the ranking, so entry 20 of 30 was never shown to the model
    w = World("long", 1)
    assert w.items.index(w.target) >= 18
    assert any(c["node"]["name"] == w.target for c in DA.controls(_nodes(w), APP, w.goal))


def test_a_control_with_no_name_is_never_listed_and_the_diagnosis_says_so():
    w = World("unnamed", 1)
    asyncio.run(w.click(*sorted(w.needed())[0]))                       # open the playlist page
    assert not any(c["node"]["name"] == "" for c in DA.controls(_nodes(w), APP, w.goal))
    assert P.cause(w) == "a control with no name is never listed"


@pytest.mark.parametrize("family", [f for f in FAMILIES if f != "unnamed"])
def test_every_visible_family_can_be_won_by_following_the_needed_controls(family):
    w = World(family, 3)
    for _ in range(8):
        need = w.needed()
        if not need:
            break
        x, y = sorted(need)[0]
        node = next(n for n in _nodes(w) if (n.get("x"), n.get("y")) == (x, y))
        asyncio.run(w.type_(w.target, [x, y]) if node["control"] == "edit" else w.click(x, y))
    assert w.success()


def test_pressing_the_players_own_play_does_nothing_and_a_wrong_playlist_is_not_a_win():
    w = World("direct", 2)
    bar_play = next(n for n in _nodes(w) if n["name"] == "Play")
    asyncio.run(w.click(bar_play["x"], bar_play["y"]))
    assert w.playing is None and not w.success()


def test_the_pretend_app_state_not_the_agents_word_decides_success():
    w = World("direct", 4)
    res = P.run_episode(w, L.random_policy(1))
    assert res["success"] == w.success()


def test_a_learner_trained_for_a_short_time_beats_the_rule_of_thumb_on_apps_it_never_saw():
    lr, curve = P.train(1500, hidden=0, seed=0)
    fams = [f for f in FAMILIES if f != "unnamed"]
    learned = P.evaluate(lambda: lr.policy(False), 10, fams)
    rule = P.evaluate(lambda: L.greedy_policy, 10, fams)
    mean = lambda t: np.mean([t[f]["train"]["success"] for f in fams])
    assert mean(learned) > mean(rule) + 0.2
    assert curve[-1][1] > curve[0][1]


def test_a_policy_only_ever_chooses_what_the_agents_own_parser_accepts():
    pol = L.Learner(seed=1).policy(True)
    bad = sum(P.run_episode(World(f, k), pol)["invalid"] for k, f in enumerate(FAMILIES * 4))
    assert bad == 0 and all(r["a"] < len(r["p"]) for r in pol.records)


def test_practice_without_write_leaves_no_file_and_does_not_touch_the_learning_log(tmp_path, monkeypatch):
    from hub.features import learning
    monkeypatch.setattr(learning, "CHOICES", tmp_path / "choices.jsonl")
    monkeypatch.setattr(P, "REPORT", tmp_path / "yard" / "report.json")
    P.practice(episodes=100, n_eval=2, write=False)
    assert not (tmp_path / "yard").exists() and not (tmp_path / "choices.jsonl").exists()


def test_status_works_before_any_run_and_reads_a_report(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "REPORT", tmp_path / "report.json")
    assert api.status()["ran"] is False
    (tmp_path / "report.json").write_text(json.dumps({"means": {"x": 1}}))
    assert api.status()["report"] == {"means": {"x": 1}}


from test_ui_lifecycle import hub  # noqa: E402,F401  (an isolated Hub on its own state folder)


def test_a_running_hub_serves_the_yard_status(hub):
    import urllib.request
    d = json.load(urllib.request.urlopen(hub + "/api/yard/status"))
    assert d["ready"] is True and d["max_episodes"] == api.MAX_EPISODES


# ---- shadow mode: what the trained policy would have pressed, recorded beside the live agent, never altering it
@pytest.fixture
def shadowed(tmp_path, monkeypatch):
    from hub.yard import shadow as SH
    monkeypatch.setattr(SH, "DIR", tmp_path)
    monkeypatch.setattr(SH, "POLICY", tmp_path / "policy.json")
    monkeypatch.setattr(SH, "LOG", tmp_path / "shadow.jsonl")
    monkeypatch.setitem(SH._CACHE, "mtime", None)
    from hub.yard import settings as YS
    monkeypatch.setattr(YS, "FILE", tmp_path / "settings.json")
    monkeypatch.setitem(YS._CACHE, "at", 0.0)
    monkeypatch.delenv("HUB_YARD_SHADOW", raising=False)
    YS.update({"shadow": True})                                  # off by default now: the test switches it on, as the R panel does
    lr, _ = P.train(1200, hidden=0, seed=0)
    (tmp_path / "policy.json").write_text(json.dumps({"linear": lr.actor.dump()}))
    return SH


def _agent_run(world, decide, shadow=True):
    return asyncio.run(DA.attempt(world.goal, APP, decide, tree=world.tree, media=world.media, click=world.click, type_=world.type_, key=world.key,
                                  settle=0, shadow=shadow))


def test_shadow_writes_what_the_policy_would_do_beside_what_the_agent_did_and_changes_nothing(shadowed):
    a, b = World("menu", 11), World("menu", 11)
    plain = _agent_run(a, L.greedy_policy, shadow=False)
    watched = _agent_run(b, L.greedy_policy, shadow=True)
    assert [t.get("do") for t in plain["trace"]] == [t.get("do") for t in watched["trace"]] and plain["ok"] == watched["ok"] and a.success() == b.success()
    rows = [json.loads(l) for l in shadowed.LOG.read_text().splitlines()]
    steps = [r for r in rows if r["kind"] == "step"]
    assert len(steps) == len(watched["trace"]) and {"live", "would", "agree"} <= set(steps[0])
    assert rows[-1]["kind"] == "result" and rows[-1]["ok"] == watched["ok"]
    s = shadowed.summary()
    assert s["steps"] == len(steps) and s["tasks"] == 1


def test_shadow_writes_nothing_without_a_trained_policy_or_when_switched_off(shadowed, monkeypatch):
    shadowed.POLICY.unlink()
    _agent_run(World("direct", 2), L.greedy_policy)
    assert not shadowed.LOG.exists()
    shadowed.POLICY.write_text(json.dumps({"linear": L.Learner().actor.dump()}))
    monkeypatch.setenv("HUB_YARD_SHADOW", "0")
    _agent_run(World("direct", 2), L.greedy_policy)
    assert not shadowed.LOG.exists()


def test_a_broken_policy_file_never_breaks_a_task(shadowed):
    shadowed.POLICY.write_text("{not json")
    res = _agent_run(World("direct", 5), L.greedy_policy)
    rows = [json.loads(l) for l in shadowed.LOG.read_text().splitlines()] if shadowed.LOG.exists() else []
    assert res["trace"] and not any(r["kind"] == "step" for r in rows)       # no step is noted, and the task ran as usual


def test_shadow_costs_the_agent_under_five_milliseconds_a_step(shadowed):
    import time
    w = World("direct", 7)
    asyncio.run(w.tree())
    o = L.parse(DA.brief(w.goal, APP, DA.controls(_nodes(w), APP, w.goal), [], [], 0))
    t0 = time.perf_counter()
    for _ in range(50):
        shadowed.note(w.goal, APP, DA.brief(w.goal, APP, DA.controls(_nodes(w), APP, w.goal), [], [], 0), {"do": "click", "control": {"id": 1}}, 0)
    assert (time.perf_counter() - t0) / 50 < 0.005
    assert o["controls"]


def test_the_practice_page_is_served_and_the_board_offers_it_as_a_tab(hub):
    import urllib.request
    html = urllib.request.urlopen(hub + "/yard").read().decode()
    assert "Reinforcement learning" in html and "/api/yard/practice" in html and "/api/yard/status" in html
    board = (Path(__file__).resolve().parents[1] / "hub" / "static" / "home-board.js").read_text(encoding="utf-8")
    assert "['REINFORCEMENT LEARNING', '/yard']" in board


def test_the_practice_tab_opens_the_page_inside_the_board_and_a_run_fills_its_tables(hub):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block").new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(hub + "/?enter=1")
        pg.wait_for_function("!!(window.__hubBoard && __hubBoard.active)")
        assert pg.evaluate("__hubBoard.open('/yard')")
        pg.wait_for_function("[...document.querySelectorAll('.hk-fr')].some(f => f.src.includes('/yard'))")
        assert "REINFORCEMENT LEARNING" in pg.inner_text(".hk[data-id='card:oc']")
        page = b.new_context(service_workers="block").new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(hub + "/yard")
        page.evaluate("fetch('/api/yard/knobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({eval_per_cell:4})})")
        assert page.evaluate("fetch('/api/yard/practice',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirm:true,episodes:100})}).then(r=>r.status)") == 200
        page.reload()
        page.wait_for_function("document.getElementById('result').textContent.includes('Last session')", timeout=20000)
        assert "learned" in page.inner_text("#result") and "rule of thumb" in page.inner_text("#result") and "random" in page.inner_text("#result")
        page.evaluate("fetch('/api/yard/knobs/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})")
        b.close()
    assert errors == []


def test_the_two_switches_stop_notes_at_once_and_environment_still_wins(tmp_path, monkeypatch):
    from hub.features import learning
    from hub.yard import settings as S, shadow
    monkeypatch.setattr(S, "FILE", tmp_path / "settings.json")
    monkeypatch.delenv("HUB_LEARNING_LOG", raising=False)
    monkeypatch.delenv("HUB_YARD_SHADOW", raising=False)
    S._CACHE["at"] = 0.0
    assert not learning.enabled() and not shadow.enabled()                           # EXPERIMENTAL: off by default
    S.update({"learning": True, "junk": True, "shadow": "no"})                       # a non-boolean is ignored
    assert learning.enabled() and not shadow.enabled()
    S.update({"learning": False})
    assert not learning.enabled() and not shadow.enabled()
    S.update({"learning": True, "shadow": True})
    assert learning.enabled() and shadow.enabled()
    monkeypatch.setenv("HUB_YARD_SHADOW", "0")
    assert not shadow.enabled() and S.current()["shadow"]["forced_off_by_environment"]


def test_the_settings_endpoint_flips_a_switch_and_refuses_nonsense(tmp_path, monkeypatch):
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
    from hub.yard import settings as S
    monkeypatch.setattr(S, "FILE", tmp_path / "settings.json")
    monkeypatch.delenv("HUB_LEARNING_LOG", raising=False)
    monkeypatch.delenv("HUB_YARD_SHADOW", raising=False)           # tools/conftest.py pins shadow off for the whole run
    S._CACHE["at"] = 0.0

    async def go():
        app = web.Application(); app.add_routes(api.routes)
        async with TestClient(TestServer(app)) as c:
            assert (await (await c.get("/api/yard/settings")).json())["learning"]["on"] is False       # off by default
            j = await (await c.post("/api/yard/settings", json={"learning": True})).json()
            assert j["learning"]["on"] is True and j["shadow"]["on"] is False
            assert (await c.post("/api/yard/settings", json={"learning": "off"})).status == 400
    asyncio.run(go())


def test_the_r_panel_has_four_tabs_with_the_flow_inside_the_yard_and_a_session_can_be_stopped(hub):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 1250, "height": 850}).new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.goto(hub + "/yard")
        assert [t.strip() for t in pg.locator(".tabs button").all_inner_texts()] == ["YARD", "TEACH", "ROUTINES", "SCORES"]          # nothing else: no overview, flow, knobs or status tab
        pg.wait_for_function("document.querySelectorAll('#flowsvg .fnode').length===22")            # the flow is part of the yard
        assert pg.locator("#stop").is_hidden() and pg.locator(".infobox").count() == 0 and "i" not in pg.locator("button.i").all_inner_texts()
        pg.evaluate("fetch('/api/yard/knobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({episodes:3000})})")
        pg.click("#go")
        pg.wait_for_selector("#stop", state="visible", timeout=8000)
        pg.wait_for_function("document.querySelector('#phase').textContent.length>0", timeout=8000)       # a phase and a percentage while it runs
        pg.click("#stop")
        pg.wait_for_function("/Stopped/.test(document.querySelector('#msg').textContent)", timeout=20000)
        pg.wait_for_function("document.getElementById('stop').hidden && !document.getElementById('go').disabled", timeout=10000)
        pg.evaluate("fetch('/api/yard/knobs/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})")
        pg.click("[data-tab=teach]")
        pg.wait_for_function("!!document.getElementById('teachframe').src")
        pg.click("[data-tab=scores]")
        pg.wait_for_function("document.querySelectorAll('#fit tr').length>=5 && document.querySelectorAll('#chal tr').length>=7")
        b.close()
    assert errors == []
