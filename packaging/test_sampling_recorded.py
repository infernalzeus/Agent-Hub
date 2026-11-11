"""R8a: a mission's model outcome carries the sampling settings it ran with, so two results at different temperatures can be compared later."""
import json

from hub import agent_knowledge as AK
from hub.agent_knowledge import model_stats as MS


def test_the_settings_in_effect_are_flat_and_small(monkeypatch):
    monkeypatch.setattr(AK, "effective_settings", lambda name: {
        "temperature": {"value": 0.2, "source": "override"}, "top_p": {"value": None, "source": "default"},
        "steps": {"value": 12, "source": "persona"}, "variant": {"value": None, "source": "default"},
        "options": {"value": {"num_predict": 900, "top_k": 40, "stop": ["x"]}, "source": "override"}})
    got = AK.sampling_of("coder")
    assert got == {"temperature": 0.2, "steps": 12, "num_predict": 900, "top_k": 40}                 # unset knobs and lists are left out


def test_a_broken_settings_lookup_never_stops_a_mission(monkeypatch):
    monkeypatch.setattr(AK, "effective_settings", lambda name: (_ for _ in ()).throw(RuntimeError("no such persona")))
    assert AK.sampling_of("nobody") == {}


def test_the_outcome_row_keeps_them_and_old_rows_still_read(tmp_path, monkeypatch):
    monkeypatch.setattr(MS, "OUTCOMES", tmp_path / "model_outcomes.json")
    MS.record(["ollama/x"], True, 12.0, 300, "m1", sampling={"temperature": 0.2})
    MS.record(["ollama/x"], False, 9.0, 300, "m2")                                                  # no settings known: the row is as before
    rows = json.loads((tmp_path / "model_outcomes.json").read_text(encoding="utf-8"))
    assert rows[0]["sampling"] == {"temperature": 0.2} and "sampling" not in rows[1]
