"""Talk with the four core agents: Smith, Viktor (the Orchestrator), Neo and the Doctor.

One window, one thread, one SPEAKER at a time. Smith is the front door and routes as he always did. Every speaker shares the same quick layer first (the dashboard, a window of this PC,
the screen commands: those are answered before any persona is asked), so every agent can do the basic asks. After that each one answers as itself:

    smith         the router: tools, apps, answers. When what you ask needs a mission he starts it and hands the conversation to the Orchestrator
    orchestrator  Viktor: owns the missions: where each is, what it is asking you, run the plan, stop it, apply or discard. Other asks go to Smith's router under its name
    neo           agents: describes them, drafts a new one on request (a draft only; saving is done on the Agency page)
    doctor        the Hub itself: starts a diagnosis mission for a fault, answers questions about how the Hub works from its own facts

You can also address one by name in a sentence ("Neo, draft an agent that checks invoices"), ask for one ("Smith, pull up Viktor": the conversation moves to Viktor and the one leaving says so), and
the speaker chips in the Talk window do the same. Viktor's id stays "orchestrator" everywhere in the code (missions, files, settings); Viktor is his name and Orchestrator his designation. A persona answers through the same
runner and the same per-agent model and settings the Agency page controls. Nothing here changes files: an answer is text, a start is a mission (private copy, you APPLY).
"""
from __future__ import annotations

import re

from ..config import logger

SPEAKERS = ("smith", "orchestrator", "neo", "doctor")
from ..agent_knowledge import AGENT_NAMES as _AN

NAME = {k: v[0] for k, v in _AN.items()}                 # one source of names: agent_knowledge.AGENT_NAMES
DESIGNATION = {k: v[1] for k, v in _AN.items()}
_ALIAS = {"agent smith": "smith", "smith": "smith", "viktor": "orchestrator", "victor": "orchestrator", "viktor the orchestrator": "orchestrator", "victor the orchestrator": "orchestrator", "the orchestrator": "orchestrator",
          "orchestrator": "orchestrator", "neo": "neo", "the doctor": "doctor", "doctor": "doctor"}                 # a speech recogniser may write Viktor with a k, or give the Orchestrator by its designation
_NAMES = r"(?:agent smith|smith|agent viktor|agent victor|viktor the orchestrator|victor the orchestrator|viktor|victor|the orchestrator|orchestrator|neo|the doctor|doctor)"
_ADDRESS = re.compile(r"^\s*(?:hey |hi |ok |okay )?(" + _NAMES + r")\b[\s,:;.!-]*(.*)$", re.I | re.S)
# asking for an agent: "Smith, pull up Viktor", "can I talk to Neo", "get the Doctor", "put Viktor on", "switch to the orchestrator". What follows the name ("get Neo to draft an agent ...") goes to that agent.
_SUMMON = re.compile(r"^\s*(?:(?:hey |hi |ok |okay )?(?:agent )?(?:smith|viktor|victor|neo|doctor|orchestrator)[\s,:;.!-]+)?(?:(?:please|can you|could you|would you|will you|can i|could i|may i|i'd like to|i would like to|i want to|i need to|let me|let's|lets|i wanna)\s+)*"
                     r"(?:pull up|bring up|bring in|bring over|call up|call in|call on|call|get me|get|put|fetch|put me through to|put me on to|put on|patch me in to|patch me to|connect me to|connect me with|hand me over to|hand me to|hand over to|pass me to|switch to|go to|change to|"
                     r"talk to|talk with|speak to|speak with|chat to|chat with|ask)\s+(" + _NAMES + r")\b\s*(?:on|up|in|over|please)?\W*(?:(?:to|and|about|:|,)\s+(.*))?$", re.I | re.S)
_TASK = re.compile(r"\b(fix|add|build|make|create|write|change|update|refactor|implement|set up|rename|remove|delete|improve|test|deploy)\b", re.I)
_STATUS = re.compile(r"\b(status|progress|how('?s| is| are)|where (is|are)|what('?s| is) (it|going|happening)|update me|any news)\b", re.I)
_STOP = re.compile(r"^\W*(stop|cancel|abort|kill)\b", re.I)
_RUN = re.compile(r"^\W*(run it|run the plan|go ahead|dispatch|start it|do it|yes|yep|go)\W*$", re.I)
_APPLY = re.compile(r"^\W*apply\b", re.I)
_DISCARD = re.compile(r"^\W*(discard|throw (it )?away|reject)\b", re.I)
_FAULT = re.compile(r"\b(wrong|broken|not working|isn'?t working|doesn'?t work|won'?t|fail(ed|s|ing)?|crash(es|ed|ing)?|error|bug|glitch|slow|stuck|freez|can'?t|cannot|unable)\b", re.I)
_ACTION = re.compile(r"\b(fix|change|add|update|improve|repair|adjust|move|rename|remove|implement|redesign|refactor|tidy|clean up|set up)\b", re.I)
_QUESTION = re.compile(r"^\s*(?:(?:hey |hi |ok |okay )?doctor[\s,:;.!-]+)?(?:how|what|why|where|when|which|who|is|are|does|do|did|tell me|explain|show me)\b", re.I)
_NEW_AGENT = re.compile(r"\b(make|create|draft|build|write|design|add)\b.*\b(agent|persona)\b", re.I)
_ACTIVE = {"running", "queued", "starting", "needs_input", "plan_ready", "awaiting_review"}
_PENDING: dict = {}                       # mission id -> answers collected so far for the orchestrator's questions


