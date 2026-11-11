"""Talk with the four core agents: Smith, the Orchestrator, Neo and the Doctor.

One window, one thread, one SPEAKER at a time. Smith is the front door and routes as he always did. Every speaker shares the same quick layer first (the dashboard, a window of this PC,
the screen commands: those are answered before any persona is asked), so every agent can do the basic asks. After that each one answers as itself:

    smith         the router: tools, apps, answers. When what you ask needs a mission he starts it and hands the conversation to the Orchestrator
    orchestrator  owns the missions: where each is, what it is asking you, run the plan, stop it, apply or discard. Other asks go to Smith's router under its name
    neo           agents: describes them, drafts a new one on request (a draft only; saving is done on the Agency page)
    doctor        the Hub itself: starts a diagnosis mission for a fault, answers questions about how the Hub works from its own facts

You can also address one by name in a sentence ("Neo, draft an agent that checks invoices"), and the speaker chips in the Talk window do the same. A persona answers through the same
runner and the same per-agent model and settings the Agency page controls. Nothing here changes files: an answer is text, a start is a mission (private copy, you APPLY).
"""
from __future__ import annotations

import re

from ..config import logger

SPEAKERS = ("smith", "orchestrator", "neo", "doctor")
NAME = {"smith": "Smith", "orchestrator": "Orchestrator", "neo": "Neo", "doctor": "Doctor"}
_ADDRESS = re.compile(r"^\s*(?:hey |hi |ok |okay )?(agent smith|smith|orchestrator|neo|doctor)\b[\s,:;.!-]*(.*)$", re.I | re.S)
_TASK = re.compile(r"\b(fix|add|build|make|create|write|change|update|refactor|implement|set up|rename|remove|delete|improve|test|deploy)\b", re.I)
_STATUS = re.compile(r"\b(status|progress|how('?s| is| are)|where (is|are)|what('?s| is) (it|going|happening)|update me|any news)\b", re.I)
_STOP = re.compile(r"^\W*(stop|cancel|abort|kill)\b", re.I)
_RUN = re.compile(r"^\W*(run it|run the plan|go ahead|dispatch|start it|do it|yes|yep|go)\W*$", re.I)
_APPLY = re.compile(r"^\W*apply\b", re.I)
_DISCARD = re.compile(r"^\W*(discard|throw (it )?away|reject)\b", re.I)
_FAULT = re.compile(r"\b(wrong|broken|not working|isn'?t working|doesn'?t work|won'?t|fail(ed|s|ing)?|crash(es|ed|ing)?|error|bug|glitch|slow|stuck|freez|can'?t|cannot|unable)\b", re.I)
_NEW_AGENT = re.compile(r"\b(make|create|draft|build|write|design|add)\b.*\b(agent|persona)\b", re.I)
_ACTIVE = {"running", "queued", "starting", "needs_input", "plan_ready", "awaiting_review"}
_PENDING: dict = {}                       # mission id -> answers collected so far for the orchestrator's questions


def address(text: str) -> "tuple[str | None, str]":
    """A leading name picks the speaker for this sentence: "Neo, draft an agent ..." -> ("neo", "draft an agent ...")."""
    m = _ADDRESS.match(text or "")
    if not m:
        return None, text
    who = "smith" if m.group(1).lower() == "agent smith" else m.group(1).lower()
    return who, m.group(2).strip()


def _reply(speaker: str, say: str, **extra) -> dict:
    return {"say": say, "action": None, "confirm": False, "backend": speaker, "speaker": speaker, **extra}


def _missions() -> list:
    from . import missions as M
    try:
        return sorted(M.S.m.values(), key=lambda m: m.created, reverse=True)
    except Exception:  # noqa: BLE001
        return []


def _focus(mission_id: "str | None"):
    from . import missions as M
    if mission_id and M.S.m.get(str(mission_id)):
        return M.S.m[str(mission_id)]
    return next((m for m in _missions() if m.status in _ACTIVE), None)


