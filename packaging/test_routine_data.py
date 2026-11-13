"""Your trusted routines as learning data: the router gets the request each answers, the learner imitates the steps, and a share is kept out as a test. The routine store is replaced by fakes."""
import pytest

from hub.yard import knobs as K, routine_data as RD, tev_dataset as TEV

pytest.importorskip("numpy")


def _rt(i, title, tool="ui", steps=None):
    return {"id": f"r{i}", "title": title, "text": RD._sentence(title), "bin": "launch_app" if tool in RD.LAUNCH else "app_task", "successes": 3, "failures": 0,
            "steps": steps if steps is not None else []}


PLAY = [{"role": "list item", "name": "Playlists", "confidence": 1.0}, {"role": "list item", "name": "ADHD", "confidence": 0.9}, {"role": "button", "name": "Play", "confidence": None}]


@pytest.fixture(autouse=True)
def knobs(tmp_path, monkeypatch):
    monkeypatch.setattr(K, "FILE", tmp_path / "knobs.json")
    return K


def test_each_trusted_routine_is_one_router_example_with_its_bin(monkeypatch):
    monkeypatch.setattr(RD, "trusted", lambda: [_rt(1, "Open Apple Music", "App"), _rt(2, "Apple Music: play something from the adhd playlist", steps=PLAY)])
    rows = RD.router_rows()
    assert [(r["text"], r["label"]) for r in rows] == [("Open Apple Music", "launch_app"), ("Apple Music play something from the adhd playlist", "app_task")]


def test_the_fine_tune_plan_counts_them_beside_the_graded_requests(monkeypatch):
    monkeypatch.setattr(RD, "trusted", lambda: [_rt(1, "Open Apple Music", "App"), _rt(2, "Open Claude", "App"), _rt(3, "Open Notepad", "App")])
    p = TEV.plan()
    assert p["from_trusted_routines"] == 3 and p["rows"] >= 3 and p["needed"] == 100 and p["routines"]["sentences"] == 3


def test_fewer_than_three_routines_all_train_and_three_or_more_keep_some_out(monkeypatch):
    two = [_rt(1, "Open Apple Music", "App"), _rt(2, "Open Claude", "App")]
    assert RD.split(two) == (two, [])
    many = [_rt(i, f"Open app number {i}", "App") for i in range(40)]
    train, held = RD.split(many)
    assert held and train and len(train) + len(held) == 40 and not set(r["id"] for r in train) & set(r["id"] for r in held)


def test_a_learner_that_imitates_the_steps_gives_the_routines_press_more_probability():
    rts = [_rt(2, "Apple Music: play something from the adhd playlist", steps=PLAY)]
    from hub.yard import learner as L
    lr = L.Learner(hidden=0, seed=1)
    before = lr.imitate_screens(RD.screens(rts, seed=0))
    for _ in range(30):
        lr.imitate_screens(RD.screens(rts, seed=3))
    after = lr.imitate_screens(RD.screens(rts, seed=0))
    assert after > before and after > 0.5, (before, after)


def test_the_models_confidence_lowers_a_steps_weight_but_never_below_half(monkeypatch):
    rts = [_rt(2, "play", steps=[{"role": "button", "name": "Play", "confidence": 0.1}, {"role": "button", "name": "Next", "confidence": 1.0}])]
    w = [x[2] for x in RD.screens(rts, seed=0)]
    assert min(w) == 0.5 and max(w) == 1.0


def test_the_switch_turns_all_of_it_off(monkeypatch):
    monkeypatch.setattr(RD, "trusted", lambda: [_rt(1, "Open Apple Music", "App")])
    K.set_many({"routine_data": False})
    assert RD.router_rows() == []
