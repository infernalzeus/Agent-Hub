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
        from hub.features import pc_control as PC                       # the saved routines: a test that looked them up found the real ADHD one and tried to replay it
        monkeypatch.setattr(PC, "DB_PATH", mine / "pc_control.sqlite")
    except ImportError:
        pass
    try:
        from hub.features import binning as BIN
        monkeypatch.setattr(BIN, "LOG", mine / "utterance_decisions.jsonl")
    except ImportError:
        pass


@pytest.fixture(autouse=True)
def _no_test_reaches_the_real_pc(monkeypatch):
    """A test run once opened Apple Music on the maker's PC: a replay test with an empty screen reached the real app launcher. Every call that would press, open or read something on this
    PC (the Windows MCP tools) now raises unless the test replaces it with its own fake. A test that really wants this PC sets AGENTHUB_REAL_PC=1 and says why."""
    import os
    if os.environ.get("AGENTHUB_REAL_PC") == "1":
        return
    try:
        from hub.features import mcp as MCP
    except ImportError:
        return

    async def refused(name, tool, args, timeout=90):
        raise AssertionError(f"a test reached the real PC: MCP {name}.{tool} {str(args)[:80]}. Fake MCP.call_tool in the test.")
    monkeypatch.setattr(MCP, "call_tool", refused)
    try:                                                       # the fast way to open an app starts a real program: a test that wants it fakes it
        from hub.features import pc_control as _PC

        async def no_fast_open(name):
            return None
        monkeypatch.setattr(_PC, "_fast_open", no_fast_open)

        async def no_bring_forward(app):                           # nor may a test move this PC's windows about
            return {"app": app, "window": None, "minimised": None, "foreground": None, "locked": None}
        monkeypatch.setattr(_PC, "_bring_forward", no_bring_forward)
    except ImportError:
        pass


def pytest_configure(config):
    """AGENTHUB_TEST_BROWSER=bundled runs the browser tests on Playwright's own Chromium instead of the system Edge. A box where Edge cannot be launched by a script (a locked-down
    profile, or an agent's sandbox) otherwise fails the first browser test, and the leaked Playwright loop turns every later test into an error."""
    import os
    if os.environ.get("AGENTHUB_TEST_BROWSER") != "bundled":
        return
    try:
        from playwright.sync_api import BrowserType
    except ImportError:
        return
    original = BrowserType.launch

    def launch(self, *args, **kwargs):
        kwargs.pop("channel", None)
        return original(self, *args, **kwargs)
    BrowserType.launch = launch
