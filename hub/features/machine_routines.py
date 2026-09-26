"""Machine routines: replay a sequence recorded from the screen surface.

The MCP routines in `pc_control` resolve a control by name, which is why they
survive a window being moved. **A game has no accessibility tree** — Unity and
DirectX render one canvas and UI Automation sees a single control with nothing
inside it — so nothing can be resolved by name there. These routines work the
only way that is left: each step remembers a small picture of what it clicked,
and finds that picture again before clicking.

That is materially weaker, and the UI says so. New art means re-record.

Three things keep it honest:

* **The click still goes through MCP.** Nothing here synthesises raw input, so
  the same provider and the same tool exclusions apply as everywhere else.
* **A weak match never clicks.** Below the profile's floor the routine stops and
  says which step it lost. A wrong click in a game can start a match or spend
  currency, so guessing is worse than failing.
* **Confidence is recorded per step.** A score drifting down over runs is a
  warning before a break, not a surprise after one.

Imaging (numpy, Pillow) is imported lazily: the hub's core is aiohttp alone, and
must start on a machine that has never recorded anything.
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

from aiohttp import web

from .. import decide as DEC, runtime as RT
from ..config import logger
from . import mcp as MCP
from . import pc_control as PC

routes = web.RouteTableDef()
ANCHORS = RT.STATE / "data" / "anchors"


# ── profiles ─────────────────────────────────────────────────────────────────────────────────────────────────────────
# One floor and one timing rule cannot serve both cases. A gameplay click two
# seconds late has missed its moment; an installer's "Next" appears whenever the
# download decides to finish. So the routine carries the policy, not the engine.
PROFILES = {
    "reflex": {
        "label": "Reflex — gameplay",
        "why": "Transient, animated UI. Punctuality matters as much as accuracy.",
        "floor": 0.90,
        "timing": "recorded",      # replay the delays exactly as they were recorded
        "ceiling_s": 2.0,          # and give up quickly: the moment has passed
        "poll_s": 0.10,
    },
    "patient": {
        "label": "Patient — installs, uploads, downloads",
        "why": "The next control appears when a transfer finishes, not on a clock.",
        "floor": 0.80,
        "timing": "wait",          # ignore recorded delays entirely
        "ceiling_s": 600.0,
        "poll_s": 0.75,
    },
    "balanced": {
        "label": "Balanced — ordinary desktop apps",
        "why": "Waits for what it expects, but not forever.",
        "floor": 0.85,
        "timing": "wait",
        "ceiling_s": 30.0,
        "poll_s": 0.35,
    },
}
DEFAULT_PROFILE = "balanced"


def profile_for(name: str) -> dict:
    return PROFILES.get(name or "", PROFILES[DEFAULT_PROFILE])


# Deterministic fallback so profile choice works with no model available at all.
@DEC.rule("routine_profile")
def _r_profile(state: dict):
    text = " ".join(str(state.get(k, "")) for k in ("description", "title", "intent")).casefold()
    if any(w in text for w in ("game", "gameplay", "match", "level", "boss", "fps", "unity", "combat")):
        return "reflex", 0.75
    if any(w in text for w in ("install", "installer", "download", "upload", "setup", "update", "transfer", "render")):
        return "patient", 0.75
    return None                                   # unsure: let a model try, else default


async def choose_profile(description: str, *, model: str | None = None) -> dict:
    """Pick a profile from what the routine is FOR, rather than hardcoding one.

    A closed question with a calibrated answer is exactly what `decide` is for;
    the rules backend answers instantly and for free when the wording is obvious.
    """
    state = {"description": description}
    question = DEC.q_choice("routine_profile",
                            "What kind of work is this routine for? Choose the timing policy that fits.",
                            list(PROFILES))
    results = DEC._decide_rules(state, [question])
    picked = results[0] if results else {}
    if picked.get("answer") is None and model:
        try:
            picked = (await DEC.decide(state, [question], backend="local", model=model))[0]
        except Exception as exc:                  # a judge that cannot answer is not an error
            logger.info("machine routine: profile model unavailable (%s); using the default", exc)
            picked = {}
    name = picked.get("answer") or DEFAULT_PROFILE
    return {"profile": name, "p": float(picked.get("p") or 0.0),
            "backend": picked.get("backend") or "default", **profile_for(name)}


# ── matching ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _np():
    import numpy                                   # lazy: core install has no numpy
    return numpy


def match_anchor(frame, anchor):
    """Where in `frame` does `anchor` appear, and how sure are we?

    Normalised cross-correlation, so a uniform brightness change (a different
    monitor, a gamma shift) does not move the score. Returns (x, y, score) for
    the anchor's CENTRE, or None when the anchor cannot fit in the frame.

    NCC over every offset is the textbook formulation:
        num = sum((F - mean_F_window) * (A - mean_A))
        den = sqrt(sum((F - mean_F_window)^2) * sum((A - mean_A)^2))
    computed with FFT for the correlation and summed-area tables for the window
    statistics, which keeps a 1920x1080 frame well inside interactive time.
    """
    np = _np()
    frame = np.asarray(frame, dtype=np.float64)
    anchor = np.asarray(anchor, dtype=np.float64)
    fh, fw = frame.shape
    ah, aw = anchor.shape
    if ah > fh or aw > fw or ah == 0 or aw == 0:
        return None

    a_zero = anchor - anchor.mean()
    a_ss = float((a_zero ** 2).sum())
    if a_ss <= 1e-9:                               # a flat anchor matches everything; refuse to pretend
        return None

    # correlation of frame with the zero-mean anchor, via FFT
    shape = (fh + ah - 1, fw + aw - 1)
    fsize = tuple(1 << int(np.ceil(np.log2(s))) for s in shape)
    F = np.fft.rfft2(frame, fsize)
    A = np.fft.rfft2(a_zero[::-1, ::-1], fsize)
    corr = np.fft.irfft2(F * A, fsize)[ah - 1:fh, aw - 1:fw]

    # windowed sum and sum-of-squares via summed-area tables
    ones = np.pad(frame, ((1, 0), (1, 0)))
    s1 = ones.cumsum(0).cumsum(1)
    s2 = np.pad(frame ** 2, ((1, 0), (1, 0))).cumsum(0).cumsum(1)

    def window(table):
        return (table[ah:, aw:] - table[:-ah, aw:] - table[ah:, :-aw] + table[:-ah, :-aw])

    n = ah * aw
    win_sum, win_sq = window(s1), window(s2)
    var = win_sq - (win_sum ** 2) / n
    den = np.sqrt(np.maximum(var, 0.0) * a_ss)
    with np.errstate(divide="ignore", invalid="ignore"):
        score = np.where(den > 1e-9, corr / den, 0.0)

    idx = int(np.argmax(score))
    top, left = divmod(idx, score.shape[1])
    return left + aw // 2, top + ah // 2, float(np.clip(score[top, left], -1.0, 1.0))


def to_gray(image):
    """Pillow image -> 2-D float array. Colour is thrown away on purpose: it
    doubles the work and a UI that only changed hue is still the same button."""
    np = _np()
    return np.asarray(image.convert("L"), dtype=np.float64)


def _grab():
    from PIL import ImageGrab                      # lazy, Windows-local
    return ImageGrab.grab()


# ── the two backends ─────────────────────────────────────────────────────────────────────────────────────────────────
def inproc_ready() -> bool:
    """Can this interpreter do the work itself? True in a checkout, false frozen."""
    try:
        _np()
        from PIL import ImageGrab  # noqa: F401
        return True
    except Exception:
        return False


def worker_ready() -> bool:
    """Is there a managed runtime that can? Checked without starting anything heavy."""
    return RT.modules_ready("vision", ["numpy", "PIL"])


def _worker_find(anchor_path: str, frame_path: str | None = None) -> "tuple[int,int,float] | None":
    """One capture-and-match in the managed runtime. Returns None if it could not."""
    script = RT.ASSETS / "packaging" / "vision_worker.py"
    cmd = [str(RT.python_for("vision")), str(script), str(anchor_path)]
    if frame_path:
        cmd.append(str(frame_path))
    run = RT.run(cmd, 120)
    if run.returncode or not (run.stdout or "").strip():
        logger.warning("vision worker failed: %s", (run.stderr or run.stdout or "")[-300:])
        return None
    try:
        data = json.loads(run.stdout.strip().splitlines()[-1])
    except ValueError:
        return None
    if not data.get("ok"):
        return None
    return int(data["x"]), int(data["y"]), float(data["score"])


def ready() -> bool:
    """Can this hub match at all — in-process, or through the managed runtime?"""
    return inproc_ready() or worker_ready()


# ── storage ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def _anchor_path(routine_id: str, ordinal: int) -> Path:
    return ANCHORS / routine_id / f"{ordinal:03d}.png"


def save_machine_routine(intent: str, title: str, window: str, profile: str,
                         steps: list[dict]) -> dict:
    """Store a recorded surface sequence.

    `steps` carry the anchor as raw PNG bytes; they are written beside the
    database rather than into it, so the store stays small and an anchor can be
    looked at by a human when a match goes wrong.
    """
    now = time.time()
    rid = __import__("hashlib").sha256(("machine:" + intent).encode()).hexdigest()[:16]
    with PC._db() as db:
        row = db.execute("SELECT id FROM pc_routines WHERE intent=?", (intent,)).fetchone()
        if row:
            rid = row["id"]
            db.execute("UPDATE pc_routines SET title=?,tool=?,kind=?,args_json=?,updated=? WHERE id=?",
                       (title, "surface", "machine", json.dumps({"window": window, "profile": profile}), now, rid))
            db.execute("DELETE FROM pc_steps WHERE routine_id=?", (rid,))
        else:
            db.execute(
                "INSERT INTO pc_routines(id,intent,title,tool,args_json,signature_json,status,"
                "successes,failures,created,updated,kind) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (rid, intent, title, "surface", json.dumps({"window": window, "profile": profile}),
                 json.dumps({"kind": "surface", "window": window}), "candidate", 0, 0, now, now, "machine"))
        for i, st in enumerate(steps):
            png = st.get("anchor_png")
            target = {"kind": "surface", "frac": st.get("frac") or [0.5, 0.5],
                      "note": st.get("note", "")}
            if png:
                path = _anchor_path(rid, i)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(png)
                target["anchor"] = str(path)
            db.execute("INSERT INTO pc_steps(routine_id,ordinal,tool,args_json,target_json,created) "
                       "VALUES(?,?,?,?,?,?)",
                       (rid, i, st.get("tool", "Click"),
                        json.dumps({k: v for k, v in (st.get("args") or {}).items()} |
                                   {"delay_ms": int(st.get("delay_ms") or 0)}),
                        json.dumps(target), now))
        return dict(db.execute("SELECT * FROM pc_routines WHERE id=?", (rid,)).fetchone())


def record_step_result(routine_id: str, ordinal: int, score: float, elapsed_ms: int) -> None:
    """Keep the last match score and how long the step took, so a routine that is
    drifting shows it before it breaks."""
    with PC._db() as db:
        row = db.execute("SELECT target_json FROM pc_steps WHERE routine_id=? AND ordinal=?",
                         (routine_id, ordinal)).fetchone()
        if not row:
            return
        target = json.loads(row["target_json"] or "{}")
        target["last_score"] = round(float(score), 4)
        target["last_ms"] = int(elapsed_ms)
        db.execute("UPDATE pc_steps SET target_json=? WHERE routine_id=? AND ordinal=?",
                   (json.dumps(target), routine_id, ordinal))


# ── replay ───────────────────────────────────────────────────────────────────────────────────────────────────────────
async def _find(anchor_gray, floor: float, ceiling_s: float, poll_s: float,
                grab=None, anchor_path: str | None = None) -> tuple[int, int, float, int]:
    """Look for the anchor until it is confidently there, or the ceiling passes.

    Returns (x, y, best_score, elapsed_ms). A caller that gets a score below the
    floor must not click: that is the whole safety rule of this module.
    """
    # In-process when we can; otherwise every poll is one child process, which is
    # why the patient profile polls slowly and reflex is only viable in-process.
    use_worker = grab is None and not inproc_ready()
    grab = grab or _grab
    started = time.monotonic()
    best = (0, 0, -1.0)
    while True:
        if use_worker:
            found = await asyncio.to_thread(_worker_find, anchor_path)
        else:
            found = match_anchor(to_gray(grab()), anchor_gray)
        if found and found[2] > best[2]:
            best = found
        if found and found[2] >= floor:
            break
        if time.monotonic() - started >= ceiling_s:
            break
        await asyncio.sleep(poll_s)
    return best[0], best[1], best[2], int((time.monotonic() - started) * 1000)


async def replay_machine_routine(routine: dict, *, grab=None, request: str = "",
                                 policy_override: dict | None = None) -> dict:
    if not ready():
        return {"ok": False, "route": "fall-through",
                "say": "Machine routines need the imaging tools. Set up Screen recording first."}
    args = json.loads(routine["args_json"] or "{}")
    # A caller may tighten the waits — tests do, and so would a 'check this
    # routine still works' button that must not block for ten minutes.
    policy = {**profile_for(args.get("profile")), **(policy_override or {})}
    steps = PC._steps(routine["id"])
    if not steps:
        return {"ok": False, "route": "fall-through", "say": "That routine has no steps saved."}

    Image = None
    if inproc_ready():
        from PIL import Image                      # lazy; not needed on the worker path
    scores = []
    for step in steps:
        target = json.loads(step["target_json"] or "{}")
        sargs = json.loads(step["args_json"] or "{}")
        anchor_path = target.get("anchor")
        if not anchor_path or not Path(anchor_path).is_file():
            PC._record_run(request, "fall-through", "skipped", f"step {step['ordinal']}: anchor missing")
            PC._remember_outcome(routine["id"], False)
            return {"ok": False, "route": "fall-through",
                    "say": f"Step {step['ordinal'] + 1} has lost its reference image; re-record this routine."}

        # Reflex replays the recorded pacing; the others wait for the screen instead.
        if policy["timing"] == "recorded" and sargs.get("delay_ms"):
            await asyncio.sleep(min(float(sargs["delay_ms"]) / 1000.0, policy["ceiling_s"]))

        anchor = to_gray(Image.open(anchor_path)) if inproc_ready() else None
        x, y, score, took = await _find(anchor, policy["floor"], policy["ceiling_s"],
                                        policy["poll_s"], grab=grab, anchor_path=anchor_path)
        record_step_result(routine["id"], step["ordinal"], score, took)
        scores.append(score)
        if score < policy["floor"]:
            PC._record_run(request, "fall-through", "skipped",
                           f"step {step['ordinal']}: best match {score:.2f} < floor {policy['floor']}")
            PC._remember_outcome(routine["id"], False)
            return {"ok": False, "route": "fall-through", "scores": scores,
                    "say": (f"I could not confidently find step {step['ordinal'] + 1} "
                            f"({score:.0%} sure, needs {policy['floor']:.0%}), so I stopped rather than "
                            "click the wrong thing.")}
        try:
            await MCP.call_tool("windows", step["tool"], {**{k: v for k, v in sargs.items()
                                                             if k != "delay_ms"}, "loc": [x, y]})
        except Exception as exc:
            PC._record_run(request, "routine", "failed", f"step {step['ordinal']}: {exc}")
            PC._remember_outcome(routine["id"], False)
            return {"ok": False, "route": "routine", "say": f"{routine['title']} failed: {str(exc)[:150]}"}

    updated = PC._remember_outcome(routine["id"], True)
    PC._record_run(request, "routine", "done", f"{len(steps)} step(s), lowest match {min(scores):.2f}")
    return {"ok": True, "route": "routine", "scores": scores,
            "say": f"Ran {routine['title']} — {len(steps)} steps, lowest match {min(scores):.0%}.",
            "routine": {"id": routine["id"], "status": updated["status"],
                        "successes": updated["successes"], "tag": "ROUTINE"}}


# ── api ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
@routes.get("/api/pc/machine/profiles")
async def api_profiles(request: web.Request) -> web.Response:
    suggested = None
    description = request.query.get("for")
    if description:
        suggested = await choose_profile(description)
    return web.json_response({"profiles": PROFILES, "default": DEFAULT_PROFILE,
                              "ready": ready(), "suggested": suggested})
