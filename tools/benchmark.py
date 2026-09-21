"""Free/local model benchmark for Agent Hub missions.

Runs the SAME three tasks through the real hub (same harness, same repo-map,
same hub-run checks) on every free/local model, and scores each result with
objective checks. Feeds hub/agent_knowledge/model_recommendations.json.

    python tools/benchmark.py            # all models
    python tools/benchmark.py --models opencode/big-pickle ollama/qwen3.6:32k
    python tools/benchmark.py --tasks calc bugfix

Tasks
  calc    build a small CLI + tests from an empty repo        (single / coder)
  bugfix  make a seeded failing pytest suite pass             (single / coder)
  plan    turn a goal into a valid multi-agent JSON plan      (orchestrator)

Needs the hub running on :8081. Missions are left on the board (project groups
benchmark-calc / benchmark-bugfix / benchmark-plan) so you can open any of them.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path
from queue import Queue

HUB = "http://127.0.0.1:8081"
REPOS = Path(r"N:/Code/git repositories/_unsorted projects")
OUT = Path(__file__).with_name("benchmark_results.json")

CLOUD = ["opencode/nemotron-3-ultra-free", "opencode/nemotron-3.5-lightning-free", "opencode/big-pickle",
         "opencode/mimo-v2.5-free", "opencode/ling-3.0-flash-fin-free", "opencode/muse-spark-1.3-contributor-free"]
LOCAL = ["ollama/gemma4:e4b-32k", "ollama/qwen3.6:32k"]
ROSTER = {"coder", "reviewer", "researcher", "tester", "doc-writer"}

BRIEFS = {
    "calc": ("Build a basic calculator in Python: a `calculator.py` CLI used like `python calculator.py 6 / 3` "
             "(two numbers and one operator: + - * /). Divide-by-zero and non-numeric input must print a clear "
             "one-line error and exit with a non-zero status (no traceback). Also write `test_calculator.py` "
             "(pytest, at least 5 tests). Keep it simple."),
    "bugfix": ("The tests in test_textstats.py are failing. Find the bug in textstats.py and fix it. "
               "Do NOT modify the tests."),
    "plan": ("Add a `done <n>` command to todo.py that marks item n as complete (with a clear error for a bad n), "
             "add pytest tests for add/list/done, and document usage in a README.md."),
}

SEEDS = {
    "benchmark-calc": {},
    "benchmark-bugfix": {
        "textstats.py": '''import re
from collections import Counter


def words(text):
    return re.findall(r"[a-z']+", text.lower())


def word_count(text):
    return len(words(text))


def top_words(text, n=3):
    """Return the n most common words as [(word, count)], most frequent first;
    ties broken alphabetically."""
    counts = Counter(words(text))
    return sorted(counts.items(), key=lambda kv: (kv[1], kv[0]))[:n]
''',
        "test_textstats.py": '''from textstats import word_count, top_words


def test_word_count():
    assert word_count("The cat and the hat.") == 5


def test_top_words_orders_by_frequency():
    assert top_words("a b b c c c", 2) == [("c", 3), ("b", 2)]


def test_top_words_ties_alphabetical():
    assert top_words("b a c", 3) == [("a", 1), ("b", 1), ("c", 1)]


def test_top_words_default_n():
    assert len(top_words("a b c d e f")) == 3
''',
    },
    "benchmark-plan": {
        "todo.py": '''import json
import sys
from pathlib import Path

DB = Path("todos.json")


def load():
    return json.loads(DB.read_text()) if DB.exists() else []


def save(items):
    DB.write_text(json.dumps(items, indent=2))


def add(text):
    items = load()
    items.append({"text": text, "done": False})
    save(items)


def list_items():
    for i, it in enumerate(load(), 1):
        print(f"{i}. [{'x' if it['done'] else ' '}] {it['text']}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "add":
        add(" ".join(sys.argv[2:]))
    else:
        list_items()
''',
    },
}
TASK_PROJECT = {"calc": "benchmark-calc", "bugfix": "benchmark-bugfix", "plan": "benchmark-plan"}


def api(method: str, path: str, body: dict | None = None, timeout: int = 60):
    req = urllib.request.Request(HUB + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace") or "{}")


def git(cwd: Path, *a: str) -> str:
    r = subprocess.run(["git", "-c", "user.email=benchmark@local", "-c", "user.name=benchmark", *a],
                       cwd=str(cwd), capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()


def seed_projects() -> None:
    for name, files in SEEDS.items():
        d = REPOS / name
        if (d / ".git").exists():
            continue
        d.mkdir(parents=True, exist_ok=True)
        git(d, "init")
        for fn, txt in files.items():
            (d / fn).write_text(txt, encoding="utf-8")
        git(d, "add", "-A")
        git(d, "commit", "--allow-empty", "-m", "seed")


def _run(cmd: list[str], cwd: str, timeout: int = 20) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as exc:
        return 99, str(exc)


def score_calc(d: dict) -> tuple[int, list[str]]:
    wt, notes, pts = d["worktree"], [], 0
    have = (Path(wt) / "calculator.py").exists() and (Path(wt) / "test_calculator.py").exists()
    if have and (d.get("verify") or {}).get("ok"):
        pts += 1
    else:
        notes.append("files/tests missing or hub checks failed")
    rc, out = _run([sys.executable, "calculator.py", "6", "*", "7"], wt)
    if rc == 0 and re.search(r"\b42(\.0)?\b", out):
        pts += 1
    else:
        notes.append(f"6*7 -> rc={rc} {out[:60]!r}")
    bad = [_run([sys.executable, "calculator.py", "6", "/", "0"], wt), _run([sys.executable, "calculator.py", "abc", "+", "1"], wt)]
    if all(rc != 0 and out and "Traceback" not in out for rc, out in bad):
        pts += 1
    else:
        notes.append("error handling: traceback or exit 0")
    return pts, notes


def score_bugfix(d: dict) -> tuple[int, list[str]]:
    wt, notes, pts = d["worktree"], [], 0
    rc, out = _run([sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"], wt, 60)
    if rc == 0:
        pts += 2
    else:
        notes.append("tests still failing: " + out[-120:].replace("\n", " "))
    if "test_textstats.py" not in git(Path(wt), "status", "--porcelain"):
        pts += 1
    else:
        notes.append("modified the tests (cheated)")
    return pts, notes


def score_plan(d: dict) -> tuple[int, list[str]]:
    kids = d.get("plan") or []
    notes, pts = [], 0
    if d.get("status") == "needs_input":
        return 0, ["asked clarifying questions instead of planning"]
    if kids:
        pts += 1
    else:
        notes.append("no plan produced")
    agents = [c.get("agent") for c in kids]
    if len(kids) >= 2 and all(a in ROSTER for a in agents) and all((c.get("brief") or "").strip() for c in kids):
        pts += 1
    elif kids:
        notes.append(f"invalid plan: agents={agents}")
    if len(set(agents)) >= 2 and ({"tester", "doc-writer"} & set(agents)) and "coder" in agents:
        pts += 1
    elif kids:
        notes.append("plan lacks role diversity (needs coder + tester/doc-writer)")
    return pts, notes


SCORERS = {"calc": score_calc, "bugfix": score_bugfix, "plan": score_plan}


def run_job(model: str, task: str, cap_s: int) -> dict:
    t0 = time.time()
    body = {"brief": BRIEFS[task], "projects": [TASK_PROJECT[task]], "runtime": "opencode", "model": model,
            "kind": "orchestrator" if task == "plan" else "single"}
    if task != "plan":
        body["agent"] = "coder"
    res = {"model": model, "task": task, "score": 0, "max": 3, "notes": [], "status": "?", "secs": 0}
    try:
        m = api("POST", "/api/missions", body)
        mid = res["id"] = m["id"]
        while time.time() - t0 < cap_s:
            time.sleep(10)
            d = api("GET", f"/api/missions/{mid}")
            if d["status"] not in ("running", "queued", "blocked"):
                break
        d = api("GET", f"/api/missions/{mid}")
        res["status"] = d["status"]
        res["secs"] = round((d.get("ended") or time.time()) - d["created"])
        segs = (d.get("runmap") or {}).get("segments") or []
        res["steps"] = sum(s.get("steps", 0) for s in segs)
        res["prompt_k"] = round(max([s.get("prompt", 0) for s in segs] or [0]) / 1000, 1)
        res["error"] = (d.get("error") or "")[:160]
        res["final_model"] = d.get("model")
        if d.get("model") and d.get("model") != model:
            res["notes"].append(f"FELL BACK to {d.get('model')} — not a clean result for {model}")
        if d["status"] in ("awaiting_review", "applied", "plan_ready", "needs_input"):
            sc, nt = SCORERS[task](d)
            res["score"], res["notes"] = sc, res["notes"] + nt
        else:
            res["notes"] = [f"mission {d['status']}: {res['error'][:100]}"]
        res["hub_check"] = (d.get("verify") or {}).get("ok")
        if task == "plan":                           # a plan_ready orchestrator row is just clutter after scoring
            try:
                api("POST", f"/api/missions/{mid}/discard")
                api("POST", f"/api/missions/{mid}/forget")
            except Exception:
                pass
    except Exception as exc:
        res["notes"] = [f"harness error: {exc}"]
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*")
    ap.add_argument("--tasks", nargs="*", default=["calc", "bugfix", "plan"])
    ap.add_argument("--local", action="store_true", help="also run the Ollama models (heavy: uses the GPU)")
    a = ap.parse_args()
    seed_projects()
    cloud = [m for m in CLOUD if not a.models or m in a.models]
    local = [m for m in LOCAL if (a.local or (a.models and m in a.models)) and (not a.models or m in a.models)]
    results: list[dict] = []
    lock = threading.Lock()

    def save():
        OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")

    def worker(q: Queue, cap: int):
        while True:
            try:
                model, tasks = q.get_nowait()
            except Exception:
                return
            for task in tasks:
                r = run_job(model, task, cap)
                with lock:
                    results.append(r)
                    save()
                    print(f"[{r['score']}/{r['max']}] {model:42s} {task:7s} {r['status']:16s} {r['secs']:>5}s "
                          f"steps={r.get('steps')} prompt={r.get('prompt_k')}k  {'; '.join(r['notes'])[:110]}", flush=True)

    qc, ql = Queue(), Queue()
    for m in cloud:
        qc.put((m, list(a.tasks)))
    for m in local:
        ql.put((m, list(a.tasks)))
    threads = [threading.Thread(target=worker, args=(qc, 2000)) for _ in range(2)]
    threads.append(threading.Thread(target=worker, args=(ql, 3000)))
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print("\n=== SUMMARY ===")
    by: dict[str, list[dict]] = {}
    for r in results:
        by.setdefault(r["model"], []).append(r)
    for m, rs in sorted(by.items(), key=lambda kv: -sum(x["score"] for x in kv[1])):
        tot = sum(x["score"] for x in rs)
        mx = sum(x["max"] for x in rs)
        avg = sum(x["secs"] for x in rs) // max(1, len(rs))
        per = " ".join(f"{x['task']}={x['score']}" for x in sorted(rs, key=lambda x: x["task"]))
        print(f"{tot:>2}/{mx:<2} {m:42s} avg {avg}s   {per}")


if __name__ == "__main__":
    main()
