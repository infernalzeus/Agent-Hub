"""Smith replaces the wake button on the landing page. His picture is the button: it shows while the wake word is off (so it can be switched on) and while you are talking with him
(you said Smith: it pops up, and goes when the talk is quiet); while the Hub only waits for his name it is invisible but still clickable. Nothing is drawn over the orb. At ENTER the
page goes quiet (microphone let go, polling stopped, the ring stops breathing) so the move to the dashboard has the whole processor."""
import time

from playwright.sync_api import sync_playwright

from test_ui_lifecycle import hub  # noqa: F401  (an isolated Hub on its own state folder)

FAKE_MIC = """navigator.mediaDevices.getUserMedia = async () => { const c = new AudioContext(), d = c.createMediaStreamDestination(), o = c.createOscillator(); o.connect(d); o.start(); return d.stream; };"""


def _nd(data):
    import json
    return json.dumps({"t": "result", "data": data}) + chr(10)


def _landing(pw, hub, **ctx_args):
    b = pw.chromium.launch(headless=True, args=["--autoplay-policy=no-user-gesture-required"])
    ctx = b.new_context(service_workers="block", viewport={"width": 1100, "height": 900}, **ctx_args)
    ctx.add_init_script(FAKE_MIC)
    pg = ctx.new_page()
    pg.goto(hub + "/offline.html")
    pg.wait_for_selector("#smith-slot", state="visible", timeout=20000)
    return b, pg


def _opacity(pg):
    return pg.evaluate("parseFloat(getComputedStyle(document.querySelector('#smith-slot img')).opacity)")


def _shown(pg):
    """On the page and in a state: nearly invisible and pulsing while the wake word is off, lit while he talks, breathing while he waits."""
    pg.wait_for_function("!document.getElementById('smith-slot').classList.contains('intro')", timeout=8000)
    pg.wait_for_function("(()=>{const c=document.getElementById('smith-slot').classList;return c.contains('pulse')||c.contains('talking')||c.contains('waiting')})()", timeout=8000)


def _hidden(pg):
    pg.wait_for_function("!document.getElementById('smith-slot').classList.contains('intro')", timeout=8000)
    """While the Hub waits for his name he is still on the page, drawn and in place: the wake ring is lit and his picture carries a soft glow."""
    pg.wait_for_function("document.getElementById('smith-slot').classList.contains('waiting')")
    assert _opacity(pg) > 0.9


def test_his_picture_is_the_button_it_pops_up_when_you_say_smith_and_nothing_is_drawn_over_the_orb(hub):
    with sync_playwright() as pw:
        b, pg = _landing(pw, hub)
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        _shown(pg)                                                                                 # wake word off: the picture is the switch
        assert pg.get_attribute("#smith-slot", "aria-label").startswith("Smith")
        assert "smith-held" in pg.get_attribute("#wake-toggle", "class")                           # the old button is no longer on the page
        pg.click("#smith-slot")
        pg.wait_for_function("window.__hubWake.state() === 'wake'", timeout=15000)
        pg.wait_for_function("document.getElementById('wake-ring').classList.contains('on')")
        _hidden(pg)                                                                                # waiting for his name: invisible
        pg.evaluate("window.__hubWake._set('convo')")                                              # you said Smith: he pops up, in the button's place
        _shown(pg)
        slot = pg.evaluate("(()=>{const r=document.getElementById('smith-slot').getBoundingClientRect(), g=document.querySelector('.globe-wrap').getBoundingClientRect();return {top:r.top,gbottom:g.bottom}})()")
        assert slot["top"] >= slot["gbottom"] - 2                                                  # below the orb, never in front of it
        for s in ("think", "speak"):
            pg.evaluate(f"window.__hubWake._set('{s}')"); _shown(pg)
        assert pg.evaluate("document.querySelectorAll('svg.smith-draw, .smith-draw').length") == 0   # no outline exists any more
        pg.evaluate("window.__hubWake._set('wake')")                                               # quiet again: gone
        _hidden(pg)
        pg.click("#smith-slot")                                                                    # the invisible him: off, the picture returns
        pg.wait_for_function("window.__hubWake.state() === 'off'", timeout=10000)
        _shown(pg)
        b.close()
    assert errors == []


def test_the_hidden_wake_button_still_works(hub):
    with sync_playwright() as pw:
        b, pg = _landing(pw, hub, reduced_motion="reduce")
        pg.evaluate("document.getElementById('wake-toggle').click()")                              # the old switch is still the one holding the state
        pg.wait_for_function("window.__hubWake.state() === 'wake'", timeout=15000)
        pg.evaluate("window.__hubWake._set('convo')")
        _shown(pg)
        b.close()


