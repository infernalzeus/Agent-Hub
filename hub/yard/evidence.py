"""Evidence for PC tasks: what was asked, how it was done, what proved it, how sure the Hub is that it worked, and a before and an after picture.

EXPERIMENTAL and SHADOW MODE only. Nothing is written unless the shadow switch on the reinforcement-learning panel is on, and nothing here
presses, types or changes anything: it watches a task the Hub was already doing and keeps a record of it on this PC (data/yard/, never committed).

Why it exists. A task is only worth learning from if we know it really worked. "The agent said done" is not proof. So each record keeps the
markers that were seen and turns them into one number, the confidence that the task was completed:

    p = 1 - product over the markers that were SEEN of (1 - w)          noisy-or: any strong marker is enough, weak ones add up
    p = p x product over the warning signs that were seen of (f)        warning signs pull it down
    p = min(p, 0.75) unless Windows itself confirmed the result         a task nobody independently checked is never "sure"

    marker (w)                                                  warning sign (f)
    windows_confirms  0.85  Windows says it is playing           invalid      0.75  the model gave an unusable answer
    routine_clean     0.45  a saved routine ran to the end       nothing_changed 0.50 the last press changed nothing on screen
    screen_changed    0.35  the last press changed the window    false_done   0.70  it said done early and was wrong
    agent_done        0.25  the agent said it was done           stopped      0.00  you pressed stop
    few_steps         0.10  four presses or fewer

The weights are first guesses. Your RIGHT and WRONG taps in TEACH are exact labels: `calibration()` shows, for each confidence band, how often
you said it was right, so the guesses can be replaced by fitted numbers once there are about thirty labels. Until then the confidence is a
guide, not a promise.

Pictures: a small JPEG of the whole screen just before and just after (at most 640 px wide). They may show personal things, so they stay in
data/yard/evidence/, only the newest KEEP records are kept, and CLEAR removes everything.
"""
from __future__ import annotations

import asyncio
import io
import json
import re
import secrets
import time

from aiohttp import web

from ..config import logger
from ..runtime import STATE

routes = web.RouteTableDef()

DIR = STATE / "data" / "yard"
FILE = DIR / "evidence.jsonl"
SHOTS = DIR / "evidence"
LABELS = DIR / "evidence_labels.json"
KEEP = 150
MAX_W = 640
CAP_UNCHECKED = 0.75
POS = {"windows_confirms": 0.85, "routine_clean": 0.45, "screen_changed": 0.35, "agent_done": 0.25, "few_steps": 0.10}
NEG = {"invalid": 0.75, "nothing_changed": 0.50, "false_done": 0.70, "stopped": 0.0}
WORDS = {"windows_confirms": "Windows itself says the result is there (something is playing)", "routine_clean": "a saved routine ran to the end",
         "screen_changed": "the last press changed the window", "agent_done": "the agent said it was done", "few_steps": "it took four presses or fewer",
         "invalid": "the model gave an unusable answer at some step", "nothing_changed": "the last press changed nothing on screen",
         "false_done": "it said done early and was wrong", "stopped": "you pressed stop"}
_ID = re.compile(r"^\d{10}-[0-9a-f]{4}$")


def enabled() -> bool:
    from . import settings as YS
    return YS.flag("shadow")


def _pos() -> dict:
    from . import knobs as K
    return {"windows_confirms": K.get("w_windows"), "routine_clean": K.get("w_routine"), "screen_changed": K.get("w_screen"), "agent_done": K.get("w_agent"), "few_steps": K.get("w_few")}


def _neg() -> dict:
    from . import knobs as K
    return {"invalid": K.get("f_invalid"), "nothing_changed": K.get("f_nothing"), "false_done": K.get("f_false_done"), "stopped": 0.0}


def _cap() -> float:
    from . import knobs as K
    return K.get("conf_cap")


def confidence(markers: dict) -> dict:
    """{p, why, capped}: how sure we are that the task was completed. Pure function of the markers; see the module note for the arithmetic."""
    from . import knobs as K
    pos, neg, cap = _pos(), _neg(), K.get("conf_cap")
    seen = [k for k in pos if markers.get(k)]
    p = 1.0
    for k in seen:
        p *= 1.0 - pos[k]
    p = 1.0 - p
    warn = [k for k in neg if markers.get(k)]
    for k in warn:
        p *= neg[k]
    capped = not markers.get("windows_confirms") and p > cap
    if capped:
        p = cap
    return {"p": round(p, 3), "why": [WORDS[k] for k in seen] + ["warning: " + WORDS[k] for k in warn], "capped": capped}


def markers_from_trace(trace: "list[dict]", ok: bool, say: str = "", music: bool = False) -> dict:
    """The markers an agent try leaves behind. `trace` is the desktop agent's own list of steps."""
    trace = trace or []
    presses = [t for t in trace if t.get("do") in ("click", "type", "key")]
    last = presses[-1] if presses else {}
    dones = sum(1 for t in trace if t.get("do") == "done")
    return {"agent_done": bool(ok), "screen_changed": last.get("changed") is True, "nothing_changed": last.get("changed") is False,
            "invalid": any(t.get("do") == "invalid" for t in trace), "false_done": max(0, dones - (1 if ok else 0)) > 0,
            "few_steps": bool(ok) and 0 < len(presses) <= 4, "windows_confirms": bool(ok) and music and "now playing" in (say or "").casefold(),
            "stopped": any(t.get("do") == "stopped" for t in trace)}


