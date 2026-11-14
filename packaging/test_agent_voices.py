"""Each core agent has its own voice (and robotic layer), picked in the Talk window, kept on the Hub, and TEST VOICE says what is typed with it."""
import asyncio
import json
import sys

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from playwright.sync_api import sync_playwright

from hub import runtime as RT
from hub.features import voice as V
from test_ui_lifecycle import hub  # noqa: F401


FAKE_CATALOG = [{"id": "x:de-DE-ChristophNeural", "n": "Christoph", "l": "de-DE", "g": "Male", "lang": "German (Germany)"},
                {"id": "x:en-GB-OliverNeural", "n": "Oliver", "l": "en-GB", "g": "Male", "lang": "English (United Kingdom)"}]


def _client(tmp_path, monkeypatch):
    async def fake_catalog():
        return FAKE_CATALOG
    monkeypatch.setattr(V, "voice_catalog", fake_catalog)
    monkeypatch.setattr(RT, "STATE", tmp_path)
    app = web.Application()
    app.add_routes(V.routes)
    return TestClient(TestServer(app))


def test_every_core_agent_starts_with_a_different_voice_a_saved_choice_sticks_and_reset_undoes_it(tmp_path, monkeypatch):
    async def go():
        async with _client(tmp_path, monkeypatch) as c:
            j = await (await c.get("/api/voice/voices")).json()
            ag = j["agents"]
            assert set(ag) == {"smith", "orchestrator", "neo", "doctor"} and len({a["voice"] for a in ag.values()}) == 4
            ids = {v["id"] for v in j["voices"]}
            assert all(a["voice"] in ids for a in ag.values()) and len(ids) >= 20
            assert set(j["recommended"]) == set(ag) and all(r["voice"] in ids and r["note"] for r in j["recommended"].values())      # each character has a stated ideal
            r = await c.post("/api/voice/agent-voice", json={"agent": "doctor", "voice": "liam", "fx": "p10", "fxs": "metal"})
            assert r.status == 200
            ag = (await (await c.get("/api/voice/voices")).json())["agents"]
            assert {k: ag["doctor"][k] for k in ("voice", "fx", "fxs")} == {"voice": "liam", "fx": "p10", "fxs": "metal"} and ag["neo"]["voice"] == "neo-calm"      # only the doctor changed
            assert (await c.post("/api/voice/agent-voice", json={"agent": "doctor", "reset": True})).status == 200
            assert (await (await c.get("/api/voice/voices")).json())["agents"]["doctor"]["voice"] == "medic"                 # back to the built-in one
            r = await c.post("/api/voice/agent-voice", json={"agent": "orchestrator", "line": "I am more than I ever was, truly.", "delivery": {"on": True, "pace": -99, "pauses": 9}})        # a test line and delivery without a voice
            assert r.status == 200
            vk = (await (await c.get("/api/voice/voices")).json())["agents"]["orchestrator"]
            assert vk["line"] == "I am more than I ever was, truly." and vk["delivery"] == {"on": True, "pace": -20, "pauses": 2.5} and vk["voice"] == "viktor-soft"      # kept, clamped, and the voice untouched
            assert j["catalog"] == FAKE_CATALOG
            r = await c.post("/api/voice/agent-voice", json={"agent": "doctor", "voice": "x:de-DE-ChristophNeural", "fx": "off"})                 # any voice Microsoft offers can be chosen
            assert r.status == 200 and (await (await c.get("/api/voice/voices")).json())["agents"]["doctor"]["voice"] == "x:de-DE-ChristophNeural"
            assert (await c.post("/api/voice/agent-voice", json={"agent": "doctor", "voice": "x:../etc/passwd"})).status == 400
            assert (await c.post("/api/voice/agent-voice", json={"agent": "nobody", "voice": "liam"})).status == 400
            assert (await c.post("/api/voice/agent-voice", json={"agent": "neo", "voice": "not-a-voice"})).status == 400
            assert (await c.post("/api/voice/agent-voice", json={"agent": "neo", "voice": "liam", "fx": "bad value!"})).status == 400
    asyncio.run(go())