def test_pressing_enter_quiets_the_page_microphone_ring_and_picture(hub):
    with sync_playwright() as pw:
        b, pg = _landing(pw, hub)
        pg.click("#smith-slot")
        pg.wait_for_function("window.__hubWake.state() === 'wake' && window.__hubWake.mic()", timeout=15000)
        pg.evaluate("window.DepthLift && (DepthLift.software = false); document.documentElement.classList.remove('hub-soft')")       # a headless browser draws in software: this test is about the ring, so say it is not
        pg.wait_for_function("getComputedStyle(document.getElementById('wake-ring')).animationName === 'wkBreath'")
        pg.evaluate("window.__hubWake._leave()")                                                   # what the click on ENTER does first
        assert pg.evaluate("window.__hubWake.mic()") is False                                      # the microphone and its analysers are let go
        assert pg.evaluate("getComputedStyle(document.getElementById('wake-ring')).animationName") == "none"
        assert pg.evaluate("document.getElementById('smith-slot').classList.contains('still') && getComputedStyle(document.getElementById('smith-slot')).display !== 'none'")      # he stays; only his animation stops
        assert pg.evaluate("localStorage.getItem('agenthub:wake')") == "1"                         # the wake word stays switched on for the dashboard
        b.close()


def _enter(pw, hub, listening):
    """Click ENTER; return milliseconds to the new address and the slowest gap between two animation frames on the way."""
    b, pg = _landing(pw, hub)
    pg.wait_for_selector("#wake-btn[data-s=enter]", timeout=20000)
    if listening:
        pg.click("#smith-slot")
        pg.wait_for_function("window.__hubWake.state() === 'wake'", timeout=15000)
        pg.evaluate("window.__hubWake._set('convo')")
        pg.wait_for_timeout(900)
    pg.evaluate("""()=>{window.__gaps=[];let last=performance.now();const f=t=>{window.__gaps.push(t-last);last=t;try{sessionStorage.setItem('gaps',JSON.stringify(window.__gaps))}catch(e){}requestAnimationFrame(f)};requestAnimationFrame(f)}""")
    t0 = time.time()
    pg.click("#wake-btn")
    pg.wait_for_url("**enter=1**", timeout=30000)
    ms = (time.time() - t0) * 1000
    b.close()
    return ms


def test_entering_the_dashboard_is_no_slower_while_he_is_listening(hub):
    with sync_playwright() as pw:
        plain = min(_enter(pw, hub, False) for _ in range(2))
        listening = min(_enter(pw, hub, True) for _ in range(2))
    assert listening < plain + 600, (plain, listening)                                             # headless uses software graphics, so only a large gap would be real


def test_his_picture_is_inside_the_page_and_while_the_hub_is_dormant_he_is_nearly_gone_and_not_a_button(hub):
    """No request to make, so nothing can fail while the Hub is down. Dormant: almost invisible, pulsing very low, and a click on him starts nothing."""
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        ctx = b.new_context(service_workers="block", viewport={"width": 1100, "height": 900})
        pg = ctx.new_page()
        asked = []
        pg.on("request", lambda r: asked.append(r.url) if "smith-icon" in r.url else None)
        pg.route("**/api/status*", lambda r: r.abort())                                           # the Hub is asleep
        pg.goto(hub + "/offline.html")
        pg.wait_for_selector("#smith-slot", timeout=20000)
        pg.wait_for_function("document.getElementById('smith-slot').classList.contains('dormant')", timeout=15000)
        assert pg.evaluate("document.querySelector('#smith-slot img').src.startsWith('data:image/png')") and not asked
        assert pg.evaluate("getComputedStyle(document.getElementById('smith-slot')).pointerEvents") == "none"
        assert pg.evaluate("Math.max(...[0,1,2].map(()=>parseFloat(getComputedStyle(document.querySelector('#smith-slot img')).opacity)))") < 0.2     # nearly invisible
        assert pg.evaluate("document.getElementById('wake-btn').getAttribute('data-s')") != "starting"
        b.close()


