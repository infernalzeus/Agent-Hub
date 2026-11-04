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


def test_a_codex_session_shows_what_was_asked_and_the_last_reply_and_its_own_review_sessions_are_hidden(tmp_path, monkeypatch):
    work = tmp_path / "proj"
    work.mkdir()
    codex = tmp_path / "codex"
    ctx = {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "<recommended_plugins>x</recommended_plugins>"}]}}
    ask = {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "make the hands scroll like a touch screen"}]}}
    reply = {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Done: a pinch now scrolls."}]}}
    _lines(codex / "2026" / "rollout-a.jsonl", [{"type": "session_meta", "payload": {"cwd": str(work)}}, ctx, ask, reply])
    review = {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "The following is the Codex agent history added since your last approval decision"}]}}
    _lines(codex / "2026" / "rollout-b.jsonl", [{"type": "session_meta", "payload": {"cwd": str(work)}}, review])
    monkeypatch.setattr(AS, "CLAUDE_DIR", tmp_path / "none")
    monkeypatch.setattr(AS, "CODEX_DIR", codex)
    rows = AS.scan(time.time())
    assert len(rows) == 1                                               # the review session is not a conversation
    assert rows[0]["title"] == "make the hands scroll like a touch screen" and "pinch now scrolls" in rows[0]["last"] and rows[0]["project"] == "proj"
