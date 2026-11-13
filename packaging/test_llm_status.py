"""The default model is this PC's own; a model found dead (Ollama cloud Nemotron needs credits, a withdrawn Zen model) is never tried first; the Doctor says when Claude Code is signed out."""
import asyncio
import json
import time

import pytest

from hub import agent_knowledge as AK
from hub.agent_knowledge import llm_status as LS, model_stats as MS
from hub.features import support as SUP, talk_agents as T

GOOD = {"loads": True, "json_ok_of_5": 5, "tool_call": True}


@pytest.fixture(autouse=True)
def _state(tmp_path, monkeypatch):
    f = tmp_path / "measured.json"
    f.write_text(json.dumps({"gemma4:e4b-32k": GOOD}), encoding="utf-8")
    monkeypatch.setattr(MS, "MEASURED", f)
    monkeypatch.setattr(MS, "OUTCOMES", tmp_path / "out.json")
    monkeypatch.setattr(LS, "FILE", tmp_path / "llm.json")
    monkeypatch.setattr(AK, "model_policy", lambda: "auto")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)


def test_the_default_is_the_local_model_for_a_short_or_a_long_brief_and_no_chain_has_a_cloud_model():
    assert AK.resolved_default_model() == AK.LOCAL_MODEL
    for brief in ("small", "x" * 900, None):
        chain = AK.model_chain(None, None, brief=brief)
        assert chain[0] == AK.LOCAL_MODEL and not [m for m in chain if m.endswith(":cloud")]
    assert "opencode/mimo-v2.5-free" not in AK.model_chain(None, None)                   # withdrawn from Zen on 13 Nov
    assert AK.resolved_default_model("ollama/nemotron-3-super:cloud") == AK.LOCAL_MODEL    # opencode.json still names it; the Hub does not follow that


def test_a_local_model_that_is_unmeasured_or_does_badly_hands_the_first_place_to_the_free_models():
    for ok in (False, False, False, True, False):
        MS.record([AK.LOCAL_MODEL], ok, 60, 100)
    assert AK.model_chain(None, None)[0] == AK.FAST_FREE_MODEL and AK.LOCAL_MODEL in AK.model_chain(None, None)
    for _ in range(12):
        MS.record([AK.LOCAL_MODEL], True, 60, 100)
    assert AK.model_chain(None, None)[0] == AK.LOCAL_MODEL


def test_a_model_found_dead_by_a_check_is_left_out_unless_pinned_and_comes_back_when_it_answers():
    LS._remember({AK.FAST_FREE_MODEL: {"ok": False, "why": "no answer", "at": time.time()}})
    assert AK.FAST_FREE_MODEL not in AK.model_chain(None, None)
    assert AK.model_chain(AK.FAST_FREE_MODEL)[0] == AK.FAST_FREE_MODEL
    LS._remember({AK.FAST_FREE_MODEL: {"ok": True, "why": "", "at": time.time()}})
    assert AK.FAST_FREE_MODEL in AK.model_chain(None, None)
    LS._remember({AK.FAST_FREE_MODEL: {"ok": False, "why": "old", "at": time.time() - LS.DEAD_TTL - 5}})
    assert AK.FAST_FREE_MODEL in AK.model_chain(None, None)                                 # a day later it is asked again, not trusted dead for ever


def test_a_check_says_in_plain_words_what_is_dead(monkeypatch):
    async def get(path, timeout=3.0):
        return 200, {"models": [{"name": "gemma4:e4b-32k", "capabilities": ["completion"]}, {"name": "nemotron-3-super:cloud", "remote_host": "https://ollama.com:443"}, {"name": "nomic-embed-text:latest", "capabilities": ["embedding"]}]}

    async def chat(name, timeout, keep_alive=None):
        return False, "needs usage credits or a subscription on ollama.com", 0.2

    async def zen(model, offered):
        return {"model": model, "ok": model != "opencode/glm-5.3-flash-free", "why": "" if model != "opencode/glm-5.3-flash-free" else "no longer offered by OpenCode Zen", "secs": 9.0}

    async def oc(args, timeout):
        return 0, "opencode/nemotron-3.5-lightning-free\nopencode/mimo-v2.6-flash-free\n"
    monkeypatch.setattr(LS, "_get", get)
    monkeypatch.setattr(LS, "_tiny_chat", chat)
    monkeypatch.setattr(LS, "_zen", zen)
    monkeypatch.setattr(LS, "_opencode", oc)
    monkeypatch.setattr(LS, "claude_status", lambda max_age=60.0: {"installed": True, "signed_in": True, "plan": "pro", "how": "claude.ai", "why": ""})
    j = asyncio.run(LS.snapshot(check=True))
    by = {r["what"]: r for r in j["lines"]}
    assert j["default"] == AK.LOCAL_MODEL and by["Ollama on this PC"]["state"] == "ok" and "1 local model " in by["Ollama on this PC"]["say"]
    assert by["Ollama cloud: nemotron-3-super:cloud"]["state"] == "bad" and "credits" in by["Ollama cloud: nemotron-3-super:cloud"]["say"]
    assert "2 of 3 answer" in by["OpenCode Zen free models"]["say"] and "glm-5.3-flash-free" in by["OpenCode Zen free models"]["say"]
    assert by["Claude Code (the Doctor)"]["state"] == "ok" and "not an API key" in by["Claude Code (the Doctor)"]["say"]
    assert "none set" in by["Paid API keys"]["say"] and not any(j["keys"].values())
    assert LS.dead("ollama/nemotron-3-super:cloud") and not LS.dead("ollama/gemma4:e4b-32k")      # remembered for the chain
    j2 = asyncio.run(LS.snapshot())                                                                 # a plain read shows the last answers and asks nothing expensive
    assert {r["what"]: r["say"] for r in j2["lines"]}["Ollama cloud: nemotron-3-super:cloud"].startswith("needs usage credits")


def test_a_repair_or_change_goes_to_claude_code_and_a_question_is_answered_in_chat(monkeypatch):
    started, asked = [], []

    async def start(text, runtime=None, model=None, allow_local=False):
        started.append(text)
        return {"id": "m1"}

    async def persona(agent, brief, role=None):
        asked.append(brief)
        return "It reads your request."
    monkeypatch.setattr(SUP, "start", start)
    monkeypatch.setattr(SUP, "brief_for", lambda t: t)
    monkeypatch.setattr(SUP, "claude_health", lambda: {"ok": True, "why": ""})
    monkeypatch.setattr(T, "_persona", persona)
    for text in ("the R panel sits too low and wastes space on my screen", "fix the layout of the teach tab please", "Doctor, change the header colour to green"):
        r = asyncio.run(T.doctor(text, [], None, None))
        assert r["ui"]["doctor"] and "Claude Code" in r["say"]
    assert len(started) == 3 and not asked
    r = asyncio.run(T.doctor("how does the router decide what I meant", [], None, None))
    assert len(started) == 3 and asked and "Claude Code signed in: yes" in asked[0] and "Never say you have no Claude access" in asked[0]


def test_the_doctor_in_talk_says_claude_code_is_signed_out_and_does_not_hand_the_repair_to_a_small_model(monkeypatch):
    async def start(text, runtime=None, model=None, allow_local=False):
        raise SUP.SignedOut(SUP.SIGN_IN)
    monkeypatch.setattr(SUP, "start", start)
    r = asyncio.run(T.doctor("the board is broken", [], None, None))
    assert "signed out" in r["say"] and "unasked" in r["say"] and "LOCAL FIRST" in r["say"] and not r.get("ui", {}).get("doctor")
