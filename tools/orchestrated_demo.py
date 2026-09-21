"""Drive real orchestrated missions through the running hub (:8081) so they show up in the Missions panel.

    python tools/orchestrated_demo.py                # all demos
    python tools/orchestrated_demo.py --only calc posts
    python tools/orchestrated_demo.py --skip-local

Each demo = a fresh project folder under `_unsorted projects/` (so it gets its own group in the panel) and one
ORCHESTRATED mission: orchestrator (asks / plans) -> [auto-answer with the recommended defaults] -> DISPATCH PIPELINE ->
steps -> hub checks -> review. Results (statuses, plan, verdicts, checks, files, timings) go to
tools/orchestrated_demo_results.json. Cloud demos run in parallel (different models); local (Ollama) demos run one after
another. One demo stops at `plan_ready` on purpose so you can edit / dispatch it yourself.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

HUB = "http://127.0.0.1:8081"
ROOT = Path(r"N:/Code/git repositories/_unsorted projects")
OUT = Path(__file__).with_name("orchestrated_demo_results.json")

BRAND = """# Quill brand

## Voice
Warm, plain, a little playful. Talks to students like a helpful friend. Short sentences.

## Audience
University students, 18-24.

## Avoid
- game-changing
- revolutionary
- synergy
- unlock your potential
"""

DEMOS = {
    "calc": dict(
        project="demo-calculator", profile="code", model="opencode/nemotron-3.5-lightning-free", local=False,
        brief="Build a calculator.", dispatch=True, suggested=False),
    "posts": dict(
        project="demo-launch-posts", profile="content", model="opencode/mimo-v2.5-free", local=False,
        files={"brand.md": BRAND},
        brief=("Write launch posts for Quill, a note-taking app for students: one X post, one LinkedIn post and one Instagram "
               "caption, plus one square Instagram card (HTML rendered to a PNG). Follow the brand file."),
        dispatch=True, suggested=False),
    "sop": dict(
        project="demo-support-sop", profile="business", model="opencode/big-pickle", local=False,
        brief=("Write an onboarding SOP for a new customer-support agent at a small SaaS company, five FAQ macros for "
               "password-reset problems, and a one-week onboarding checklist."),
        dispatch=True, suggested=True),
    "research": dict(
        project="demo-wiki-research", profile="research", model="opencode/nemotron-3-ultra-free", local=False, reference=True,
        brief=("Using the reference library, write a one-page brief on what Agent Hub's Missions feature does and its three "
               "biggest weaknesses. Cite the wiki pages you used."),
        dispatch=True, suggested=False),
    "manual": dict(
        project="demo-manual-plan", profile="code", model="opencode/nemotron-3.5-lightning-free", local=False,
        brief="Plan a small command-line todo app (add, list, done) with tests.", dispatch=False, suggested=False),
    "fast-calc": dict(
        project="demo-fast-calculator", profile="code", model="ollama/nemotron-3-super:cloud", local=False,
        brief="Build a calculator.", dispatch=True, suggested=False),
    "fast-posts": dict(
        project="demo-fast-launch-posts", profile="content", model="ollama/nemotron-3-super:cloud", local=False,
        files={"brand.md": BRAND},
        brief=("Write launch posts for Quill, a note-taking app for students: one X post, one LinkedIn post and one Instagram "
               "caption, plus one square Instagram card (HTML rendered to a PNG). Follow the brand file."),
        dispatch=True, suggested=False),
    "fast-manual": dict(
        project="demo-fast-manual-plan", profile="code", model="ollama/nemotron-3-super:cloud", local=False,
        brief="Plan a small command-line todo app (add, list, done) with tests.", dispatch=False, suggested=False),
    "b-code": dict(
        project="basic-reverse-string", profile="code", model="ollama/nemotron-3-super:cloud", local=False,
        brief="Write a Python function reverse_string(s) in text_utils.py and a pytest test for it in tests/test_text_utils.py.",
        dispatch=True, suggested=False),
    "b-vague": dict(
        project="basic-calculator", profile="code", model="ollama/nemotron-3-super:cloud", local=False,
        brief="Build a calculator.", dispatch=True, suggested=False),
    "b-post": dict(
        project="basic-x-post", profile="content", model="ollama/nemotron-3-super:cloud", local=False,
        files={"brand.md": BRAND},
        brief="Write one X post announcing Quill, a note-taking app for students. Follow the brand file.",
        dispatch=True, suggested=False),
    "b-sop": dict(
        project="basic-password-sop", profile="business", model="ollama/nemotron-3-super:cloud", local=False,
        brief="Write a short SOP (five steps) for resetting a customer's password.", dispatch=True, suggested=True),
    "b-wiki": dict(
        project="basic-wiki-brief", profile="research", model="ollama/nemotron-3-super:cloud", local=False, reference=True,
        brief="In five bullets, explain what Agent Hub is. Cite the wiki pages you used.", dispatch=True, suggested=False),
    "b-plan": dict(
        project="basic-todo-plan", profile="code", model="ollama/nemotron-3-super:cloud", local=False,
        brief="Plan a tiny command-line todo app (add and list only).", dispatch=False, suggested=False),
    "b-local": dict(
        project="basic-local-reverse", profile="code", model="ollama/gemma4:e4b-32k", local=True,
        brief="Write a Python function reverse_string(s) in text_utils.py and a pytest test for it in tests/test_text_utils.py.",
        dispatch=True, suggested=False),
    "local-calc": dict(
        project="demo-local-calculator", profile="code", model="ollama/gemma4:e4b-32k", local=True,
        brief=("Build a command-line calculator: calc.py evaluating expressions like '2+3*4' with + - * / and parentheses "
               "(no eval), and tests/test_calc.py with pytest."),
        dispatch=True, suggested=False),
    "local-posts": dict(
        project="demo-local-posts", profile="content", model="ollama/qwen3.6:32k", local=True,
        files={"brand.md": BRAND.replace("Quill", "Crumb & Co bakery").replace("University students, 18-24.", "Neighbourhood families.")},
        brief="Write three short social posts (X, Instagram, Facebook) announcing a weekend two-for-one sourdough sale. Follow the brand file.",
        dispatch=True, suggested=False),
}


def api(method: str, path: str, body: dict | None = None, timeout: int = 60):
    req = urllib.request.Request(HUB + path, method=method, data=json.dumps(body or {}).encode() if method == "POST" else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode() or "{}")


def make_project(name: str, files: dict | None) -> Path:
    d = ROOT / name
    if d.exists():
        return d
    d.mkdir(parents=True)
    g = lambda *a: subprocess.run(["git", "-C", str(d), "-c", "user.email=demo@local", "-c", "user.name=demo", *a],
                                  check=True, capture_output=True)
    g("init")
    for rel, txt in (files or {}).items():
        (d / rel).write_text(txt, encoding="utf-8")
    g("add", "-A")
    g("commit", "--allow-empty", "-m", "init")
    g("branch", "-M", "main")
    return d


lock = threading.Lock()
CLOUD_SLOTS = threading.Semaphore(2)
results: dict[str, dict] = {}


def save() -> None:
    with lock:
        OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")


def log(key: str, msg: str) -> None:
    with lock:
        print(f"[{time.strftime('%H:%M:%S')}] {key:11s} {msg}", flush=True)


def run_demo(key: str, cfg: dict, cap_s: int) -> None:
    res = results[key] = {"key": key, "project": cfg["project"], "model": cfg["model"], "profile": cfg["profile"],
                          "timeline": [], "started": time.time()}
    t0 = time.time()
    try:
        d = make_project(cfg["project"], cfg.get("files"))
        m = api("POST", "/api/missions", {"brief": cfg["brief"], "kind": "orchestrator", "projects": [str(d)],
                                          "runtime": "opencode", "model": cfg["model"], "profile": cfg["profile"],
                                          "reference": bool(cfg.get("reference"))})
        mid = res["id"] = m["id"]
        log(key, f"dispatched {mid} on {cfg['model']}")
        last, answered, dispatched = None, False, False
        while time.time() - t0 < cap_s:
            time.sleep(15)
            dd = api("GET", f"/api/missions/{mid}")
            st = dd["status"]
            steps = "".join({"done": "●", "running": "◐", "failed": "✖", "queued": "○", "proposed": "·"}.get(s["status"], "?") for s in dd.get("plan", []))
            sig = f"{st} {steps}"
            if sig != last:
                res["timeline"].append({"t": round(time.time() - t0), "status": st, "steps": steps})
                log(key, f"{st:16s} {steps}  {(dd.get('error') or '')[:80]}")
                last = sig
            if st == "needs_input" and not answered:
                res["asked"] = [q["q"] for q in dd["questions"]]
                api("POST", f"/api/missions/{mid}/answer", {"answers": [{"q": q["q"], "a": q.get("default", "")} for q in dd["questions"]]})
                answered = True
                log(key, "answered the questions with the recommended defaults")
            elif st == "plan_ready":
                res["plan"] = [{"id": s["id"], "agent": s["agent"], "after": s["depends_on"], "brief": s["brief"][:140]} for s in dd["plan"]]
                if cfg.get("dispatch") and not dispatched:
                    api("POST", f"/api/missions/{mid}/run-plan", {"use_suggested": bool(cfg.get("suggested"))})
                    dispatched = True
                    log(key, "DISPATCH PIPELINE" + (" (use suggested models)" if cfg.get("suggested") else ""))
                elif not cfg.get("dispatch"):
                    res["outcome"] = "left at plan_ready for you"
                    break
            elif st in ("awaiting_review", "failed", "timed_out", "applied", "discarded"):
                break
            save()
        dd = api("GET", f"/api/missions/{mid}")
        res.update(status=dd["status"], secs=round(time.time() - t0), error=dd.get("error", ""), verify=dd.get("verify"),
                   model_note=dd.get("model_note"), files=[f["path"] for f in dd.get("changed_files", [])],
                   steps=[{"id": s["id"], "agent": s["agent"], "status": s["status"], "model": s.get("model"), "verdict": s.get("verdict"),
                           "rounds": s.get("rounds"), "summary": (s.get("summary") or "")[-260:]} for s in dd.get("plan", [])],
                   runmap=[{"agent": g.get("agent"), "model": g.get("model"), "phase": g.get("phase"), "secs": g.get("secs"),
                            "steps": g.get("steps"), "reason": g.get("reason")} for g in (dd.get("runmap") or {}).get("segments", [])])
        log(key, f"FINAL {dd['status']} in {res['secs']}s, files={res['files']}")
    except Exception as exc:                                    # noqa: BLE001
        res["harness_error"] = str(exc)
        log(key, f"HARNESS ERROR {exc}")
    save()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--skip-local", action="store_true")
    ap.add_argument("--cap", type=int, default=3600, help="seconds per demo")
    a = ap.parse_args()
    keys = [k for k in DEMOS if (not a.only or k in a.only) and not (a.skip_local and DEMOS[k]["local"])]
    cloud = [k for k in keys if not DEMOS[k]["local"]]
    local = [k for k in keys if DEMOS[k]["local"]]
    def gated(k):
        with CLOUD_SLOTS:
            run_demo(k, DEMOS[k], a.cap)
    ts = [threading.Thread(target=gated, args=(k,)) for k in cloud]

    def seq():
        for k in local:
            run_demo(k, DEMOS[k], a.cap)
    if local:
        ts.append(threading.Thread(target=seq))
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    print("ALL DONE", flush=True)


if __name__ == "__main__":
    main()
