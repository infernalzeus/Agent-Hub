"""pytest: never collect the hub's own data folder (mission working copies there are whole copies of the repo, tests included)."""
collect_ignore_glob = ["data/*"]

import pytest


@pytest.fixture(autouse=True)
def _knobs_file_is_private_to_each_test(tmp_path, monkeypatch):
    """The learning layer's adjustable numbers live in a file on this PC; a test must never read yours or write to it."""
    try:
        from hub.yard import knobs as K
    except ImportError:
        return
    monkeypatch.setattr(K, "FILE", tmp_path / "knobs.json")
    K._CACHE.update(mtime=None, data={}, file=None)



@pytest.fixture(autouse=True)
def _the_users_learning_data_is_never_a_test_scratchpad(tmp_path, monkeypatch):
    """A test once wrote made-up requests into the real decision log and made-up screens into the real shadow memory. Every test starts with both pointing at its own
    folder; a test that wants a particular file still sets its own."""
    mine = tmp_path / "_private"
    try:
        from hub.yard import memory as MEM
        monkeypatch.setattr(MEM, "MEMORY_STEPS", mine / "memory_steps.jsonl")
    except ImportError:
        pass
    try:
        from hub.features import binning as BIN
        monkeypatch.setattr(BIN, "LOG", mine / "utterance_decisions.jsonl")
    except ImportError:
        pass