def test_speaking_uses_the_agents_voice_unless_a_voice_is_named(tmp_path, monkeypatch):
    seen = []

    class Fake:
        def __init__(self, text, voice, rate="+0%", pitch="+0Hz"):
            seen.append(voice if voice != "en-AU-WilliamMultilingualNeural" else (voice, rate, pitch))

        async def stream(self):
            yield {"type": "audio", "data": b"ID3audio"}
    import edge_tts
    monkeypatch.setattr(edge_tts, "Communicate", Fake)
    monkeypatch.setattr(V, "_TTS_CACHE", {})

    async def go():
        async with _client(tmp_path, monkeypatch) as c:
            await c.post("/api/voice/agent-voice", json={"agent": "neo", "voice": "connor"})
            assert (await c.post("/api/voice/speak", json={"text": "hello there", "agent": "neo"})).status == 200
            assert (await c.post("/api/voice/speak", json={"text": "hello again", "agent": "neo", "voice": "jenny"})).status == 200      # the test box names a voice: it wins
            assert (await c.post("/api/voice/speak", json={"text": "more", "voice": "smith", "rate": -22, "pitch": -6})).status == 200       # shaped delivery: a slower, lower phrase
    asyncio.run(go())
    assert seen == ["en-IE-ConnorNeural", "en-US-JennyNeural", ("en-AU-WilliamMultilingualNeural", "-22%", "-28Hz")]      # Smith: rate 0 and pitch -22 moved by -22% and -6Hz


def test_the_voice_test_panel_speaks_custom_text_in_the_chosen_voice_and_only_saves_on_set_as_default(hub):
    spoken, saved = [], []
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 1280, "height": 900}).new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.route("**/api/voice/speak", lambda r: (spoken.append(r.request.post_data_json), r.fulfill(status=503, body="no voice in a test"))[1])
        pg.on("request", lambda rq: saved.append(rq.post_data_json) if rq.url.endswith("/api/voice/agent-voice") else None)
        pg.goto(hub + "/?enter=1")
        pg.wait_for_function("!!window.HubVoice && document.querySelectorAll('#v-voice option').length>=20", timeout=20000)
        pg.evaluate("document.getElementById('voice').hidden=false")
        assert pg.locator("#v-lab").is_hidden()
        pg.locator("#v-labbtn").click(force=True)
        assert pg.locator("#v-lab").is_visible()
        pg.locator("#v-lab-who [data-lab=neo]").click(force=True)
        pg.wait_for_function("document.getElementById('v-voice').value==='neo-calm'")
        pg.select_option("#v-voice", "liam")
        pg.fill("#v-lab-text", "Testing one two three")
        pg.locator("#v-test").click(force=True)
        pg.wait_for_function("document.getElementById('v-lab-st').textContent.startsWith('No audio')", timeout=8000)      # the fake service said no: the panel says so
        assert saved == []                                                                      # speaking a test saves nothing
        pg.locator("#v-lab-save").click(force=True)
        pg.wait_for_function("document.getElementById('v-lab-st').textContent.includes('from now on')")
        pg.locator("#v-lab-who [data-lab=doctor]").click(force=True)
        pg.wait_for_function("document.getElementById('v-voice').value==='medic'")                 # the doctor has his own
        pg.locator("#v-lab-who [data-lab=neo]").click(force=True)
        pg.wait_for_function("document.getElementById('v-voice').value==='liam'")                  # and Neo's choice stayed
        pg.locator("#v-lab-rec").click(force=True)
        assert pg.input_value("#v-voice") == "neo-calm"                                         # RECOMMENDED fills the ideal in
        assert pg.input_value("#v-in") == ""                                                    # nothing touched the chat box
        pg.locator("#v-lab-reset").click(force=True)
        pg.wait_for_function("document.getElementById('v-lab-st').textContent.includes('built-in')")
        b.close()
    assert errors == []
    assert [s for s in saved if s.get("voice")] == [{"agent": "neo", "voice": "liam", "fx": "off", "fxs": "radio"}] or any(s.get("agent") == "neo" and s.get("voice") == "liam" for s in saved), saved
    assert any(s and s.get("text") == "Testing one two three" and s.get("voice") == "liam" and s.get("agent") == "neo" for s in spoken), spoken


