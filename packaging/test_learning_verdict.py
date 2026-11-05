"""Applying or discarding a mission is an exact label for choices nothing recorded: which agent got each step, and whether a Doctor fix was wanted.
Recorded only; no learner reads these yet."""
import json
from types import SimpleNamespace

from hub import agent_knowledge as AK
from hub.features import learning as L, missions as M


def rows(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def mk(brief, plan, profile="code"):
    return SimpleNamespace(id="m1", brief=brief, plan=plan, profile=profile, agents=[], runtime="opencode", model="ollama/x")


def test_apply_and_discard_label_each_step_agent(tmp_path, monkeypatch):
    f = tmp_path / "choices.jsonl"
    monkeypatch.setattr(L, "CHOICES", f); monkeypatch.setattr(L, "enabled", lambda: True); L._close()
    m = mk("add a thing", [{"agent": "coder"}, {"agent": "tester"}])
    M._learn_verdict(m, True); M._learn_verdict(m, False); L._close()
    r = rows(f)
    assert [(x["kind"], x["chosen"], x["ok"]) for x in r] == [("persona", "coder", True), ("persona", "tester", True), ("persona", "coder", False), ("persona", "tester", False)]
    assert all(x["context"] == "code" and x["mission"] == "m1" and x["by"] == "orchestrator" for x in r)
    t = L.counters(r)["persona"]["code"]
    assert t["coder"]["ok"] == 1 and t["coder"]["failed"] == 1


def test_a_doctor_mission_also_records_a_fix_verdict(tmp_path, monkeypatch):
    f = tmp_path / "choices.jsonl"
    monkeypatch.setattr(L, "CHOICES", f); monkeypatch.setattr(L, "enabled", lambda: True); L._close()
    M._learn_verdict(mk("You are the doctor for Agent Hub, a Python app.", []), False); L._close()
    r = rows(f)
    assert len(r) == 1 and r[0]["kind"] == "fix" and r[0]["ok"] is False and r[0]["chosen"] == "opencode:ollama/x"


def test_the_new_kinds_are_known_and_recording_never_raises(monkeypatch):
    assert "persona" in L.KINDS and "fix" in L.KINDS
    monkeypatch.setattr(L, "note", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk full")))
    M._learn_verdict(mk("x", [{"agent": "coder"}]), True)          # must not raise


def test_an_agent_without_its_own_model_reports_the_default_for_all_agents(monkeypatch):
    monkeypatch.setattr(AK, "load_overrides", lambda: {"coder": {"model": "ollama/special"}})
    assert AK.effective_settings("coder")["model"] == {"value": "ollama/special", "source": "override"}
    other = AK.effective_settings("tester")["model"]
    assert other["source"] == "all" and other["value"] and "all agents" in other["note"]


def test_changing_one_setting_does_not_wipe_the_others(tmp_path, monkeypatch):
    import asyncio
    from hub.features import opencode as OC
    monkeypatch.setattr(AK, "OVERRIDES_FILE", tmp_path / "ov.json")
    AK.save_override("coder", {"model": "a/b", "temperature": 0.3, "steps": 9})

    class Req:
        match_info = {"name": "coder"}
        async def json(self): return {"model": "c/d"}
        async def read(self): return b'{"model": "c/d"}'
        can_read_body = True
    try:
        asyncio.run(OC.oc_agent_settings(Req()))
    except Exception:
        pass
    got = AK.load_overrides()["coder"]
    assert got["model"] == "c/d" and got["temperature"] == 0.3 and got["steps"] == 9
    AK.save_override("coder", {"model": ""})                         # an empty model removes the override: the agent follows the default again
    assert "model" not in AK.load_overrides()["coder"]
