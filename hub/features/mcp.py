"""MCP servers OpenCode is configured with (opencode.json in the OpenCode install folder -> "mcp"), and a safe on/off switch.

  GET  /api/mcp                       every server: enabled?, command, which tools are excluded, installed?
  POST /api/mcp/{name}/enabled        {enabled: bool}  flips ONLY that flag (a timestamped backup is kept the first time each day)

The hub never edits a server's command or tool list; adding or changing servers stays a deliberate manual edit. `enabled` is what missions
see: a disabled server is not started, so its tools do not exist for any agent. Windows MCP is registered with PowerShell, Registry,
FileSystem and Process excluded, so even when ON it can only drive the UI (click, type, screenshots, apps, clipboard, scraping).
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from aiohttp import web

from ..config import logger
from . import opencode as OCM

routes = web.RouteTableDef()


def _cfg_path() -> Path:
    return Path(OCM.OPENCODE_CONFIG)


def _read() -> dict:
    try:
        return json.loads(_cfg_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def servers() -> list[dict]:
    out = []
    for name, v in ((_read().get("mcp")) or {}).items():
        cmd = v.get("command") or []
        cmd = cmd if isinstance(cmd, list) else [str(cmd)]
        excl = ""
        if "--exclude-tools" in cmd:
            i = cmd.index("--exclude-tools")
            excl = cmd[i + 1] if i + 1 < len(cmd) else ""
        exe = cmd[0] if cmd else ""
        out.append({"name": name, "enabled": bool(v.get("enabled", True)), "type": v.get("type", "local"), "command": cmd,
                    "excluded_tools": [t for t in excl.split(",") if t], "installed": bool(exe) and Path(exe).exists()})
    return out


def set_enabled(name: str, enabled: bool) -> dict:
    cfg = _read()
    m = (cfg.get("mcp") or {}).get(name)
    if m is None:
        raise KeyError(name)
    if bool(m.get("enabled", True)) == enabled:
        return {"changed": False, "enabled": enabled}
    if enabled and not Path((m.get("command") or [""])[0]).exists():
        raise FileNotFoundError("the server program is not installed at the configured path")
    p = _cfg_path()
    bak = p.with_name(f"{p.name}.bak_{time.strftime('%Y%m%d')}")
    if not bak.exists():
        shutil.copy2(p, bak)
    m["enabled"] = enabled
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    os.replace(tmp, p)
    return {"changed": True, "enabled": enabled}


_PROBE = ("import asyncio,json,sys,os\nfrom mcp import ClientSession, StdioServerParameters\nfrom mcp.client.stdio import stdio_client\n"
          "cmd=json.loads(sys.argv[1]); env=dict(os.environ); env.update(json.loads(sys.argv[2]))\n"
          "async def main():\n p=StdioServerParameters(command=cmd[0],args=cmd[1:],env=env)\n async with stdio_client(p) as (r,w):\n  async with ClientSession(r,w) as s:\n"
          "   await asyncio.wait_for(s.initialize(),40); t=await asyncio.wait_for(s.list_tools(),40); print(json.dumps(sorted(x.name for x in t.tools)))\n"
          "asyncio.run(asyncio.wait_for(main(),80))\n")


async def probe(name: str) -> dict:
    """Start the server just long enough to list its tools, then stop it. Nothing is clicked, typed or opened."""
    import asyncio
    import subprocess
    m = ((_read().get("mcp")) or {}).get(name)
    if not m:
        raise KeyError(name)
    cmd = m.get("command") or []
    py = Path(cmd[0]).parent / "python.exe"
    if not py.exists():
        raise FileNotFoundError("cannot find the server's Python next to its program")
    env = {k: str(v) for k, v in (m.get("environment") or {}).items()}

    def run():
        r = subprocess.run([str(py), "-c", _PROBE, json.dumps(cmd), json.dumps(env)], capture_output=True, text=True, timeout=100)
        return r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "", r.stderr[-300:]
    out, err = await asyncio.get_running_loop().run_in_executor(None, run)
    try:
        return {"tools": json.loads(out)}
    except Exception:
        raise RuntimeError("the server did not answer: " + err.replace("\n", " ")[-160:])


_CALL = ("import asyncio,json,sys,os\nfrom mcp import ClientSession, StdioServerParameters\nfrom mcp.client.stdio import stdio_client\n"
         "cmd=json.loads(sys.argv[1]); env=dict(os.environ); env.update(json.loads(sys.argv[2])); tool=sys.argv[3]; args=json.loads(sys.argv[4])\n"
         "async def main():\n p=StdioServerParameters(command=cmd[0],args=cmd[1:],env=env)\n async with stdio_client(p) as (r,w):\n  async with ClientSession(r,w) as s:\n"
         "   await asyncio.wait_for(s.initialize(),40); out=await asyncio.wait_for(s.call_tool(tool,arguments=args),40); print(json.dumps({'error':bool(getattr(out,'isError',False)),'text':[getattr(x,'text',str(x)) for x in getattr(out,'content',[])]}))\n"
         "asyncio.run(asyncio.wait_for(main(),80))\n")


# A fresh client process per call costs about 4 s of start-up before any work (measured on this PC: 5.5 s a call
# one-shot, 1.4 s a call inside one session). A short-lived helper keeps ONE session open between calls and exits
# on its own after HUB_MCP_KEEPALIVE_S idle seconds (0 switches it off), so nothing stays running while the PC is
# used for something else. It runs in the server's own Python because that is where the `mcp` package is.
KEEPALIVE_S = float(os.environ.get("HUB_MCP_KEEPALIVE_S", "45") or 0)

_SERVE = ("import asyncio,json,sys,os\nfrom mcp import ClientSession, StdioServerParameters\nfrom mcp.client.stdio import stdio_client\n"
          "cmd=json.loads(sys.argv[1]); env=dict(os.environ); env.update(json.loads(sys.argv[2])); idle=float(sys.argv[3])\n"
          "def out(o):\n sys.stdout.write('@@'+json.dumps(o)+chr(10)); sys.stdout.flush()\n"
          "async def main():\n p=StdioServerParameters(command=cmd[0],args=cmd[1:],env=env)\n async with stdio_client(p) as (r,w):\n  async with ClientSession(r,w) as s:\n"
          "   await asyncio.wait_for(s.initialize(),40); out({'ready':True}); loop=asyncio.get_running_loop()\n"
          "   while True:\n    try: line=await asyncio.wait_for(loop.run_in_executor(None,sys.stdin.readline),idle)\n    except asyncio.TimeoutError: return\n"
          "    if not line.strip(): return\n    q=json.loads(line)\n    try:\n     o=await asyncio.wait_for(s.call_tool(q['tool'],arguments=q['args']),q.get('timeout',60))\n"
          "     out({'id':q['id'],'error':bool(getattr(o,'isError',False)),'text':[getattr(x,'text',str(x)) for x in getattr(o,'content',[])]})\n"
          "    except Exception as e: out({'id':q['id'],'error':True,'text':[str(e)[:300]]})\n"
          "try: asyncio.run(main())\nfinally: os._exit(0)\n")

_KEEP: dict = {}
_KEEP_LOCK = threading.Lock()


def _read_marked(proc, timeout: float) -> dict:
    """The next '@@{json}' line the helper prints; other output (library chatter) is skipped."""
    box: list = []

    def reader():
        for raw in iter(proc.stdout.readline, ""):
            if raw.startswith("@@"):
                box.append(json.loads(raw[2:]))
                return
        box.append(None)
    th = threading.Thread(target=reader, daemon=True)
    th.start()
    th.join(timeout)
    if not box or box[0] is None:
        raise RuntimeError("the kept-open MCP session did not answer")
    return box[0]


def _keep_call(name: str, py: Path, cmd: list, env: dict, tool: str, args: dict, timeout: int) -> dict:
    """One call through the kept-open session, starting it if needed. Raises if the session misbehaves."""
    with _KEEP_LOCK:
        proc = _KEEP.get(name)
        if proc is None or proc.poll() is not None:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            proc = subprocess.Popen([str(py), "-c", _SERVE, json.dumps(cmd), json.dumps(env), str(KEEPALIVE_S)],
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                    encoding="utf-8", errors="replace", creationflags=flags)
            try:
                _read_marked(proc, 50)
            except Exception:
                proc.kill()
                raise
            _KEEP[name] = proc
        try:
            proc.stdin.write(json.dumps({"id": 1, "tool": tool, "args": args, "timeout": timeout}) + chr(10))
            proc.stdin.flush()
            got = _read_marked(proc, timeout + 5)
        except Exception:
            proc.kill()
            _KEEP.pop(name, None)
            raise
        return {"error": got.get("error"), "text": got.get("text") or []}


def stop_kept() -> None:
    """End any kept-open session now (tests, shutdown)."""
    with _KEEP_LOCK:
        for proc in _KEEP.values():
            try:
                proc.kill()
            except OSError:
                pass
        _KEEP.clear()


async def call_tool(name: str, tool: str, args: dict, timeout: int = 90) -> dict:
    """Invoke one configured local MCP tool: through a kept-open session when that is on, else a one-shot client process."""
    m = ((_read().get("mcp")) or {}).get(name)
    if not m:
        raise KeyError(name)
    if not bool(m.get("enabled", True)):
        raise PermissionError(f"{name} MCP is switched off")
    cmd = m.get("command") or []
    py = Path(cmd[0]).parent / "python.exe" if cmd else Path()
    if not py.exists():
        raise FileNotFoundError("cannot find the MCP server Python")
    env = {k: str(v) for k, v in (m.get("environment") or {}).items()}
    loop = asyncio.get_running_loop()
    if KEEPALIVE_S > 0:
        try:
            result = await loop.run_in_executor(None, _keep_call, name, py, cmd, env, tool, args, min(timeout, 60))
            if result.get("error"):
                raise RuntimeError("MCP tool failed: " + " ".join(result.get("text") or [])[:240])
            return result
        except RuntimeError as exc:
            if str(exc).startswith("MCP tool failed"):
                raise
            logger.info("mcp: kept-open session unavailable (%s); using a one-shot call", exc)
        except Exception as exc:  # noqa: BLE001
            logger.info("mcp: kept-open session failed (%s); using a one-shot call", exc)

    def run():
        r = subprocess.run([str(py), "-c", _CALL, json.dumps(cmd), json.dumps(env), tool, json.dumps(args)], capture_output=True, text=True, timeout=timeout)
        out = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
        return r.returncode, out, r.stderr[-400:]
    code, out, err = await loop.run_in_executor(None, run)
    try:
        result = json.loads(out)
    except Exception as exc:
        raise RuntimeError("MCP tool did not return usable JSON: " + err.replace("\n", " ")[-180:]) from exc
    if code or result.get("error"):
        raise RuntimeError("MCP tool failed: " + " ".join(result.get("text") or [err])[:240])
    return result


@routes.post("/api/mcp/{name}/probe")
async def api_mcp_probe(request: web.Request) -> web.Response:
    try:
        return web.json_response(await probe(request.match_info["name"]))
    except KeyError:
        raise web.HTTPNotFound(text="no such MCP server")
    except (FileNotFoundError, RuntimeError) as exc:
        raise web.HTTPBadRequest(text=str(exc))


@routes.get("/api/mcp")
async def api_mcp(request: web.Request) -> web.Response:
    return web.json_response({"servers": servers(), "config": str(_cfg_path())})


@routes.post("/api/mcp/{name}/enabled")
async def api_mcp_enabled(request: web.Request) -> web.Response:
    try:
        b = await request.json()
    except Exception:
        b = {}
    try:
        r = set_enabled(request.match_info["name"], bool(b.get("enabled")))
    except KeyError:
        raise web.HTTPNotFound(text="no such MCP server")
    except FileNotFoundError as exc:
        raise web.HTTPBadRequest(text=str(exc))
    return web.json_response({**r, "servers": servers(), "note": "applies to the next mission step; restart the OpenCode workspace to apply it there"})
