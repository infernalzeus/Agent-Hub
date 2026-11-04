"""The Doctor falls back to the local team when Claude Code is signed out, says why, and the Hub shows it."""
import asyncio
from types import SimpleNamespace

from hub.features import missions as M, support as SUP


def _m(mid, runtime, status, error=""):
    return SimpleNamespace(id=mid, runtime=runtime, status=status, error=error, answer="")


def test_a_sign_in_error_on_the_last_claude_code_mission_is_reported_and_a_good_one_clears_it(tmp_path, monkeypatch):
    monkeypatch.setattr(SUP, "FILE", tmp_path / "ids.json")
    SUP.write_json(SUP.FILE, ["a", "b"])
    monkeypatch.setattr(M, "S", SimpleNamespace(m={"a": _m("a", "claude-code", "failed", "Failed to authenticate. API Error: 401 OAuth access token has expired"), "b": _m("b", "opencode", "applied")}))
    h = SUP.claude_health()
    assert h["ok"] is False and "/login" in h["why"]
    monkeypatch.setattr(M, "S", SimpleNamespace(m={"a": _m("a", "claude-code", "applied")}))
    assert SUP.claude_health()["ok"] is True


def test_asking_the_doctor_while_signed_out_uses_the_local_team_and_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(SUP, "FILE", tmp_path / "ids.json")
    monkeypatch.setattr(SUP, "claude_health", lambda: {"ok": False, "why": SUP.SIGN_IN})
    seen = {}

    async def fake(brief, runtime, model):
        seen["runtime"] = runtime
        return {"id": "m1"}
    monkeypatch.setattr(SUP, "_dispatch", fake)
    monkeypatch.setattr(SUP, "brief_for", lambda t: t)
    m = asyncio.run(SUP.start("what is wrong", "claude-code"))
    assert seen["runtime"] == "opencode" and "signed out" in m["note"]
