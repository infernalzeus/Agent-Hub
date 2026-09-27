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
