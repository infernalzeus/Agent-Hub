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

