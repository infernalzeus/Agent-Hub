"""Talk's speech must start as soon as it can: the first sentence plays while the rest is still being made, and a "working on it" line never holds an answer up.
The voice service is replaced inside the page by a stub that records when each request was made and answers after a chosen delay."""
import sys

import pytest

sys.path.insert(0, "packaging")
from playwright.sync_api import sync_playwright  # noqa: E402
from test_ui_lifecycle import hub  # noqa: E402,F401

STUB = """
(() => {
  window.__log = []; window.__starts = []; window.__cfg = { speak: [300, 1200], act: 0, say: 'x', action: null };
  const realStart = AudioBufferSourceNode.prototype.start;
  AudioBufferSourceNode.prototype.start = function (...a) { window.__starts.push(Math.round(performance.now() - window.__t0)); return realStart.apply(this, a); };
  const wav = () => { const n = 800, b = new ArrayBuffer(44 + n * 2), v = new DataView(b);
    const w = (o, s) => [...s].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
    w(0, 'RIFF'); v.setUint32(4, 36 + n * 2, true); w(8, 'WAVEfmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, 8000, true);
    v.setUint32(28, 16000, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true); w(36, 'data'); v.setUint32(40, n * 2, true); return b; };
  const realFetch = window.fetch.bind(window);
  window.fetch = async (url, opts) => {
    const u = String(url), at = Math.round(performance.now() - window.__t0), sleep = (ms) => new Promise((r) => setTimeout(r, ms));
    if (u.includes('/api/voice/chat')) return new Response(JSON.stringify({ say: window.__cfg.say, action: window.__cfg.action, confirm: false }), { headers: { 'Content-Type': 'application/json' } });
    if (u.includes('/api/voice/act')) { await sleep(window.__cfg.act); return new Response(JSON.stringify({ say: window.__cfg.answer || 'Done.' }), { headers: { 'Content-Type': 'application/json' } }); }
    if (u.includes('/api/voice/speak')) { const text = JSON.parse(opts.body).text; const k = window.__log.filter((x) => x.kind === 'speak').length;
      window.__log.push({ kind: 'speak', at, text }); await sleep(window.__cfg.speak[Math.min(k, window.__cfg.speak.length - 1)]); return new Response(wav(), { headers: { 'Content-Type': 'audio/wav' } }); }
    return realFetch(url, opts);
  };
})();
"""


@pytest.fixture
def talk(hub):
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--autoplay-policy=no-user-gesture-required"])
        pg = b.new_context(service_workers="block").new_page()
        pg.add_init_script(STUB)
        pg.goto(hub + "/?enter=1")
        pg.wait_for_function("!!window.HubVoice")
        pg.evaluate("window.__t0 = performance.now()")
        yield pg
        b.close()


def test_the_first_sentence_is_made_alone_and_plays_before_the_rest_is_ready(talk):
    talk.evaluate("""window.__cfg.say = 'Opening the ADHD playlist in Apple Music. It started on the first try and the media session confirms it is playing. Tell me if you want the next one.';
                     window.__cfg.speak = [300, 1500, 1500]; HubVoice.ask('hello')""")
    talk.wait_for_function("window.__starts.length >= 1", timeout=8000)
    log = talk.evaluate("window.__log")
    assert log[0]["text"] == "Opening the ADHD playlist in Apple Music."                    # alone, so it is quick to make
    assert len(log) == 2 and max(x["at"] for x in log) - min(x["at"] for x in log) < 250   # the rest are already being made, side by side
    first = talk.evaluate("window.__starts[0]")
    assert first < 900, first                                                              # about the first sentence's time (300 ms), not the whole answer's (1.5 s)


def test_a_working_line_never_holds_the_answer_up(talk):
    talk.evaluate("""window.__cfg.say = 'On it.'; window.__cfg.action = { id: 'desktop_task', args: {} }; window.__cfg.act = 3600;
                     window.__cfg.answer = 'Done. It is playing now.'; window.__cfg.speak = [1500, 300]; HubVoice.ask('play the playlist')""")
    talk.wait_for_function("window.__starts.length >= 1", timeout=12000)
    log = talk.evaluate("window.__log")
    line = next(x for x in log if x["text"] != "Done. It is playing now." and x["text"] != "Done.")
    answer = next(x for x in log if x["text"].startswith("Done"))
    assert 2800 < line["at"] < 3500                                                        # the line is only asked for after three seconds
    assert answer["at"] - 3600 < 400, answer["at"]                                         # the answer is asked for the moment the action returns
    assert len(talk.evaluate("window.__starts")) == 1                                      # the dropped line was never played; only the answer was


def test_talk_keeps_listening_while_a_task_runs_stop_cuts_in_and_another_request_waits_its_turn(talk):
    talk.evaluate("""window.__cfg.say = 'On it.'; window.__cfg.action = { id: 'desktop_task', args: {} }; window.__cfg.act = 2500; window.__cfg.speak = [50];
                     window.__chats = 0; const f = window.fetch; window.fetch = (u, o) => { if (String(u).includes('/api/voice/chat')) window.__chats++; return f(u, o); };
                     HubVoice.ask('play the playlist'); void 0""")
    talk.wait_for_timeout(500)
    talk.evaluate("HubVoice.ask('and then open missions'); void 0")
    talk.wait_for_timeout(300)
    assert talk.evaluate("window.__chats") == 1                                            # the second request is held, not sent and not cutting the task off
    assert "I will do that as soon as this is finished" in talk.inner_text("#voice")
    talk.evaluate("HubVoice.ask('stop'); void 0")
    talk.wait_for_timeout(300)
    assert "Stopped." in talk.inner_text("#voice")
    talk.wait_for_timeout(2600)
    assert talk.evaluate("window.__chats") == 1                                            # stop also dropped the waiting request


def test_a_second_request_runs_after_the_first_finishes(talk):
    talk.evaluate("""window.__cfg.say = 'On it.'; window.__cfg.action = { id: 'desktop_task', args: {} }; window.__cfg.act = 1200; window.__cfg.speak = [50];
                     window.__chats = 0; const f = window.fetch; window.fetch = (u, o) => { if (String(u).includes('/api/voice/chat')) window.__chats++; return f(u, o); };
                     HubVoice.ask('first'); setTimeout(() => HubVoice.ask('second'), 300); void 0""")
    talk.wait_for_function("window.__chats === 2", timeout=9000)


def test_closing_the_talk_panel_stops_what_it_started(talk):
    talk.evaluate("""window.__cfg.say = 'On it.'; window.__cfg.action = { id: 'desktop_task', args: {} }; window.__cfg.act = 2500; window.__cfg.speak = [50];
                     window.__cancels = 0; const f = window.fetch; window.fetch = (u, o) => { if (String(u).includes('/api/voice/cancel')) window.__cancels++; return f(u, o); };
                     HubVoice.ask('play the playlist'); void 0""")
    talk.wait_for_timeout(500)
    assert talk.evaluate("HubVoice.state().acting") is True
    talk.click("#v-close")
    talk.wait_for_timeout(300)
    assert talk.evaluate("window.__cancels") == 1                                          # the server was told to stop whatever it is doing on the PC
    assert talk.evaluate("HubVoice.state().acting") is False and talk.evaluate("HubVoice.state().busy") is False
