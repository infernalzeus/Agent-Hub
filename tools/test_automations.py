"""An automation runs steps in order, and stops before anything consequential.

These pin the behaviour the whole feature rests on: that a gated step waits
rather than acts, that a run survives being answered later, that a failure stops
the rest, and that an event cannot set an automation triggering itself forever.
"""
import asyncio
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hub import events                              # noqa: E402
from hub.features import automations as A           # noqa: E402
from hub.features import capabilities as C          # noqa: E402


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "FILE", tmp_path / "automations.json")
    monkeypatch.setattr(A, "RUNS", tmp_path / "runs.json")
    events._subs.clear()
    events._recent.clear()
    return tmp_path


@pytest.fixture()
def ran(monkeypatch):
    """Record which steps actually executed, so a gate can be proven to block one."""
    seen = []

    async def fake(step, run):
        seen.append(step["id"])
        if step.get("explode"):
            raise RuntimeError("step blew up")
        return f"did {step['id']}"

    monkeypatch.setitem(A._STEPS, "hub", fake)
    monkeypatch.setitem(A._STEPS, "mission", fake)
    monkeypatch.setitem(A._STEPS, "routine", fake)
    return seen


def _auto(**kw):
    base = {"name": "nightly", "trigger": {"kind": "manual"},
            "steps": [{"kind": "hub", "path": "/api/status"}]}
    base.update(kw)
    return base


# -- validation ---------------------------------------------------------------
def test_an_automation_needs_a_name(store):
    assert "name" in A.validate(_auto(name=" "))


def test_an_automation_needs_at_least_one_step(store):
    assert "at least one step" in A.validate(_auto(steps=[]))


def test_an_event_trigger_must_name_an_event_the_hub_emits(store):
    assert "actually emits" in A.validate(
        _auto(trigger={"kind": "event", "event": "mission.exploded"}))
    assert A.validate(_auto(trigger={"kind": "event", "event": "mission.finished"})) == ""


def test_a_hub_step_cannot_point_outside_the_api(store):
    assert "/api/" in A.validate(_auto(steps=[{"kind": "hub", "path": "/etc/passwd"}]))


def test_a_mission_step_needs_a_brief_and_a_project(store):
    assert "brief" in A.validate(_auto(steps=[{"kind": "mission", "project": "p"}]))
    assert "project" in A.validate(_auto(steps=[{"kind": "mission", "brief": "do it"}]))


def test_saving_an_invalid_automation_raises(store):
    with pytest.raises(ValueError):
        A.save(_auto(steps=[{"kind": "nonsense"}]))


# -- storage ------------------------------------------------------------------
def test_save_then_load(store):
    row = A.save(_auto())
    assert A.load() == [row]
    assert A.get(row["id"])["name"] == "nightly"


def test_saving_again_updates_rather_than_duplicates(store):
    row = A.save(_auto())
    again = A.save({**_auto(name="renamed"), "id": row["id"]})
    assert len(A.load()) == 1
    assert again["name"] == "renamed"
    assert again["created"] == row["created"], "created should not move on an edit"


def test_delete(store):
    row = A.save(_auto())
    assert A.delete(row["id"]) is True
    assert A.load() == []
    assert A.delete(row["id"]) is False


def test_steps_are_given_ids_so_a_run_can_refer_to_them(store):
    row = A.save(_auto(steps=[{"kind": "hub", "path": "/api/status"},
                              {"kind": "hub", "path": "/api/apps"}]))
    assert [s["id"] for s in row["steps"]] == ["s1", "s2"]


# -- running ------------------------------------------------------------------
def test_steps_run_in_order_and_the_run_is_recorded(store, ran):
    a = A.save(_auto(steps=[{"kind": "hub", "path": "/api/status"},
                            {"kind": "hub", "path": "/api/apps"}]))
    run = asyncio.run(A.start(a))
    assert ran == ["s1", "s2"]
    assert run["status"] == "done"
    assert [s["status"] for s in run["steps"]] == ["done", "done"]
    assert A.get_run(run["id"])["status"] == "done", "the run must be on disk"


