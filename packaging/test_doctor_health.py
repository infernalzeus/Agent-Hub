"""The Doctor falls back to the local team when Claude Code is signed out, says why, and the Hub shows it."""
import asyncio
from types import SimpleNamespace

from hub.features import missions as M, support as SUP


def _m(mid, runtime, status, error=""):
    return SimpleNamespace(id=mid, runtime=runtime, status=status, error=error, answer="")


def test_a_sign_in_error_on_the_last_claude_code_mission_is_reported_and_a_good_one_clears_it(tmp_path, monkeypatch):
    from hub.agent_knowledge import llm_status as LS
    monkeypatch.setattr(LS, "claude_status", lambda max_age=60.0: None)           # cannot tell live: judge from the last missions
    monkeypatch.setattr(SUP, "FILE", tmp_path / "ids.json")
    SUP.write_json(SUP.FILE, ["a", "b"])
    monkeypatch.setattr(M, "S", SimpleNamespace(m={"a": _m("a", "claude-code", "failed", "Failed to authenticate. API Error: 401 OAuth access token has expired"), "b": _m("b", "opencode", "applied")}))
    h = SUP.claude_health()
    assert h["ok"] is False and "/login" in h["why"]
    monkeypatch.setattr(M, "S", SimpleNamespace(m={"a": _m("a", "claude-code", "applied")}))
    assert SUP.claude_health()["ok"] is True


def test_the_live_sign_in_answer_beats_an_old_failed_mission(tmp_path, monkeypatch):
    from hub.agent_knowledge import llm_status as LS
    monkeypatch.setattr(SUP, "FILE", tmp_path / "ids.json")
    SUP.write_json(SUP.FILE, ["a"])
    monkeypatch.setattr(M, "S", SimpleNamespace(m={"a": _m("a", "claude-code", "failed", "Failed to authenticate 401")}))
    monkeypatch.setattr(LS, "claude_status", lambda max_age=60.0: {"installed": True, "signed_in": True, "plan": "pro", "how": "claude.ai", "why": ""})
    assert SUP.claude_health()["ok"] is True
    monkeypatch.setattr(LS, "claude_status", lambda max_age=60.0: {"installed": True, "signed_in": False, "why": "Claude Code is signed out. Open a terminal, run claude, then type /login."})
    h = SUP.claude_health()
    assert h["ok"] is False and "/login" in h["why"]


def _fake_dispatch(monkeypatch, seen):
    async def fake(brief, runtime, model):
        seen["runtime"] = runtime
        return {"id": "m1"}
    monkeypatch.setattr(SUP, "_dispatch", fake)
    monkeypatch.setattr(SUP, "brief_for", lambda t: t)


def test_asking_the_doctor_while_signed_out_is_refused_not_quietly_given_to_a_local_model(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setattr(SUP, "FILE", tmp_path / "ids.json")
    monkeypatch.setattr(SUP, "claude_health", lambda: {"ok": False, "why": SUP.SIGN_IN})
    seen = {}
    _fake_dispatch(monkeypatch, seen)
    with pytest.raises(SUP.SignedOut) as e:
        asyncio.run(SUP.start("what is wrong", "claude-code"))
    assert "/login" in str(e.value) and seen == {}                                  # nothing was started


def test_the_local_team_is_used_only_when_asked_for(tmp_path, monkeypatch):
    monkeypatch.setattr(SUP, "FILE", tmp_path / "ids.json")
    monkeypatch.setattr(SUP, "claude_health", lambda: {"ok": False, "why": SUP.SIGN_IN})
    seen = {}
    _fake_dispatch(monkeypatch, seen)
    m = asyncio.run(SUP.start("what is wrong", "claude-code", allow_local=True))
    assert seen["runtime"] == "opencode" and "because you said to" in m["note"]
    seen.clear()
    m = asyncio.run(SUP.start("what is wrong", "opencode"))                          # the owner chose the local team on the Support page: no claim, no refusal
    assert seen["runtime"] == "opencode" and m["note"] == ""