def _grab_jpeg() -> "bytes | None":
    try:
        from ..features import machine_routines as MR
        from . import knobs as K
        im = MR._grab().convert("RGB")
        width = K.get("evidence_width")
        if im.width > width:
            im = im.resize((width, round(im.height * width / im.width)))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=K.get("jpeg_quality"), optimize=True)
        return out.getvalue()
    except Exception as exc:  # noqa: BLE001 - no screen, no picture; the record is still worth keeping
        logger.info("yard evidence: no picture: %s", exc)
        return None


async def snap() -> "bytes | None":
    """A small picture of the whole screen, or None when shadow mode is off or the screen cannot be read."""
    if not enabled():
        return None
    return await asyncio.get_running_loop().run_in_executor(None, _grab_jpeg)


def _rows() -> "list[dict]":
    try:
        return [json.loads(l) for l in FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    except (OSError, ValueError):
        return []


def _labels() -> dict:
    try:
        d = json.loads(LABELS.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def record(way: str, goal: str, app: str, ok: bool, markers: dict, seconds: float, routine: "str | None" = None,
           before: "bytes | None" = None, after: "bytes | None" = None) -> "str | None":
    """Keep one task. Returns its id, or None when shadow mode is off. Never raises."""
    if not enabled():
        return None
    try:
        rid = f"{int(time.time())}-{secrets.token_hex(2)}"
        DIR.mkdir(parents=True, exist_ok=True)
        pics = []
        for name, data in (("before", before), ("after", after)):
            if data:
                SHOTS.mkdir(parents=True, exist_ok=True)
                (SHOTS / f"{rid}-{name}.jpg").write_bytes(data)
                pics.append(name)
        conf = confidence(markers)
        from . import settings as YS
        attested = bool(routine) and routine in {r.get("id") for r in YS.golden().get("routines", [])}       # a routine you had already checked: a CHECK, never a training sample
        row = {"id": rid, "attested": attested, "at": round(time.time(), 1), "way": way, "goal": str(goal)[:160], "app": str(app)[:60], "ok": bool(ok), "seconds": round(seconds, 1),
               "markers": {k: bool(v) for k, v in markers.items()}, "confidence": conf["p"], "why": conf["why"], "capped": conf["capped"], "pics": pics, "routine": routine}
        with FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        _prune()
        return rid
    except Exception as exc:  # noqa: BLE001
        logger.info("yard evidence: could not keep a task: %s", exc)
        return None


def _prune() -> None:
    from . import knobs as K
    keep_n = K.get("evidence_keep")
    rows = _rows()
    if len(rows) <= keep_n:
        return
    old, keep = rows[:-keep_n], rows[-keep_n:]
    for r in old:
        for name in r.get("pics") or []:
            try:
                (SHOTS / f"{r['id']}-{name}.jpg").unlink()
            except OSError:
                pass
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in keep), encoding="utf-8")
    tmp.replace(FILE)


def items(limit: int = 60) -> "list[dict]":
    """Newest first. A task you HID does not come back; one you DELETED is gone."""
    labels = _labels()
    out = []
    for r in reversed(_rows()):
        lab = labels.get(r["id"])
        if lab and lab.get("grade") == "skip":
            continue
        out.append({**r, "label": lab})
        if len(out) >= limit:
            break
    return out


def calibration() -> "list[dict]":
    """For each confidence band: how many tasks you graded, and how many of those you said were right. This is what the weights get fitted to."""
    labels = _labels()
    bands = [(0.0, 0.5), (0.5, 0.75), (0.75, 0.9), (0.9, 1.01)]
    out = [{"band": f"{int(lo * 100)}-{min(100, int(hi * 100))} %", "graded": 0, "right": 0} for lo, hi in bands]
    for r in _rows():
        g = labels.get(r["id"])
        if not g or g.get("grade") not in ("right", "wrong") or r.get("attested"):      # attested routines are checks, not training samples
            continue
        for b, (lo, hi) in zip(out, bands):
            if lo <= r["confidence"] < hi:
                b["graded"] += 1
                b["right"] += g["grade"] == "right"
    return out


def summary() -> dict:
    rows, labels = _rows(), _labels()
    return {"on": enabled(), "kept": len(rows), "graded": sum(1 for r in rows if r["id"] in labels), "calibration": calibration()}


@routes.get("/api/yard/evidence")
async def api_items(request: web.Request) -> web.Response:
    return web.json_response({"on": enabled(), "items": items(), "calibration": calibration(), "keep": KEEP, "weights": {"markers": _pos(), "warnings": _neg(), "cap": _cap()}})