def test_a_typed_test_line_stays_with_its_agent_and_shaped_phrasing_asks_phrase_by_phrase(hub):
    spoken = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 1280, "height": 900}).new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.route("**/api/voice/speak", lambda r: (spoken.append(r.request.post_data_json), r.fulfill(status=503, body="no voice in a test"))[1])
        pg.goto(hub + "/?enter=1")
        pg.wait_for_function("!!window.HubVoice && document.querySelectorAll('#v-voice option').length>=20", timeout=20000)
        pg.evaluate("document.getElementById('voice').hidden=false")
        pg.locator("#v-labbtn").click(force=True)
        pg.locator("#v-lab-who [data-lab=orchestrator]").click(force=True)
        assert pg.input_value("#v-lab-text") == "I am more than I ever was."                    # each agent starts with a line of its own
        pg.fill("#v-lab-text", "I am... *more* than I ever was.")
        pg.wait_for_timeout(900)                                                                 # saved a moment after typing stops
        pg.locator("#v-lab-who [data-lab=doctor]").click(force=True)
        assert "Hold still" in pg.input_value("#v-lab-text")                                     # the Doctor's line is not Viktor's
        pg.locator("#v-lab-who [data-lab=orchestrator]").click(force=True)
        assert pg.input_value("#v-lab-text") == "I am... *more* than I ever was."                # and Viktor's stayed
        pg.reload()
        pg.wait_for_function("document.querySelectorAll('#v-voice option').length>=20", timeout=20000)
        pg.evaluate("document.getElementById('voice').hidden=false")
        pg.locator("#v-labbtn").click(force=True)
        pg.locator("#v-lab-who [data-lab=orchestrator]").click(force=True)
        assert pg.input_value("#v-lab-text") == "I am... *more* than I ever was."                # kept on the Hub, not in this page
        pg.check("#v-del-on")
        pg.locator("#v-test").click(force=True)
        pg.wait_for_function("document.getElementById('v-lab-st').textContent.startsWith('No audio')", timeout=8000)
        b.close()
    assert errors == []
    texts = [s["text"] for s in spoken]
    assert len(spoken) >= 2 and "more" in texts and any(t.startswith("I am") for t in texts), texts      # cut into phrases, the starred word on its own
    more = next(s for s in spoken if s["text"] == "more")
    assert more.get("rate", 0) < 0 and more.get("pitch", 0) < 0                                    # leaned on: slower and lower


def test_dramatic_pauses_break_a_plain_sentence_and_choosing_an_agent_does_not_scroll_the_open_voice_panel(hub):
    spoken = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block", viewport={"width": 900, "height": 520}).new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.route("**/api/voice/speak", lambda r: (spoken.append(r.request.post_data_json), r.fulfill(status=503, body="no voice in a test"))[1])
        pg.goto(hub + "/?enter=1")
        pg.wait_for_function("!!window.HubVoice && document.querySelectorAll('#v-voice option').length>=20", timeout=25000)
        pg.evaluate("document.getElementById('voice').hidden=false")
        pg.locator("#v-labbtn").click(force=True)
        pg.fill("#v-lab-text", "I am more than I ever was")                                      # no comma, no dash, no full stop
        pg.check("#v-del-on")
        pg.select_option("#v-del-pauses", "2.3")
        pg.locator("#v-test").click(force=True)
        pg.wait_for_function("document.getElementById('v-lab-st').textContent.startsWith('No audio')", timeout=8000)
        before = pg.evaluate("[document.getElementById('voice').scrollTop, scrollY]")
        pg.evaluate("document.querySelector('#v-who [data-who=neo]').click()")                   # a script click: Playwright's own click would scroll the button into view and hide the bug
        pg.wait_for_timeout(500)
        after = pg.evaluate("[document.getElementById('voice').scrollTop, scrollY]")
        has_groups = pg.evaluate("document.querySelectorAll('#v-voice optgroup').length")
        b.close()
    assert errors == []
    assert len(spoken) >= 3 and spoken[0]["text"].startswith("I am"), [s["text"] for s in spoken]      # broken at "than" and in the middle of what is left
    assert before == after, (before, after)
    assert has_groups >= 1


