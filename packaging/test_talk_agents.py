"""Talk with the four core agents: one window, one speaker at a time. Smith routes; a mission he starts hands the conversation to the Orchestrator; Neo and the Doctor answer as themselves;
a name at the start of a sentence picks the speaker; every speaker still gets the dashboard and PC quick commands first."""
import asyncio
import json
from types import SimpleNamespace

from playwright.sync_api import sync_playwright

from hub.features import talk_agents as TA
from test_ui_lifecycle import hub  # noqa: F401


def _mission(status="running", **kw):
    base = dict(id="abc123def456", status=status, brief="add dark mode to the settings page", plan=[{"agent": "coder", "brief": "write the css", "status": "running"}], questions=[], created=1.0)
    base.update(kw)
    return SimpleNamespace(**base)


def _smith(text, history, mission):
    async def chat(t, h, m):
        return {"say": "Smith's router heard: " + t, "action": None, "confirm": False, "backend": "router"}
    return chat


def test_a_name_at_the_start_of_a_sentence_picks_who_answers():
    assert TA.address("Neo, draft an agent that checks invoices") == ("neo", "draft an agent that checks invoices")
    assert TA.address("hey doctor the hub is slow") == ("doctor", "the hub is slow")
    assert TA.address("Agent Smith open the dashboard") == ("smith", "open the dashboard")
    assert TA.address("neon lights are nice") == (None, "neon lights are nice")                         # a word that merely starts with a name is not an address
    assert TA.address("Orchestrator") == ("orchestrator", "")


def test_the_orchestrator_reports_a_mission_and_takes_commands_for_it(monkeypatch):
    m = _mission()
    monkeypatch.setattr(TA, "_missions", lambda: [m])
    posts = []

    async def post(path, body=None):
        posts.append((path, body))
        return {"ok": True, "status": 200}
    monkeypatch.setattr(TA, "_post", post)
    chat = _smith("", [], None)
    r = asyncio.run(TA.speak_as("orchestrator", "how is it going?", [], None, chat))
    assert r["speaker"] == "orchestrator" and "dark mode" in r["say"] and r["mission"] == m.id
    m.status = "plan_ready"
    r = asyncio.run(TA.speak_as("orchestrator", "run it", [], None, chat))
    assert posts[-1][0] == f"/api/missions/{m.id}/run-plan" and "Running the plan" in r["say"]
    m.status = "awaiting_review"
    asyncio.run(TA.speak_as("orchestrator", "apply", [], None, chat))
    assert posts[-1][0] == f"/api/missions/{m.id}/apply"
    asyncio.run(TA.speak_as("orchestrator", "stop", [], None, chat))
    assert posts[-1][0] == f"/api/missions/{m.id}/abort"


def test_the_orchestrator_asks_its_questions_one_at_a_time_then_hands_all_answers_over(monkeypatch):
    m = _mission("needs_input", questions=[{"q": "Which page?"}, {"q": "Light or dark first?", "options": ["light", "dark"]}])
    monkeypatch.setattr(TA, "_missions", lambda: [m])
    TA._PENDING.clear()
    posts = []

    async def post(path, body=None):
        posts.append((path, body))
        return {"ok": True, "status": 200}
    monkeypatch.setattr(TA, "_post", post)
    chat = _smith("", [], None)
    first = asyncio.run(TA.speak_as("orchestrator", "the settings page", [], None, chat))
    assert "Light or dark first?" in first["say"] and "light, dark" in first["say"] and not posts
    asyncio.run(TA.speak_as("orchestrator", "dark", [], None, chat))
    assert posts == [(f"/api/missions/{m.id}/answer", {"answers": [{"q": "Which page?", "a": "the settings page"}, {"q": "Light or dark first?", "a": "dark"}]})]


def test_a_new_ask_to_the_orchestrator_goes_through_smiths_router_under_its_name(monkeypatch):
    monkeypatch.setattr(TA, "_missions", lambda: [])
    r = asyncio.run(TA.speak_as("orchestrator", "please add a search box to the missions page", [], None, _smith("", [], None)))
    assert r["speaker"] == "orchestrator" and "router heard" in r["say"]


