"""A routine that worked must be found again however the request is worded. 'play something from the ADHD playlist', 'play music from the ADHD playlist' and 'play the ADHD list'
are one job; they used to be three, so the saved routine was never found and the slow step-by-step agent (about 70 seconds) ran every time. Tested against a throwaway routine
database, never yours."""
import pytest

from hub.features import pc_control as PC

SAME = ["play something from the adhd playlist", "play music from the ADHD playlist", "play the ADHD list", "Play ADHD", "put on the adhd playlist please", "shuffle the ADHD playlist"]


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(PC, "DB_PATH", tmp_path / "pc_control.sqlite")
    return tmp_path


def _save(intent, status="candidate", successes=0):
    PC.save_ui_routine(intent, "Apple Music: " + intent, "Apple Music", [{"tool": "Click", "target": {"name": "ADHD"}}], {"window": "Apple Music", "fingerprint": "x"})
    with PC._db() as d:
        d.execute("UPDATE pc_routines SET status=?, successes=? WHERE intent=?", (status, successes, intent))


def test_every_wording_of_one_play_request_has_one_key():
    keys = {PC.do_intent("apple music", s) for s in SAME}
    assert keys == {"do:apple music:play:adhd"}


def test_different_things_and_different_jobs_keep_different_keys():
    assert PC.do_intent("apple music", "play the robelec speedplay list") == "do:apple music:play:robelec speedplay"
    assert PC.do_intent("apple music", "open the adhd playlist") != PC.do_intent("apple music", "play the adhd playlist")      # opening a page is not playing it
    assert PC.do_intent("apple music", "play ADHD") != PC.do_intent("apple music", "play focus flow")
    assert PC.do_intent("notepad", "play ADHD") != PC.do_intent("apple music", "play ADHD")


@pytest.mark.parametrize("said", SAME)
def test_a_routine_saved_under_the_old_key_is_found_for_any_wording(db, said):
    _save("do:apple music:play:adhd playlist something")                       # how the real one was stored before the wording was ignored
    got = PC.routine_for_do("apple music", said)
    assert got and got["intent"] == "do:apple music:play:adhd playlist something"


def test_it_does_not_answer_for_another_playlist_or_another_app(db):
    _save("do:apple music:play:adhd playlist something")
    assert PC.routine_for_do("apple music", "play the focus flow playlist") is None
    assert PC.routine_for_do("spotify", "play the adhd playlist") is None
    assert PC.routine_for_do("apple music", "open the adhd playlist") is None


def test_a_trusted_routine_wins_over_a_candidate_and_a_disabled_one_is_ignored(db):
    _save("do:apple music:play:adhd playlist something", "candidate", 0)
    _save("do:apple music:play:adhd music", "trusted", 5)
    assert PC.routine_for_do("apple music", "play ADHD")["intent"] == "do:apple music:play:adhd music"
    with PC._db() as d:
        d.execute("UPDATE pc_routines SET status='disabled' WHERE intent='do:apple music:play:adhd music'")
    assert PC.routine_for_do("apple music", "play ADHD")["intent"] == "do:apple music:play:adhd playlist something"