def test_coming_back_to_the_landing_page_from_the_dashboard_his_button_works_again(hub):
    with sync_playwright() as pw:
        b, pg = _landing(pw, hub)
        pg.click("#smith-slot")
        pg.wait_for_function("window.__hubWake.state() === 'wake'", timeout=15000)
        pg.evaluate("window.__hubWake._leave()")                                                   # ENTER pressed: the page goes quiet and his button is put away
        assert pg.evaluate("document.getElementById('smith-slot').classList.contains('still') && getComputedStyle(document.getElementById('smith-slot')).display !== 'none'")      # he stays; only his animation stops
        pg.evaluate("window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}))")   # back from the page cache
        assert pg.evaluate("getComputedStyle(document.getElementById('smith-slot')).display") != "none"
        assert pg.evaluate("getComputedStyle(document.getElementById('wake-ring')).animationName") != "none" or not pg.evaluate("document.getElementById('wake-ring').classList.contains('on')")
        _shown(pg)
        pg.click("#smith-slot")                                                                    # and it is clickable: the wake word switches on again
        pg.wait_for_function("window.__hubWake.state() === 'wake' && window.__hubWake.mic()", timeout=15000)
        b.close()


def test_asking_for_viktor_on_the_landing_page_swaps_the_picture_and_stop_throws_a_late_answer_away(hub):
    """He asked "bring Viktor" and nothing changed; then STOP was pressed and the answer still arrived seconds later and spoke."""
    with sync_playwright() as pw:
        b, pg = _landing(pw, hub)
        errors, sent = [], []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.route("**/api/voice/speak", lambda r: r.fulfill(status=503, body="no voice in a test"))

        def chat(route):
            body = route.request.post_data_json
            sent.append(body)
            if "slow" in body["text"]:
                time.sleep(2.5)
                return route.fulfill(body=_nd({"say": "Too late.", "action": None, "confirm": False, "speaker": "smith", "ui": {}}), content_type="application/x-ndjson")
            route.fulfill(body=_nd({"say": "I am here.", "action": None, "confirm": False, "speaker": "orchestrator", "ui": {},
                                    "transition": {"from": "smith", "to": "orchestrator", "line": "Of course. I will bring in Viktor."}}), content_type="application/x-ndjson")
        pg.route("**/api/voice/stream", chat)
        _shown(pg)
        pg.click("#smith-slot")
        pg.wait_for_function("window.__hubWake.state() === 'wake'", timeout=15000)
        assert pg.evaluate("window.__hubWake.who()") == "smith"
        pg.evaluate("window.__hubWake.say('bring Viktor')")
        pg.wait_for_function("window.__hubWake.who() === 'orchestrator'", timeout=8000)
        pg.wait_for_function("document.querySelector('#smith-slot img').src.includes('/static/agent-icons/orchestrator.png')", timeout=4000)     # Smith went, Viktor arrived
        assert "other" in pg.get_attribute("#smith-slot", "class")
        assert sent[0]["speaker"] == "smith"
        texts = pg.evaluate("[...document.querySelectorAll('#wake-lines .wl')].map(e => e.textContent)")
        assert any(t.startswith("Smith: Of course") for t in texts) and any(t.startswith("Viktor: I am here") for t in texts), texts      # each line is under its own speaker's name
        pg.evaluate("window.__hubWake.say('slow one')")
        assert sent[-1]["speaker"] == "orchestrator"                                           # the next sentence goes to Viktor
        pg.evaluate("window.__hubWake.stop()")                                                 # STOP while it is thinking
        pg.wait_for_timeout(3500)
        assert pg.evaluate("window.__hubWake.who()") == "smith"
        texts = pg.evaluate("[...document.querySelectorAll('#wake-lines .wl')].map(e => e.textContent)")
        assert not any("Too late" in t for t in texts), texts                                  # the late answer was not said
        b.close()
    assert errors == []


def test_smith_stays_a_plain_outline_and_only_a_second_picture_fades_in_while_he_answers(hub):
    with sync_playwright() as pw:
        b, pg = _landing(pw, hub)
        _shown(pg)
        pg.click("#smith-slot")
        pg.wait_for_function("window.__hubWake.state() === 'wake'", timeout=15000)
        pg.evaluate("document.getElementById('smith-slot').classList.remove('hear')")              # the fake microphone's tone makes him "hear"; take that away for the resting state
        assert pg.evaluate("getComputedStyle(document.querySelector('#smith-slot .lit-img')).animationName") == "none"      # outline at rest
        pg.evaluate("window.__hubWake._set('think')")
        pg.wait_for_function("getComputedStyle(document.querySelector('#smith-slot .lit-img')).animationName === 'smDigits'", timeout=4000)
        assert pg.evaluate("getComputedStyle(document.querySelector('#smith-slot img:not(.lit-img)')).animationName") == "none"     # the outline itself does not move or change colour
        css = pg.evaluate("[...document.styleSheets].flatMap(s => { try { return [...s.cssRules].map(r => r.cssText) } catch (e) { return [] } }).join(' ')")
        assert "hue-rotate" not in css and "rgba(0,230,118" not in css.split("smLit")[1][:200]                                 # no lime pulse
        b.close()


