"""Talk to a coding agent over the Agent Client Protocol (ACP), so one piece of code serves every agent that speaks it.

ACP is JSON-RPC 2.0, one message per line, over the agent's stdin and stdout. The Hub is the *client*: it starts the agent
as a subprocess, sends `initialize`, `session/new` and `session/prompt`, reads the `session/update` notifications that stream
back, and answers the agent's own requests. The one that matters is `session/request_permission`: the agent wants to run
something and asks. Here that becomes an item in "Needs attention" that you answer from the board, instead of a prompt in a
terminal nobody is looking at. File and terminal requests are refused: the Hub does not offer those capabilities, the agent
uses its own tools in its own working copy.

Method names are from the ACP overview (agentclientprotocol.com): `initialize`, `session/new`, `session/prompt`,
`session/update`, `session/cancel`, `session/request_permission`. Licence of the protocol text: not stated on that page.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid

from aiohttp import web

from ..config import logger

routes = web.RouteTableDef()

PROTOCOL = 1
PENDING: "dict[str, dict]" = {}          # permission questions waiting for a person
ASK_TIMEOUT_S = 600


class ACPError(Exception):
    pass


class Agent:
    """One running ACP agent."""

    def __init__(self, cmd: "list[str]", cwd: "str | None" = None, label: str = "agent", on_update=None):
        self.cmd, self.cwd, self.label, self.on_update = cmd, cwd, label, on_update
        self.proc: "asyncio.subprocess.Process | None" = None
        self._id = 0
        self._waiting: "dict[int, asyncio.Future]" = {}
        self._reader: "asyncio.Task | None" = None
        self.capabilities: dict = {}
        self.updates: "list[dict]" = []

    async def start(self) -> None:
        self.proc = await asyncio.create_subprocess_exec(*self.cmd, cwd=self.cwd, stdin=asyncio.subprocess.PIPE,
                                                         stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        self._reader = asyncio.ensure_future(self._read())

    async def close(self) -> None:
        if self._reader:
            self._reader.cancel()
        if self.proc and self.proc.returncode is None:
            try:
                self.proc.kill()
                await asyncio.wait_for(self.proc.wait(), 2)
            except Exception:  # noqa: BLE001
                pass

    async def _send(self, msg: dict) -> None:
        assert self.proc and self.proc.stdin
        self.proc.stdin.write((json.dumps(msg) + "\n").encode())
        await self.proc.stdin.drain()

    async def request(self, method: str, params: dict, timeout: float = 30) -> dict:
        self._id += 1
        fut = asyncio.get_running_loop().create_future()
        self._waiting[self._id] = fut
        await self._send({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params})
        res = await asyncio.wait_for(fut, timeout)
        if "error" in res:
            raise ACPError(str(res["error"])[:200])
        return res.get("result") or {}

    async def _read(self) -> None:
        assert self.proc and self.proc.stdout
        while True:
            line = await self.proc.stdout.readline()
            if not line:
                for f in self._waiting.values():
                    if not f.done():
                        f.set_exception(ACPError("the agent exited"))
                return
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if "method" in msg and "id" in msg:                  # the agent asks us something
                asyncio.ensure_future(self._serve(msg))
            elif "method" in msg:                                # a notification
                if msg["method"] == "session/update":
                    self.updates.append(msg.get("params") or {})
                    if self.on_update:
                        try:
                            self.on_update(msg.get("params") or {})
                        except Exception:  # noqa: BLE001
                            pass
            elif "id" in msg and msg["id"] in self._waiting:
                f = self._waiting.pop(msg["id"])
                if not f.done():
                    f.set_result(msg)

    async def _serve(self, msg: dict) -> None:
        method, params, mid = msg["method"], msg.get("params") or {}, msg["id"]
        if method == "session/request_permission":
            outcome = await ask_person(self.label, params)
            await self._send({"jsonrpc": "2.0", "id": mid, "result": {"outcome": outcome}})
        else:                                                    # file system, terminals: not offered
            await self._send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"{method} is not offered by this client"}})

    # -- the three calls a client needs ---------------------------------------------------------------------------
    async def initialize(self) -> dict:
        r = await self.request("initialize", {"protocolVersion": PROTOCOL, "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False}})
        self.capabilities = r
        return r

    async def new_session(self, cwd: str) -> str:
        return (await self.request("session/new", {"cwd": cwd, "mcpServers": []})).get("sessionId", "")

    async def prompt(self, session: str, text: str, timeout: float = 900) -> str:
        r = await self.request("session/prompt", {"sessionId": session, "prompt": [{"type": "text", "text": text}]}, timeout=timeout)
        return str(r.get("stopReason") or "")

    async def cancel(self, session: str) -> None:
        await self._send({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": session}})


async def ask_person(label: str, params: dict) -> dict:
    """Park the agent's permission question where a person will see it, and wait for the answer."""
    qid = "q" + uuid.uuid4().hex[:8]
    tool = (params.get("toolCall") or {})
    options = [{"id": o.get("optionId"), "name": o.get("name"), "kind": o.get("kind")} for o in (params.get("options") or [])]
    fut = asyncio.get_running_loop().create_future()
    PENDING[qid] = {"id": qid, "agent": label, "title": str(tool.get("title") or tool.get("kind") or "an action")[:120], "options": options,
                    "asked": time.time(), "future": fut}
    logger.info("acp: %s asks permission: %s", label, PENDING[qid]["title"])
    try:
        chosen = await asyncio.wait_for(fut, ASK_TIMEOUT_S)
        return {"outcome": "selected", "optionId": chosen}
    except asyncio.TimeoutError:
        return {"outcome": "cancelled"}                         # nobody answered: the answer is no
    finally:
        PENDING.pop(qid, None)


def pending() -> "list[dict]":
    return [{k: v for k, v in q.items() if k != "future"} for q in PENDING.values()]


def answer(qid: str, option_id: "str | None") -> bool:
    q = PENDING.get(qid)
    if not q or q["future"].done():
        return False
    if option_id is None or option_id not in [o["id"] for o in q["options"]]:
        q["future"].set_result(next((o["id"] for o in q["options"] if str(o.get("kind", "")).startswith("reject")), None))
    else:
        q["future"].set_result(option_id)
    return True


@routes.get("/api/acp/pending")
async def api_pending(request: web.Request) -> web.Response:
    return web.json_response({"pending": pending()})


@routes.post("/api/acp/answer")
async def api_answer(request: web.Request) -> web.Response:
    try:
        b = await request.json()
    except Exception:  # noqa: BLE001
        b = {}
    if not answer(str(b.get("id") or ""), b.get("option")):
        raise web.HTTPNotFound(text="no such question, or it was already answered")
    return web.json_response({"ok": True})


@routes.post("/api/acp/probe")
async def api_probe(request: web.Request) -> web.Response:
    """Start an agent only far enough to learn what it supports. No prompt is sent, so nothing is spent or changed."""
    from . import opencode as OC
    ag = Agent([str(OC.OPENCODE_EXE), "acp"], label="opencode")
    try:
        await ag.start()
        info = await asyncio.wait_for(ag.initialize(), 20)
        return web.json_response({"ok": True, "agent": "opencode", "info": info})
    except Exception as exc:  # noqa: BLE001
        return web.json_response({"ok": False, "agent": "opencode", "why": f"{type(exc).__name__}: {str(exc)[:160]}"})
    finally:
        await ag.close()