def test_a_failing_step_stops_the_ones_after_it(store, ran):
    a = A.save(_auto(steps=[{"kind": "hub", "path": "/api/status"},
                            {"kind": "hub", "path": "/api/apps", "explode": True},
                            {"kind": "hub", "path": "/api/graph"}]))
    run = asyncio.run(A.start(a))
    assert run["status"] == "failed"
    assert ran == ["s1", "s2"], "the third step must not have run"
    assert "blew up" in run["steps"][1]["note"]
    assert run["steps"][2]["status"] == "pending"


def test_the_run_says_what_started_it(store, ran):
    a = A.save(_auto())
    assert asyncio.run(A.start(a, why="on schedule"))["why"] == "on schedule"


# -- gates --------------------------------------------------------------------
def test_a_gated_step_waits_and_does_not_run(store, ran):
    a = A.save(_auto(steps=[{"kind": "hub", "path": "/api/status"},
                            {"kind": "hub", "path": "/api/youtube/upload", "gate": True}]))
    run = asyncio.run(A.start(a))
    assert run["status"] == "awaiting_approval"
    assert ran == ["s1"], "the gated step must not have executed"
    assert run["steps"][1]["status"] == "awaiting_approval"


def test_approving_runs_the_gated_step_and_continues(store, ran):
    a = A.save(_auto(steps=[{"kind": "hub", "path": "/api/youtube/upload", "gate": True},
                            {"kind": "hub", "path": "/api/status"}]))
    run = asyncio.run(A.start(a))
    assert ran == []
    done = asyncio.run(A.approve(run["id"], True))
    assert done["status"] == "done"
    assert ran == ["s1", "s2"], "approval must run the step it was holding"


def test_declining_stops_the_run_without_running_anything_else(store, ran):
    a = A.save(_auto(steps=[{"kind": "hub", "path": "/api/youtube/upload", "gate": True},
                            {"kind": "hub", "path": "/api/status"}]))
    run = asyncio.run(A.start(a))
    stopped = asyncio.run(A.approve(run["id"], False))
    assert stopped["status"] == "stopped"
    assert ran == [], "declining must not run the gated step or the ones after it"


def test_a_gate_survives_being_answered_later(store, ran):
    """The whole point of persisting a run: approval can come tomorrow."""
    a = A.save(_auto(steps=[{"kind": "hub", "path": "/api/youtube/upload", "gate": True}]))
    rid = asyncio.run(A.start(a))["id"]
    reloaded = A.get_run(rid)
    assert reloaded["status"] == "awaiting_approval"
    assert asyncio.run(A.approve(rid, True))["status"] == "done"


def test_approving_a_run_that_is_not_waiting_is_refused(store, ran):
    a = A.save(_auto())
    run = asyncio.run(A.start(a))
    with pytest.raises(ValueError, match="not waiting"):
        asyncio.run(A.approve(run["id"], True))


# -- event triggers -----------------------------------------------------------
def test_an_event_starts_only_the_automations_listening_for_it(store, ran):
    A.save(_auto(name="on finish", trigger={"kind": "event", "event": "mission.finished"},
                 steps=[{"kind": "hub", "path": "/api/status", "id": "finish"}]))
    A.save(_auto(name="on download", trigger={"kind": "event", "event": "download.finished"},
                 steps=[{"kind": "hub", "path": "/api/status", "id": "download"}]))
    A.save(_auto(name="manual", steps=[{"kind": "hub", "path": "/api/status", "id": "manual"}]))
    asyncio.run(A.on_event({"kind": "mission.finished", "payload": {}}))
    assert ran == ["finish"], "only the matching event trigger may fire"


def test_a_disabled_automation_does_not_fire(store, ran):
    A.save(_auto(enabled=False, trigger={"kind": "event", "event": "mission.finished"}))
    asyncio.run(A.on_event({"kind": "mission.finished", "payload": {}}))
    assert ran == []


def test_an_automation_cannot_trigger_itself_forever(store, ran):
    a = A.save(_auto(trigger={"kind": "event", "event": "automation.finished"}))
    asyncio.run(A.on_event({"kind": "automation.finished",
                            "payload": {"automation": a["id"], "run": "r1"}}))
    assert ran == [], "its own completion must not start it again"