def address(text: str) -> "tuple[str | None, str]":
    """A leading name picks the speaker for this sentence: "Neo, draft an agent ..." -> ("neo", "draft an agent ...")."""
    m = _ADDRESS.match(text or "")
    if not m:
        return None, text
    who = _ALIAS.get(re.sub(r"^agent (?=vi[ck]tor)", "", m.group(1).lower()).strip(), "smith")
    return who, m.group(2).strip()


def summon(text: str, current: str = "smith") -> "dict | None":
    """"Smith, pull up Viktor": who is wanted, and what is left of the sentence for them. None when the sentence is not a request for an agent (a question about one, a task, a bare name)."""
    m = _SUMMON.match(text or "")
    if not m:
        return None
    who = _ALIAS.get(re.sub(r"^agent (?=vi[ck]tor)", "", m.group(1).lower()).strip())
    if not who:
        return None
    return {"to": who, "from": current, "rest": (m.group(2) or "").strip(), "same": who == current}


def handoff_line(frm: str, to: str) -> str:
    """What the one who is leaving says, each in their own way, short enough to be said aloud."""
    n = NAME[to]
    return {"smith": f"Of course. I will bring in {n}.", "orchestrator": f"Right. {n} is yours; I will step aside.", "neo": f"Understood. Handing you to {n}.",
            "doctor": f"Certainly. {n} will take it from here."}[frm]


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


async def _persona(agent: str, brief: str, role: "str | None" = None) -> str:
    """One answer from a persona (its own model and settings), in the Hub's scratch workspace: nothing is written, nothing waits for review."""
    from . import converse as CONV
    from . import missions as M
    from .converse import _voice
    try:
        from ..yard import presets as _PRE
        with _PRE.speaking_as("researcher", "doctor") if role == "doctor" else _PRE.speaking_as(agent, agent):      # the Doctor answers as the researcher persona, with HIS preset
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
    brief = ("You are Viktor, the Orchestrator, speaking with the user directly in Talk. Missions now:\n" + digest() + "\n\nRecent conversation:\n" + _history_text(history)
             + "\n\nUser: " + t + "\n\nAnswer as Viktor in at most three plain sentences. Do not write files and do not change anything. If they want work done, say what you would need to know first.")
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
    asks_for_work = bool(_FAULT.search(text) or (not _QUESTION.match(text) and (_ACTION.search(text) or len(text.split()) >= 6)))      # a fault, "fix / change / add ...", or a longer statement that is not a question: work for Claude Code, not a chat answer
    if asks_for_work:
        try:
            m = await SUP.start(text if len(text) > 25 else "")
            return _reply("doctor", "I have started the repair in Claude Code, on a private copy of the Hub. Nothing changes in the live Hub until you say apply.", ui={"doctor": True, "doctor_id": m["id"]})
        except SUP.SignedOut as exc:
            return _reply("doctor", f"I cannot repair that yet: {exc} I will not hand a repair to a small local model unasked. To use the local team anyway, open Support and choose LOCAL FIRST (OPENCODE).")
        except Exception as exc:  # noqa: BLE001
            return _reply("doctor", f"I could not start the repair: {str(exc)[:120]}")
    signed = "yes" if SUP.claude_health().get("ok") else "no"
    brief = (SUP.brief_for(text) + "\n\nHOW YOU WORK: in this chat you answer questions with this PC's own model. A fault, or a change the user asks for, is not done by you here: the Hub hands it to Claude Code on a private copy of the Hub (Claude Code signed in: "
             + signed + "), and nothing changes until the user applies it. Never say you have no Claude access or that you cannot make changes: say that a repair is started when they report a fault or ask for a change.\n\n"
             "This is a question, not a fault: answer it in at most four plain sentences from the facts above. Do not write files and do not change anything.")
    say = await _persona("researcher", brief, role="doctor")
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
        return _reply(speaker, {"orchestrator": "Viktor here. Ask me about the missions, or tell me what to get done.", "neo": "Neo here. Ask me about the agents, or have me draft one.",
                                "doctor": "The Doctor here. Tell me what looks wrong, or ask how something in the Hub works."}[speaker])
    return await _HANDLERS[speaker](text, history, mission_id, chat_fn)