def test_the_doctor_diagnoses_a_fault_and_answers_a_question(monkeypatch):
    from hub.features import support as SUP

    async def start(text, runtime=None, model=None):
        return {"id": "m1"}
    monkeypatch.setattr(SUP, "start", start)

    async def persona(agent, brief, role=None):
        return "The Hub keeps its state in the data folder."
    monkeypatch.setattr(TA, "_persona", persona)
    r = asyncio.run(TA.speak_as("doctor", "the dashboard is broken and nothing opens", [], None, _smith("", [], None)))
    assert r["ui"] == {"doctor": True, "doctor_id": "m1"}
    r = asyncio.run(TA.speak_as("doctor", "where does the hub keep its data", [], None, _smith("", [], None)))
    assert "data folder" in r["say"] and "ui" not in r


def test_neo_drafts_an_agent_but_saves_nothing(monkeypatch):
    seen = []

    async def persona(agent, brief, role=None):
        seen.append(agent)
        return "Invoice checker: reads invoices, flags totals that do not add up."
    monkeypatch.setattr(TA, "_persona", persona)
    r = asyncio.run(TA.speak_as("neo", "create an agent that checks invoices", [], None, _smith("", [], None)))
    assert seen == ["neo"] and r["url"] == "/agents" and "Invoice checker" in r["say"] and "Agency" in r["say"]


def test_a_bare_name_greets_and_smith_with_no_words_does_not_reach_the_router(monkeypatch):
    chat = _smith("", [], None)
    assert "here" in asyncio.run(TA.speak_as("neo", "", [], None, chat))["say"].lower()
    assert asyncio.run(TA.speak_as("smith", "", [], None, chat))["say"] == "Here."


def test_the_talk_window_sends_the_chosen_speaker_and_a_mission_hands_it_to_the_orchestrator(hub):
    sent = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 1280, "height": 800}).new_page()

        def chat(route):
            body = route.request.post_data_json
            sent.append(body.get("speaker"))
            who = body.get("speaker")
            route.fulfill(json={"say": "ok from " + who, "action": {"id": "start_mission", "args": {"project": "p", "text": "t"}} if who == "smith" else None, "confirm": False, "speaker": who, "backend": "x"})
        pg.route("**/api/voice/chat", chat)
        pg.route("**/api/voice/act", lambda r: r.fulfill(json={"say": "Started.", "handoff": "orchestrator", "mission": "abc123def456"}))
        pg.route("**/api/voice/speak", lambda r: r.fulfill(status=503, body="no voice in a test"))
        pg.goto(hub + "/?enter=1")
        pg.wait_for_function("!!window.__hubBoard && !!window.__hubBoard.active && !!window.HubVoice", timeout=20000)
        pg.evaluate("document.getElementById('voice').hidden=false")
        chips = pg.locator("#v-who [data-who]")
        assert chips.count() == 4 and pg.locator("#v-who .on").get_attribute("data-who") == "smith"
        pg.locator("#v-who [data-who=neo]").click(force=True)
        pg.evaluate("HubVoice.ask('what agents do I have'); void 0")
        pg.wait_for_function("document.querySelectorAll('#v-log .v-msg.hub').length>=1", timeout=8000)
        assert sent[-1] == "neo"
        pg.locator("#v-who [data-who=smith]").click(force=True)
        pg.evaluate("HubVoice.ask('add a search box to missions'); void 0")                       # Smith's router starts a mission ...
        pg.wait_for_function("document.querySelector('#v-who .on').dataset.who==='orchestrator'", timeout=10000)   # ... and the Orchestrator takes the conversation
        assert sent[-1] == "smith"
        b.close()


def test_viktor_is_the_orchestrators_name_and_orchestrator_his_designation():
    assert TA.NAME["orchestrator"] == "Viktor" and TA.DESIGNATION["orchestrator"] == "Orchestrator"
    for said in ("Viktor", "Victor", "Viktor, what is running", "hey viktor the orchestrator", "Orchestrator what is running", "Agent Viktor stop"):
        assert TA.address(said)[0] == "orchestrator", said