# -- schedule trigger ---------------------------------------------------------
def test_only_due_schedules_start(store, ran):
    now = time.time()
    due = A.save(_auto(name="due", trigger={"kind": "schedule", "every": "daily", "at": "09:00"},
                       steps=[{"kind": "hub", "path": "/api/status", "id": "due"}]))
    rows = A.load()
    for r in rows:
        r["next"] = now - 10 if r["id"] == due["id"] else now + 9999
    A._save(rows)
    A.save(_auto(name="later", trigger={"kind": "schedule", "every": "daily", "at": "09:00"},
                 steps=[{"kind": "hub", "path": "/api/status", "id": "later"}]))
    rows = A.load()
    for r in rows:
        if r["name"] == "later":
            r["next"] = now + 9999
    A._save(rows)
    asyncio.run(A.tick(now))
    assert "due" in ran and "later" not in ran


def test_a_manual_automation_is_never_started_by_the_clock(store, ran):
    A.save(_auto())
    assert asyncio.run(A.tick(time.time())) == []
    assert ran == []


# -- capabilities -------------------------------------------------------------
def test_denied_paths_are_refused_whatever_the_prefix_says():
    assert C.refuse("POST", "/api/shutdown")
    assert C.refuse("POST", "/api/llm/keys")


def test_an_unlisted_path_is_refused_and_says_how_to_allow_it():
    why = C.refuse("GET", "/api/something-new")
    assert "capabilities.ALLOWED" in why


def test_an_allowed_path_passes():
    assert C.refuse("GET", "/api/status") == ""


def test_a_get_is_never_consequential():
    assert C.consequential("/api/pc/machine/profiles", "GET") is False
    assert C.consequential("/api/youtube/upload", "GET") is False


def test_the_things_that_are_hard_to_undo_are_flagged():
    assert C.consequential("/api/youtube/upload", "POST")
    assert C.consequential("/api/missions/m1/apply", "POST")
    assert C.consequential("/api/missions/m1/discard", "POST")


def test_a_hub_step_to_a_denied_path_fails_the_run(store):
    a = A.save({"name": "sneaky", "trigger": {"kind": "manual"},
                "steps": [{"kind": "hub", "path": "/api/missions", "method": "GET"}]})
    # swap in the real hub step so the capability check is the thing under test
    a["steps"][0]["path"] = "/api/shutdown"
    run = asyncio.run(A._advance(a, A._new_run(a, "test")))
    assert run["status"] == "failed"
    assert "not available to automations" in run["steps"][0]["note"]


# -- missions announcing themselves -------------------------------------------
# save() is called on every streamed chunk, so this is where a careless emit
# would fire an automation hundreds of times, or fire every automation at boot.
def _store(tmp_path, monkeypatch):
    from hub.features import missions as M
    monkeypatch.setattr(M, "MISSIONS_DIR", tmp_path)
    st = M.Store()
    got = []
    monkeypatch.setattr(events, "publish", lambda k, p=None: got.append((k, p)))
    return M, st, got


def test_a_mission_reaching_review_is_announced_once(tmp_path, monkeypatch):
    M, st, got = _store(tmp_path, monkeypatch)
    m = M.Mission(id="m1", project_slug="p", project_name="P", project_path=str(tmp_path),
                  brief="b", agent="coder", kind="single", status="running")
    st.save(m)                                   # first sight: running, nothing to say
    m.status = "awaiting_review"
    st.save(m)
    st.save(m)                                   # a later chunk with no change
    assert [k for k, _ in got] == ["mission.finished"], "exactly one announcement"


def test_a_restart_does_not_announce_every_old_mission(tmp_path, monkeypatch):
    """Re-reading finished missions from disk at boot must not fire automations."""
    M, st, got = _store(tmp_path, monkeypatch)
    old = M.Mission(id="m2", project_slug="p", project_name="P", project_path=str(tmp_path),
                    brief="b", agent="coder", kind="single", status="applied")
    st.save(old)                                 # never seen before, already terminal
    assert got == []


def test_needs_you_is_announced_even_on_first_sight(tmp_path, monkeypatch):
    """A mission that comes back from disk still waiting really does need you."""
    M, st, got = _store(tmp_path, monkeypatch)
    m = M.Mission(id="m3", project_slug="p", project_name="P", project_path=str(tmp_path),
                  brief="b", agent="coder", kind="single", status="needs_input")
    st.save(m)
    assert [k for k, _ in got] == ["mission.needs_you"]
