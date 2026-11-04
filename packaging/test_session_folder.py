"""A session row carries its folder, its last message and its kind; opening the folder only ever uses a folder the log scan reported."""
import asyncio
import json
import os
import time

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from hub.features import agent_sessions as AS, home_state as HS


def _lines(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _setup(tmp_path, monkeypatch):
    work = tmp_path / "work" / "repo"
    work.mkdir(parents=True)
    claude, codex = tmp_path / "claude", tmp_path / "codex"
    _lines(claude / "proj" / "abcdef123456.jsonl", [
        {"type": "user", "cwd": str(work), "message": {"content": "fix the clicks"}},
        {"type": "assistant", "cwd": str(work), "message": {"content": [{"type": "text", "text": "Done, the tolerance is wider now."}], "stop_reason": "end_turn"}}])
    _lines(codex / "2026" / "rollout-1.jsonl", [
        {"type": "session_meta", "payload": {"cwd": str(work)}},
        {"type": "event_msg", "payload": {"type": "agent_message", "message": "Layout checked."}}])
    monkeypatch.setattr(AS, "CLAUDE_DIR", claude)
    monkeypatch.setattr(AS, "CODEX_DIR", codex)
    return work


def test_rows_carry_folder_last_message_and_kind(tmp_path, monkeypatch):
    work = _setup(tmp_path, monkeypatch)
    rows = {r["agent"]: r for r in AS.scan(time.time())}
    assert rows["claude"]["cwd"] == str(work) and "tolerance" in rows["claude"]["last"]
    assert rows["codex"]["cwd"] == str(work) and rows["codex"]["last"] == "Layout checked."     # Codex names its folder only in the first line
    s = HS._sess(rows["claude"])
    assert s["kind"] == "agent-log" and s["cwd"] == str(work) and s["last"]


def test_open_folder_uses_only_a_folder_the_scan_reported(tmp_path, monkeypatch):
    work = _setup(tmp_path, monkeypatch)
    opened = []
    monkeypatch.setattr(os, "startfile", lambda p: opened.append(p), raising=False)

    async def go():
        app = web.Application(); app.add_routes(HS.routes)
        async with TestClient(TestServer(app)) as c:
            assert (await c.post("/api/sessions/open-folder", json={"id": "abcdef123456"})).status == 200
            assert opened == [str(work)]
            assert (await c.post("/api/sessions/open-folder", json={"id": "nope"})).status == 404
            assert (await c.post("/api/sessions/open-folder", json={"id": "C:/Windows", "path": "C:/Windows"})).status == 404
            assert (await c.post("/api/sessions/open-folder", data="x")).status == 400
            assert opened == [str(work)]                                     # nothing else was opened
    asyncio.run(go())
