"""The R panel is connected to what it describes: the trusted folder files routines away (by hand or after 30 days), and the model order really follows the tally in APPLY mode."""
import time
from contextlib import contextmanager

from hub import agent_knowledge as AK
from hub.agent_knowledge import model_stats as MS
from hub.yard import knobs as K, presets as P, routine_folder as RF


def _fake_db(rows):
    class Db:
        def execute(self, sql, *a):
            return [dict(r) for r in rows]

    @contextmanager
    def db():
        yield Db()
    return db


def test_trusted_routines_are_filed_by_hand_or_after_thirty_days_and_only_trusted_ones(tmp_path, monkeypatch):
    from hub.features import pc_control as PC
    now = time.time()
    rows = [{"id": "old", "status": "trusted", "updated": now - 40 * 86400}, {"id": "new", "status": "trusted", "updated": now - 3 * 86400}, {"id": "cand", "status": "candidate", "updated": now}]
    monkeypatch.setattr(PC, "_db", _fake_db(rows))
    monkeypatch.setattr(RF, "_file", lambda: tmp_path / "folder.json")
    assert RF.state(now)["filed"] == ["old"]                                  # trusted for more than 30 days: it files itself
    assert RF.set_filed("new", True) and RF.state(now)["filed"] == ["new", "old"]
    assert not RF.set_filed("cand", True)                                     # a candidate cannot be filed
    assert RF.set_filed("old", False) and RF.state(now)["filed"] == ["new"]   # taken out by hand: the 30-day rule does not put it back
    rows[1]["status"] = "candidate"                                           # demoted: it leaves the folder
    assert RF.state(now)["filed"] == []


def test_in_apply_mode_the_tally_puts_the_model_with_the_better_record_first_and_otherwise_the_order_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(K, "FILE", tmp_path / "knobs.json")
    monkeypatch.setattr(P, "_dir", lambda: tmp_path)
    chain = ["ollama/a", "opencode/b", "opencode/c"]
    monkeypatch.setattr(MS, "table", lambda models=None, last=60: {"ollama/a": {"ok": 1, "failed": 4}, "opencode/b": {"ok": 5, "failed": 0}})
    assert AK._tally_first(chain) == chain                                    # shadow (the default): it only watches
    K.set_many({"preset_mode": "apply"})
    assert AK._tally_first(chain) == ["opencode/b", "ollama/a", "opencode/c"]  # apply: the model that passed the project's checks goes first
    monkeypatch.setattr(MS, "table", lambda models=None, last=60: {"ollama/a": {"ok": 1, "failed": 0}})
    assert AK._tally_first(chain) == chain                                    # one model with a record is not an opinion


def test_the_models_table_lists_every_model_in_the_order_it_would_be_tried_with_whether_it_works(tmp_path, monkeypatch):
    monkeypatch.setattr(K, "FILE", tmp_path / "knobs.json")
    monkeypatch.setattr(P, "_dir", lambda: tmp_path)
    t = P.models_table()
    ranked = [r for r in t["rows"] if r.get("order")]
    assert [r["order"] for r in ranked] == list(range(1, len(ranked) + 1)) and ranked[0]["model"] == AK.model_chain(None)[0]
    assert all(r["works"] in ("works", "unmeasured", "broken", "dead") for r in t["rows"]) and "model order" in t["tally"]