def test_a_kokoro_voice_on_this_pc_can_be_chosen_and_speaks_through_the_worker_or_falls_back_to_microsoft(tmp_path, monkeypatch):
    from hub.features import kokoro_tts as KT
    monkeypatch.setattr(KT, "voices", lambda: [{"id": "k:am_onyx", "name": "Onyx · Kokoro, on this PC, American male", "voice": "am_onyx"}])
    calls = []

    async def fake_synth(text, voice, speed=1.0):
        calls.append((text, voice, round(speed, 2)))
        if text == "break":
            raise RuntimeError("worker died")
        return b"RIFFfakewav"
    monkeypatch.setattr(KT, "synth", fake_synth)

    class Fake:
        def __init__(self, text, voice, rate="+0%", pitch="+0Hz"):
            self.v = voice

        async def stream(self):
            yield {"type": "audio", "data": b"ID3audio"}
    import edge_tts
    monkeypatch.setattr(edge_tts, "Communicate", Fake)
    monkeypatch.setattr(V, "_TTS_CACHE", {})

    async def go():
        async with _client(tmp_path, monkeypatch) as c:
            j = await (await c.get("/api/voice/voices")).json()
            assert j["kokoro"] == [{"id": "k:am_onyx", "name": "Onyx · Kokoro, on this PC, American male"}]
            assert (await c.post("/api/voice/agent-voice", json={"agent": "neo", "voice": "k:am_onyx"})).status == 200
            assert (await c.post("/api/voice/agent-voice", json={"agent": "neo", "voice": "k:not_here"})).status == 400
            r = await c.post("/api/voice/speak", json={"text": "hello", "agent": "neo", "rate": -10})
            assert r.status == 200 and r.content_type == "audio/wav" and await r.read() == b"RIFFfakewav"
            assert calls == [("hello", "am_onyx", 0.9)]                                      # rate -10 % is a speed of 0.9
            r2 = await c.post("/api/voice/speak", json={"text": "hello", "agent": "neo", "rate": -10})
            assert r2.headers.get("X-Voice-Cached") == "1" and len(calls) == 1                # the second time is from memory
            r3 = await c.post("/api/voice/speak", json={"text": "break", "agent": "neo"})
            assert r3.status == 200 and r3.content_type == "audio/mpeg"                       # the worker failed: Microsoft's voice says it instead
    asyncio.run(go())


def test_asking_for_an_agent_is_a_rule_not_a_model_call(tmp_path):
    """"Bring Victor" took 12 to 35 s on the model (13 Nov log): every wording below is now caught by the rule that answers in milliseconds."""
    from hub.features import talk_agents as TA
    for text, who in [("Bring Victor.", "orchestrator"), ("Can you bring Victor?", "orchestrator"), ("I would like to speak to the Agent Victor.", "orchestrator"),
                      ("get the agent neo please", "neo"), ("bring me the doctor", "doctor"), ("summon Neo", "neo"), ("Smith, pull up Viktor", "orchestrator"), ("give me Smith", "smith")]:
        got = TA.summon(text, "smith")
        assert got and got["to"] == who, (text, got)
    for text in ("what is Neo doing", "bring up the dashboard", "show me the dashboard"):
        assert TA.summon(text, "smith") is None, text                                 # a question about an agent, or about something else, is not a request for one