def test_any_agents_name_wakes_that_agent_and_unmatched_speech_is_shown_dimly(hub):
    with sync_playwright() as pw:
        b, pg = _landing(pw, hub)
        _shown(pg)
        names = pg.evaluate("""() => { const f = window.__hubWake._split; return ['Smith, status', 'hey Viktor what is running', 'Victor', 'agent smith', 'the doctor, fix it', 'Neo draft an agent', 'smif open home', 'banana', 'doc how is it'].map(t => { const r = f(t); return r ? r.who + '|' + r.rest : null; }); }""")
        b.close()
    assert names == ["smith|status", "orchestrator|what is running", "orchestrator|", "smith|", "doctor|fix it", "neo|draft an agent", "smith|open home", None, "doctor|how is it"], names


def test_a_slow_answer_is_covered_by_a_short_holding_phrase_that_a_real_answer_cuts_off(hub):
    """The model took 8 to 35 s to answer in the 14 Nov log and the page said nothing: after a moment he now says one short line (kept ready, so it is instant)."""
    with sync_playwright() as pw:
        b, pg = _landing(pw, hub)
        asked = []
        pg.route("**/api/voice/speak", lambda r: (asked.append(r.request.post_data_json["text"]), r.fulfill(status=503, body="no voice in a test"))[1])

        def chat(route):
            time.sleep(2.4)
            route.fulfill(body=_nd({"say": "Here it is.", "action": None, "confirm": False, "speaker": "smith", "ui": {}}), content_type="application/x-ndjson")
        pg.route("**/api/voice/stream", chat)
        _shown(pg)
        pg.click("#smith-slot")
        pg.wait_for_function("window.__hubWake.state() === 'wake'", timeout=15000)
        pg.evaluate("window.__hubWake.say('tell me something long')")
        pg.wait_for_timeout(2000)
        assert "One moment." in asked, asked                                                  # said while the answer was still being worked out
        pg.wait_for_function("document.querySelector('#wake-lines') && [...document.querySelectorAll('#wake-lines .wl')].some(e => e.textContent.includes('Here it is'))", timeout=8000)
        b.close()


def test_a_streamed_answer_is_said_sentence_by_sentence_as_it_arrives_and_not_said_again_at_the_end(hub):
    """The whole sentence used to appear and then wait for its voice: now each sentence is fetched as a voice when it arrives and shown when it starts."""
    import json
    with sync_playwright() as pw:
        b, pg = _landing(pw, hub)
        asked = []
        pg.route("**/api/voice/speak", lambda r: (asked.append(r.request.post_data_json["text"]), r.fulfill(status=503, body="no voice in a test"))[1])
        lines = [{"t": "say", "text": "First sentence."}, {"t": "say", "text": "And a second one."},
                 {"t": "result", "data": {"say": "First sentence. And a second one.", "action": None, "confirm": False, "speaker": "smith", "ui": {}, "backend": "fast:test"}}]
        pg.route("**/api/voice/stream", lambda r: r.fulfill(body=chr(10).join(json.dumps(x) for x in lines) + chr(10), content_type="application/x-ndjson"))
        _shown(pg)
        pg.click("#smith-slot")
        pg.wait_for_function("window.__hubWake.state() === 'wake'", timeout=15000)
        pg.evaluate("window.__hubWake.say('tell me something')")
        pg.wait_for_function("[...document.querySelectorAll('#wake-lines .wl')].filter(e => e.textContent.startsWith('Smith: ')).length >= 2", timeout=8000)
        texts = pg.evaluate("[...document.querySelectorAll('#wake-lines .wl')].map(e => e.textContent)")
        b.close()
    assert {t for t in asked if t not in ("Yes?", "One moment.")} == {"First sentence.", "And a second one."}, asked          # a voice was asked for each sentence (fetched ahead, then used), none for the whole answer
    assert "Smith: First sentence." in texts and "Smith: And a second one." in texts and not any("First sentence. And" in t for t in texts), texts