@routes.get("/api/yard/evidence/{id}/{which}.jpg")
async def api_pic(request: web.Request) -> web.StreamResponse:
    rid, which = request.match_info["id"], request.match_info["which"]
    if not _ID.match(rid) or which not in ("before", "after"):
        raise web.HTTPNotFound()
    p = SHOTS / f"{rid}-{which}.jpg"
    if not p.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(p, headers={"Cache-Control": "private, max-age=3600"})


@routes.post("/api/yard/evidence/{id}/label")
async def api_label(request: web.Request) -> web.Response:
    """{"grade": "right"|"wrong", "note": optional}. One exact label for how sure we should have been."""
    rid = request.match_info["id"]
    try:
        b = await request.json()
    except Exception:  # noqa: BLE001
        raise web.HTTPBadRequest(text='send {"grade": "right"|"wrong"}')
    if b.get("grade") not in ("right", "wrong", "skip"):
        raise web.HTTPBadRequest(text='send {"grade": "right"|"wrong"|"skip"}')
    if not any(r["id"] == rid for r in _rows()):
        raise web.HTTPNotFound(text="no such task")
    labels = _labels()
    labels[rid] = {"grade": b["grade"], "at": round(time.time(), 1)}
    if isinstance(b.get("note"), str) and b["note"].strip():
        labels[rid]["note"] = b["note"].strip()[:300]
    DIR.mkdir(parents=True, exist_ok=True)
    tmp = LABELS.with_suffix(".tmp")
    tmp.write_text(json.dumps(labels), encoding="utf-8")
    tmp.replace(LABELS)
    return web.json_response({"ok": True, "calibration": calibration()})


@routes.post("/api/yard/evidence/{id}/replay")
async def api_replay(request: web.Request) -> web.Response:
    """Play the saved routine behind a task once more, so you can see whether it still does the job. This DOES act on the PC, so it needs {"confirm": true}."""
    rid = request.match_info["id"]
    try:
        b = await request.json()
    except Exception:  # noqa: BLE001
        b = {}
    if b.get("confirm") is not True:
        raise web.HTTPBadRequest(text="Confirm first: replaying presses things on this PC")
    row = next((r for r in _rows() if r["id"] == rid), None)
    if not row:
        raise web.HTTPNotFound(text="no such task")
    if not row.get("routine"):
        raise web.HTTPConflict(text="this task was done by the agent, not a saved routine, so there is nothing to replay")
    from ..features import pc_control as PC
    try:
        got = await PC.run_routine(row["routine"], request="teach replay")
    except (KeyError, ValueError) as exc:
        raise web.HTTPConflict(text=str(exc))
    return web.json_response({"ok": bool(got.get("ok")), "say": str(got.get("say") or "")[:200]})


@routes.delete("/api/yard/evidence/{id}")
async def api_delete_one(request: web.Request) -> web.Response:
    """Remove one task for good: its row, its pictures and its label. Used for tests you do not want and that must not come back."""
    rid = request.match_info["id"]
    if not _ID.match(rid):
        raise web.HTTPNotFound()
    rows = _rows()
    mine = next((r for r in rows if r["id"] == rid), None)
    if mine is None:
        raise web.HTTPNotFound(text="no such task")
    for name in mine.get("pics") or []:
        try:
            (SHOTS / f"{rid}-{name}.jpg").unlink()
        except OSError:
            pass
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + chr(10) for r in rows if r["id"] != rid), encoding="utf-8")
    tmp.replace(FILE)
    labels = _labels()
    if labels.pop(rid, None) is not None:
        LABELS.write_text(json.dumps(labels), encoding="utf-8")
    return web.json_response({"ok": True})


@routes.get("/api/yard/confidence/fit")
async def api_confidence_fit(request: web.Request) -> web.Response:
    """A PROPOSAL, never applied: weights for the markers fitted to what you said, and whether they score better than the hand-set formula (cross-fold Brier).
    Needs about 30 graded tasks. Attested routines are left out."""
    from . import calibrate as CAL
    labels = _labels()
    graded = [(r["markers"], 1.0 if labels[r["id"]]["grade"] == "right" else 0.0) for r in _rows()
              if r["id"] in labels and labels[r["id"]].get("grade") in ("right", "wrong") and not r.get("attested")]
    return web.json_response(CAL.fit_marker_weights(graded, list(POS) + list(NEG), lambda m: confidence(m)["p"]))


@routes.get("/api/yard/golden")
async def api_golden(request: web.Request) -> web.Response:
    """The routines you had checked before the fresh start. They are replayed to see they still work and are never training samples."""
    from . import settings as YS
    return web.json_response({"fresh_since": YS.fresh_since(), **({"at": None, "routines": []} | YS.golden())})


@routes.delete("/api/yard/evidence")
async def api_clear(request: web.Request) -> web.Response:
    if request.query.get("confirm") != "1":
        raise web.HTTPBadRequest(text="add ?confirm=1")
    import shutil
    shutil.rmtree(SHOTS, ignore_errors=True)
    for p in (FILE, LABELS):
        try:
            p.unlink()
        except OSError:
            pass
    return web.json_response({"ok": True})
