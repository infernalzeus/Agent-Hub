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


def _client(tmp_path, monkeypatch):
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
            assert ag["doctor"] == {"voice": "liam", "fx": "p10", "fxs": "metal"} and ag["neo"]["voice"] == "neo-calm"      # only the doctor changed
            assert (await c.post("/api/voice/agent-voice", json={"agent": "doctor", "reset": True})).status == 200
            assert (await (await c.get("/api/voice/voices")).json())["agents"]["doctor"]["voice"] == "medic"                 # back to the built-in one
            assert (await c.post("/api/voice/agent-voice", json={"agent": "nobody", "voice": "liam"})).status == 400
            assert (await c.post("/api/voice/agent-voice", json={"agent": "neo", "voice": "not-a-voice"})).status == 400
            assert (await c.post("/api/voice/agent-voice", json={"agent": "neo", "voice": "liam", "fx": "bad value!"})).status == 400
    asyncio.run(go())


def test_speaking_uses_the_agents_voice_unless_a_voice_is_named(tmp_path, monkeypatch):
    seen = []

    class Fake:
        def __init__(self, text, voice, rate="+0%", pitch="+0Hz"):
            seen.append(voice)

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
    asyncio.run(go())
    assert seen == ["en-IE-ConnorNeural", "en-US-JennyNeural"]


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
