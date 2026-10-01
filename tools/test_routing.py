"""Repetition must never promote an ask into something heavier than it is.

The rule these protect: "open Apple Music" is one call, and "open Apple Music
every morning" is the same call with a clock on it. Getting this wrong is
expensive in the direction nobody notices - a saved automation nobody asked for,
or a request to record a routine for something that had a command all along.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hub.features.routing import classify, read_trigger, shape   # noqa: E402


# -- the Apple Music rule -----------------------------------------------------
def test_a_one_step_ask_is_a_call():
    assert classify("open Apple Music", "cli", 1)["kind"] == "call"


def test_repeating_it_is_still_a_call():
    got = classify("open Apple Music every morning at 8", "cli", 1)
    assert got["kind"] == "call", "repetition must not promote it"
    assert got["trigger"]["kind"] == "schedule"
    assert got["note"], "the page should say so out loud"


@pytest.mark.parametrize("ask", [
    "every day at 9 tidy the downloads",
    "each morning check the repos",
    "nightly back up the notes",
    "weekly summarise my commits",
])
def test_a_clock_is_a_trigger_not_a_kind(ask):
    assert classify(ask, "hub", 1)["kind"] == "call"


# -- climbing only when the step below cannot do it ---------------------------
def test_several_steps_is_an_automation():
    assert classify("download it then upload it", "hub", 2)["kind"] == "automation"


def test_no_machine_interface_needs_a_routine():
    assert classify("press export in that old app", "gui", 1)["kind"] == "routine"


def test_a_gui_thing_with_several_steps_is_still_an_automation():
    assert shape(3, "gui") == "automation"


def test_something_absent_is_blocked_not_invented():
    assert classify("use a program I never installed", "absent", 1)["kind"] == "blocked"


# -- what it refuses to decide ------------------------------------------------
def test_without_a_verdict_it_asks_rather_than_guesses():
    got = classify("open Apple Music")
    assert got["needs_scout"] is True
    assert "kind" not in got, "it must not invent a kind from the wording alone"


# -- reading the trigger ------------------------------------------------------
def test_a_plain_ask_runs_once():
    assert read_trigger("tidy my downloads")["kind"] == "manual"


def test_an_event_is_recognised():
    assert read_trigger("when a download finishes, tag it")["kind"] == "event"


def test_a_time_is_picked_up_and_a_missing_one_is_not_invented():
    assert read_trigger("every day at 7pm")["at"] == "19:00"
    vague = read_trigger("every day")
    assert vague["at"] == "09:00" and vague["sure"] is False, "a default must admit it is one"


def test_asking_you_to_do_something_is_not_an_event():
    """'when you have finished' is addressed to the agent, not a trigger."""
    assert read_trigger("when you are done, tell me")["kind"] == "manual"
