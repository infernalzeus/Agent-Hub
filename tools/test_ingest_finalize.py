"""An ingest that produced no manifest must not look finished.

Found by running the thing: a model answered BLOCKED on its first tool call,
never listing the folder. The run exited 0, so the mission went to
`awaiting_review` with an empty feed and no error — and APPLY could only refuse.
The user's only clue was a blank review screen.
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from hub.features import missions as M  # noqa: E402


def _mission(tmp_path: Path, kind: str) -> M.Mission:
    return M.Mission(
        id="mtest0001", kind=kind, brief="wire in this app",
        project_path=str(tmp_path), project_slug="thing", project_name="Thing",
        worktree=str(tmp_path), branch="agent/thing", base_branch="main",
        agent="app-ingestor", status="running", created=time.time(),
    )


def _finalize(m, wt, data_dir, rc=0):
    asyncio.run(M._finalize(m, wt, data_dir, rc, False))


def test_ingest_without_manifest_fails(tmp_path):
    data = tmp_path / ".ocdata"
    data.mkdir()
    m = _mission(tmp_path, "ingest-app")
    _finalize(m, tmp_path, data)
    assert m.status == "failed", "no manifest means nothing to review"
    assert "app-hub.json" in m.error


def test_the_agents_own_reason_is_kept(tmp_path):
    data = tmp_path / ".ocdata"
    data.mkdir()
    (data / "mission.jsonl").write_text(
        json.dumps({"type": "text", "part": {"text": "BLOCKED: no app files present."}}) + "\n",
        encoding="utf-8")
    m = _mission(tmp_path, "ingest-app")
    _finalize(m, tmp_path, data)
    assert m.status == "failed"
    assert m.error.startswith("BLOCKED: no app files present"), m.error


def test_ingest_with_a_manifest_still_reaches_review(tmp_path):
    data = tmp_path / ".ocdata"
    data.mkdir()
    (tmp_path / "app-hub.json").write_text(
        json.dumps({"id": "thing", "cmd": ["node", "server.js"], "port": 8110}), encoding="utf-8")
    m = _mission(tmp_path, "ingest-app")
    _finalize(m, tmp_path, data)
    assert m.status == "awaiting_review", m.status


def test_other_missions_are_untouched(tmp_path):
    """A coding mission has no manifest and must not be failed for it."""
    data = tmp_path / ".ocdata"
    data.mkdir()
    m = _mission(tmp_path, "single")
    _finalize(m, tmp_path, data)
    assert m.status == "awaiting_review", m.status


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


# ── the lockfile guard ────────────────────────────────────────────────────────
# Seen for real: the agent wrote `npm ci` for a project with no package-lock.json,
# because the agent's own instructions used `npm ci` as the example. That install
# fails, so the app registers and then breaks the first time it is opened.

def test_npm_ci_without_a_lockfile_is_swapped(tmp_path):
    man = {"install": ["npm", "ci"]}
    note = M._fix_lockfile_install(man, tmp_path)
    assert man["install"] == ["npm", "install"]
    assert "package-lock.json" in note


def test_npm_ci_with_a_lockfile_is_left_alone(tmp_path):
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")
    man = {"install": ["npm", "ci"]}
    assert M._fix_lockfile_install(man, tmp_path) == ""
    assert man["install"] == ["npm", "ci"], "a valid npm ci must survive"


def test_other_install_commands_are_untouched(tmp_path):
    for cmd in (["npm", "install"], ["$PYTHON", "-m", "pip", "install", "-r", "requirements.txt"], []):
        man = {"install": cmd}
        assert M._fix_lockfile_install(man, tmp_path) == ""
        assert man["install"] == cmd


def test_frozen_lockfile_variants(tmp_path):
    man = {"install": ["pnpm", "install", "--frozen-lockfile"]}
    assert "pnpm-lock.yaml" in M._fix_lockfile_install(man, tmp_path)
    assert man["install"] == ["pnpm", "install"]
    (tmp_path / "yarn.lock").write_text("", encoding="utf-8")
    man = {"install": ["yarn", "--frozen-lockfile"]}
    assert M._fix_lockfile_install(man, tmp_path) == "", "yarn.lock is present"


# ── the brief must state what is in the folder ────────────────────────────────
# Measured over three identical runs: one ended in 30s with "BLOCKED: No project
# files exist", having never listed the directory. The hub knows the contents, so
# it says them.

def test_listing_shows_files_and_one_level_of_folders(tmp_path):
    (tmp_path / "server.js").write_text("", encoding="utf-8")
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "public").mkdir()
    (tmp_path / "public" / "index.html").write_text("", encoding="utf-8")
    out = M._folder_listing(tmp_path)
    assert "server.js" in out and "package.json" in out
    assert "public/" in out and "public/index.html" in out


def test_listing_hides_noise_and_the_hubs_own_files(tmp_path):
    for name in ("node_modules", ".git", ".ocdata"):
        (tmp_path / name).mkdir()
    for name in ("AGENTS.md", "opencode.json", "app-hub.json", "HUB_INGEST.md"):
        (tmp_path / name).write_text("", encoding="utf-8")
    (tmp_path / "server.js").write_text("", encoding="utf-8")
    out = M._folder_listing(tmp_path)
    assert "server.js" in out
    for hidden in ("node_modules", ".git", "AGENTS.md", "app-hub.json", "HUB_INGEST.md"):
        assert hidden not in out, f"{hidden} should not be offered as one of the app's files"


def test_the_brief_carries_the_listing_and_the_shape(tmp_path):
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "server.js").write_text("", encoding="utf-8")
    brief = M._ingest_brief(str(tmp_path), "thing", "Thing", None, is_local=True, folder=tmp_path)
    assert "THE FOLDER CONTAINS" in brief
    assert "package.json" in brief
    assert "node" in brief, "the hub's own detector should be quoted to the agent"
    assert "you are reading the wrong path" in brief


def test_a_brief_without_a_folder_still_works(tmp_path):
    """A clone has no folder yet at brief time; it must not crash or claim one."""
    brief = M._ingest_brief("https://example.com/x.git", "x", None, None, is_local=False)
    assert "THE FOLDER CONTAINS" not in brief
    assert "fresh clone" in brief


def test_the_manifest_file_itself_is_repaired(tmp_path):
    """What you read at REVIEW must be what actually runs."""
    mf = tmp_path / "app-hub.json"
    mf.write_text(json.dumps({"id": "x", "cmd": ["node", "server.js"],
                              "port": 8110, "install": ["npm", "ci"]}), encoding="utf-8")
    note = M._repair_manifest(mf, tmp_path)
    assert "package-lock.json" in note
    assert json.loads(mf.read_text(encoding="utf-8"))["install"] == ["npm", "install"]


def test_a_sound_manifest_is_not_rewritten(tmp_path):
    mf = tmp_path / "app-hub.json"
    original = json.dumps({"id": "x", "cmd": ["node", "server.js"],
                           "port": 8110, "install": ["npm", "install"]})
    mf.write_text(original, encoding="utf-8")
    assert M._repair_manifest(mf, tmp_path) == ""
    assert mf.read_text(encoding="utf-8") == original, "an untouched manifest must stay byte-identical"


# ── stopping is not failing ───────────────────────────────────────────────────
# Found running the stop test: pressing STOP on a single-agent ask left it
# FAILED, in red, with the error "aborted". Nothing failed; the user changed
# their mind. The orchestrated path already said "paused by you".

def test_stopped_is_a_terminal_status():
    assert "stopped" in M._TERMINAL, "a stopped ask is over, and must be archivable"


def test_abort_says_stopped_not_failed(tmp_path, monkeypatch):
    m = _mission(tmp_path, "single")
    m.status = "running"
    monkeypatch.setitem(M.S.m, m.id, m)
    monkeypatch.setattr(M.S, "save", lambda _m: None)
    monkeypatch.setattr(M.OCM.ak_status, "worktree_changed_files",
                        lambda _p: asyncio.sleep(0, result=[]))
    asyncio.run(M.abort(m.id))
    assert m.status == "stopped", f"a stop must not read as {m.status}"
    assert m.error == "stopped by you"
    assert "abort" not in (m.error or "").lower()


def test_an_orchestrated_ask_still_pauses(tmp_path, monkeypatch):
    """It was already right, and must stay resumable rather than become stopped."""
    m = _mission(tmp_path, "orchestrator")
    m.status = "running"
    m.plan = [{"id": "s1", "status": "running"}]
    monkeypatch.setitem(M.S.m, m.id, m)
    monkeypatch.setattr(M.S, "save", lambda _m: None)
    monkeypatch.setattr(M.OCM.ak_status, "worktree_changed_files",
                        lambda _p: asyncio.sleep(0, result=[]))
    asyncio.run(M.abort(m.id))
    assert m.status == "paused", m.status