def _line(m) -> str:
    step = next((s for s in (m.plan or []) if s.get("status") not in ("done", "complete")), None)
    now = f", now {step.get('agent')}: {str(step.get('brief') or '')[:70]}" if step and m.status == "running" else ""
    return f"{m.id[:6]} {m.status.replace('_', ' ')}: {m.brief[:80]}{now}"


def digest(limit: int = 5) -> str:
    rows = _missions()[:limit]
    return "\n".join(_line(m) for m in rows) or "No missions yet."


async def _post(path: str, body: "dict | None" = None) -> dict:
    import aiohttp
    from .. import config
    origin = f"http://127.0.0.1:{config.PORT}"
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=120)) as s:
        async with s.post(origin + path, json=body or {}, headers={"Origin": origin}) as r:
            try:
                data = await r.json()
            except Exception:  # noqa: BLE001
                data = {}
            return {"ok": r.status == 200, "status": r.status, **(data if isinstance(data, dict) else {})}


async def _persona(agent: str, brief: str) -> str:
    """One answer from a persona (its own model and settings), in the Hub's scratch workspace: nothing is written, nothing waits for review."""
    from . import converse as CONV
    from . import missions as M
    from .converse import _voice
    try:
        text = await M.ask_scratch(agent, brief, timeout=CONV.AGENT_TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        logger.info("talk_agents: %s did not answer: %s", agent, exc)
        return ""
    return _voice(text)


def _history_text(history: "list | None") -> str:
    rows = [f"{'User' if h.get('role') == 'user' else 'You'}: {str(h.get('text') or '')[:200]}" for h in (history or [])[-6:] if isinstance(h, dict)]
    return "\n".join(rows)


# ---- the Orchestrator
async def orchestrator(text: str, history, mission_id, chat_fn) -> dict:
    m = _focus(mission_id)
    t = text.strip()
    if m is not None and m.status == "needs_input" and m.questions and t and not _STOP.match(t):
        got = _PENDING.setdefault(m.id, [])
        got.append({"q": str(m.questions[len(got)].get("q") or ""), "a": t})
        if len(got) < len(m.questions):
            nxt = m.questions[len(got)]
            opts = nxt.get("options")
            return _reply("orchestrator", f"Noted. {nxt.get('q')}" + (f" Options: {', '.join(map(str, opts))}." if opts else ""), mission=m.id)
        _PENDING.pop(m.id, None)
        r = await _post(f"/api/missions/{m.id}/answer", {"answers": got})
        return _reply("orchestrator", "Thank you. I am planning it now." if r["ok"] else "I could not pass your answers on: " + str(r.get("status")), mission=m.id)
    if m is not None and _STOP.match(t):
        r = await _post(f"/api/missions/{m.id}/abort")
        return _reply("orchestrator", "Stopped it." if r["ok"] else "I could not stop it.", mission=m.id)
    if m is not None and m.status == "plan_ready" and _RUN.match(t):
        r = await _post(f"/api/missions/{m.id}/run-plan", {})
        return _reply("orchestrator", "Running the plan. It will wait for your review at the end." if r["ok"] else "I could not start the plan.", mission=m.id)
    if m is not None and m.status == "awaiting_review" and _APPLY.match(t):
        r = await _post(f"/api/missions/{m.id}/apply")
        return _reply("orchestrator", "Applied. Say restart the Hub if it needs one." if r["ok"] else "That did not apply: " + str(r.get("status")), mission=m.id)
    if m is not None and m.status == "awaiting_review" and _DISCARD.match(t):
        r = await _post(f"/api/missions/{m.id}/discard")
        return _reply("orchestrator", "Discarded." if r["ok"] else "I could not discard it.", mission=m.id)
    if _STATUS.search(t) and not _TASK.search(t):
        if m is None:
            return _reply("orchestrator", "Nothing is running. " + (digest(2) if _missions() else "There are no missions yet."))
        extra = f" It asks: {m.questions[0].get('q')}" if m.status == "needs_input" and m.questions else (" The plan is ready; say run it." if m.status == "plan_ready" else (" It is waiting for your review; say apply or discard." if m.status == "awaiting_review" else ""))
        return _reply("orchestrator", _line(m) + "." + extra, mission=m.id)
    if _TASK.search(t) and len(t.split()) >= 4:
        res = await chat_fn(t, history or [], mission_id)               # a new ask: Smith's router finds the project and asks you to confirm; it stays the Orchestrator's conversation
        res["speaker"] = "orchestrator"
        return res
    brief = ("You are the Orchestrator, speaking with the user directly in Talk. Missions now:\n" + digest() + "\n\nRecent conversation:\n" + _history_text(history)
             + "\n\nUser: " + t + "\n\nAnswer as the Orchestrator in at most three plain sentences. Do not write files and do not change anything. If they want work done, say what you would need to know first.")
    say = await _persona("orchestrator", brief)
    return _reply("orchestrator", say or "I could not think that through just now. Ask me for the status, or tell me what to do.", mission=m.id if m else None)


# ---- Neo
async def neo(text: str, history, mission_id, chat_fn) -> dict:
    from .. import agent_knowledge as AK
    try:
        names = ", ".join(sorted(p["name"] for p in AK.list_agents())[:40])
    except Exception:  # noqa: BLE001
        names = ""
    if _NEW_AGENT.search(text):
        brief = ("You are Neo, who drafts agent personas. The user asks, in Talk: " + text.strip() + "\n\nDraft the persona in plain words: its name, what it is for, what it must never do, and the tools it needs. "
                 "At most six short lines. This is a draft only; the user saves it on the Agency page.")
        say = await _persona("neo", brief)
        return _reply("neo", (say or "I could not draft that just now.") + " Open Agency, press the plus button and I will turn it into a saved agent there.", url="/agents")
    brief = ("You are Neo, who knows the Hub's agents. The agents are: " + names + ".\n\nRecent conversation:\n" + _history_text(history) + "\n\nUser: " + text.strip()
             + "\n\nAnswer as Neo in at most three plain sentences. Do not write files and do not change anything.")
    say = await _persona("neo", brief)
    return _reply("neo", say or "I could not answer that just now.")


# ---- the Doctor
async def doctor(text: str, history, mission_id, chat_fn) -> dict:
    from . import support as SUP
    if _FAULT.search(text):
        try:
            m = await SUP.start(text if len(text) > 25 else "")
            return _reply("doctor", "I am looking at the Hub now. I will show you what I find.", ui={"doctor": True, "doctor_id": m["id"]})
        except Exception as exc:  # noqa: BLE001
            return _reply("doctor", f"I could not start the diagnosis: {str(exc)[:120]}")
    brief = (SUP.brief_for(text) + "\n\nThis is a question, not a fault: answer it in at most four plain sentences from the facts above. Do not write files and do not change anything.")
    say = await _persona("researcher", brief)
    return _reply("doctor", say or "I could not answer that just now. If something is broken, tell me what you see and I will diagnose it.")


_HANDLERS = {"orchestrator": orchestrator, "neo": neo, "doctor": doctor}


async def speak_as(speaker: str, text: str, history, mission_id, chat_fn) -> dict:
    """`chat_fn(text, history, mission)` is Smith's router, handed in so this module needs nothing of voice.py. Returns the same shape as Smith's reply, plus `speaker`."""
    if speaker == "smith" and not text.strip():
        return _reply("smith", "Here.")
    if speaker not in _HANDLERS:
        res = await chat_fn(text, history or [], mission_id)
        res["speaker"] = "smith"
        return res
    if not text.strip():
        return _reply(speaker, {"orchestrator": "Here. Ask me about the missions, or tell me what to get done.", "neo": "Here. Ask me about the agents, or have me draft one.",
                                "doctor": "Here. Tell me what looks wrong, or ask how something in the Hub works."}[speaker])
    return await _HANDLERS[speaker](text, history, mission_id, chat_fn)