def test_asking_for_an_agent_moves_the_conversation_and_a_question_about_one_does_not():
    want = {"Smith, pull up Viktor": ("orchestrator", ""), "can I talk to Neo": ("neo", ""), "get the doctor": ("doctor", ""), "put Viktor on": ("orchestrator", ""),
            "switch to the orchestrator": ("orchestrator", ""), "Hey Smith, can you bring up Viktor please": ("orchestrator", ""), "call the doctor": ("doctor", ""),
            "get Neo to draft an agent that checks invoices": ("neo", "draft an agent that checks invoices"), "ask Viktor to run the plan": ("orchestrator", "run the plan"),
            "I want to speak with the Doctor about the slow dashboard": ("doctor", "the slow dashboard")}
    for said, (to, rest) in want.items():
        got = TA.summon(said, "smith")
        assert got and got["to"] == to and got["rest"] == rest and got["from"] == "smith", (said, got)
    for said in ("what does Neo do", "Neo", "play my playlist", "call mum", "get the weather in Leeds", "Doctor, why is it slow", "put Neo's name in the list"):
        assert TA.summon(said, "smith") is None, said
    assert TA.summon("talk to Smith", "smith")["same"] is True


def test_the_talk_window_moves_from_smith_to_viktor_with_a_line_from_each(hub):
    """The real chat route and the real window: nothing stubbed but the voice."""
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 1280, "height": 800}).new_page()
        pg.route("**/api/voice/speak", lambda r: r.fulfill(status=503, body="no voice in a test"))
        pg.goto(hub + "/?enter=1")
        pg.wait_for_function("!!window.__hubBoard && !!window.__hubBoard.active && !!window.HubVoice", timeout=20000)
        pg.evaluate("document.getElementById('voice').hidden=false")
        pg.wait_for_function("document.getElementById('v-name').textContent==='SMITH'", timeout=5000)
        pg.evaluate("HubVoice.ask('Smith, pull up Viktor'); void 0")
        pg.wait_for_function("document.querySelector('#v-who .on').dataset.who==='orchestrator'", timeout=10000)
        pg.wait_for_function("document.getElementById('v-name').textContent==='VIKTOR'", timeout=5000)
        face_on_board = pg.evaluate("(document.querySelector('.talk-btn img')||{}).src||''")
        got = pg.evaluate("""()=>({role:document.getElementById('v-role').textContent,face:document.getElementById('v-face').getAttribute('src'),chip:document.querySelector('#v-who [data-who=orchestrator]').textContent,
          log:[...document.querySelectorAll('#v-log .v-msg')].map(e=>e.textContent)})""")
        b.close()
    assert got["role"] == "Orchestrator" and got["face"].endswith("/orchestrator.png") and got["chip"] == "VIKTOR", got
    assert face_on_board.endswith("/static/agent-icons/orchestrator.png") or face_on_board == "", face_on_board          # the Talk button on the board wears his face (when the board has one)
    text = " | ".join(got["log"])
    assert "bring in Viktor" in text and "Viktor here" in text, text                                   # Smith says he is bringing Viktor in, then Viktor speaks


def test_each_of_the_four_agents_has_a_preset_selector_in_the_talk_window_and_on_the_agency_page(hub):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 1280, "height": 900}).new_page()
        pg.route("**/api/voice/speak", lambda r: r.fulfill(status=503, body="no voice in a test"))
        pg.goto(hub + "/?enter=1")
        pg.wait_for_function("!!window.__hubBoard && !!window.__hubBoard.active && !!window.HubVoice", timeout=20000)
        pg.evaluate("document.getElementById('voice').hidden=false")
        pg.wait_for_function("document.querySelectorAll('#v-preset option').length>=7", timeout=8000)
        pg.locator("#v-who [data-who=neo]").click(force=True)
        pg.select_option("#v-preset", "varied")
        pg.wait_for_timeout(400)
        pg.goto(hub + "/agents")
        pg.wait_for_selector(".ag-entry", timeout=15000)
        pg.wait_for_function("document.querySelectorAll('[data-agent-preset]').length>=4", timeout=8000)
        roles = pg.evaluate("[...document.querySelectorAll('[data-agent-preset]')].map(s=>s.dataset.agentPreset+':'+s.value)")
        b.close()
    assert sorted(r.split(":")[0] for r in roles) == ["doctor", "neo", "orchestrator", "smith"] and "neo:varied" in roles, roles
    assert (__import__("json").loads(__import__("urllib.request", fromlist=["x"]).urlopen(hub + "/api/agents/presets").read())["choices"]).get("neo") == "varied"
