"""The bandit: no opinion until two options have a trusted record; then the better record; replayed against the log it only ever uses earlier events."""
from hub.features import bandit as B


def ev(chosen, ok, ctx="small", kind="model"):
    return {"kind": kind, "context": ctx, "chosen": chosen, "ok": ok}


def test_no_opinion_with_one_option_or_too_few_results():
    assert B.advise({"a": {"ok": 5, "failed": 0}})["would"] is None
    assert B.advise({"a": {"ok": 2, "failed": 0}, "b": {"ok": 1, "failed": 1}})["would"] is None


def test_prefers_the_better_record_and_a_perfect_one_of_one_does_not_beat_a_long_good_one():
    t = {"a": {"ok": 8, "failed": 2}, "b": {"ok": 3, "failed": 0}}
    assert B.advise(t)["would"] == "b"                     # 3 of 3 (0.80 with the prior) edges 8 of 10 (0.75); both are trusted
    assert B.advise({"a": {"ok": 9, "failed": 1}, "b": {"ok": 1, "failed": 0}})["would"] is None   # b is not yet trusted


def test_replay_judges_each_decision_only_by_what_came_before_it():
    log = [ev("a", True)] * 3 + [ev("b", False)] * 3 + [ev("b", True), ev("a", True)]
    r = B.replay(log, "model")
    assert r["decided"] == 8
    assert r["had_an_opinion"] == 2                       # only the last two came after both options had three results
    assert r["differed"] == 1                             # it would have picked a, and b was really chosen once


def test_unlabelled_choices_are_counted_but_teach_nothing():
    log = [ev("a", None)] * 10 + [ev("b", None)] * 10
    r = B.replay(log, "model")
    assert r == {"decided": 20, "had_an_opinion": 0, "agreed": 0, "differed": 0}
