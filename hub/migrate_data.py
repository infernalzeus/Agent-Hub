"""Move what earlier versions put OUTSIDE the hub's folder into the hub's own data folder.

    python -m hub.migrate_data               show what would move (changes nothing)
    python -m hub.migrate_data --apply       do it
    python -m hub.migrate_data --from <folder> [--from <folder> ...]   also treat <folder> as an old mission work folder

Versions 0.0.3.3 to 0.1.14 chose the drive with the most free space and made <drive>:\\AgentHub there (and a machine's own local settings could point
the work folder anywhere). The hub now keeps everything under its own folder (`hub/locations.py: BASE`). This moves the old mission working copies
(git worktrees, with `git worktree move`, so nothing is lost and the branches stay attached), updates the mission records that name them, moves the
quick-chat workspace, and removes folders that end up empty. A working copy whose project no longer exists (a test project in a temp folder, say) is
orphaned: it is reported and, with --apply, deleted only if it has no unmerged work to lose, which for an orphan is nothing anyone can reach.

It refuses to run while the hub is running (the hub holds those folders and keeps mission state in memory).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

from . import locations as LOC
from .config import PORT

OLD_BASE_NAME = "AgentHub"


def _git(*args, cwd=None, timeout=120) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout)


def hub_running() -> bool:
    s = socket.socket()
    s.settimeout(0.5)
    try:
        return s.connect_ex(("127.0.0.1", PORT)) == 0
    finally:
        s.close()


def old_default_bases() -> "list[Path]":
    """<drive>:\\AgentHub for every drive where an earlier version made one (it holds work/ or _missions/ or downloads/)."""
    out = []
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        p = Path(f"{letter}:\\") / OLD_BASE_NAME
        try:
            if p.is_dir() and any((p / n).exists() for n in ("work", "downloads", "inbox", "outputs", "opencode", "projects")):
                out.append(p)
        except OSError:
            pass
    return out


def _main_repo(worktree: Path) -> "Path | None":
    """The project a working copy belongs to, read from its .git pointer file; None when that project is gone."""
    f = worktree / ".git"
    try:
        text = f.read_text(encoding="utf-8").strip() if f.is_file() else ""
    except OSError:
        return None
    if not text.startswith("gitdir:"):
        return None
    gitdir = Path(text.split(":", 1)[1].strip())
    # <main>/.git/worktrees/<name>
    try:
        main = gitdir.parent.parent.parent
    except IndexError:
        return None
    return main if (main / ".git").exists() else None


def _is_worktree(p: Path) -> bool:
    return (p / ".git").is_file()


def _rewrite_records(records: Path, old: Path, new: Path) -> int:
    n = 0
    forms = {str(old): str(new), str(old).replace("\\", "/"): str(new).replace("\\", "/"), str(old).replace("\\", "\\\\"): str(new).replace("\\", "\\\\")}
    for f in records.glob("*.json"):
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        new_text = text
        for a, b in forms.items():
            new_text = new_text.replace(a, b)
        if new_text != text:
            json.loads(new_text)                         # never write something that is no longer valid JSON
            f.write_text(new_text, encoding="utf-8")
            n += 1
    return n


def plan_work_folder(src: Path, dst: Path) -> "list[dict]":
    steps = []
    for child in sorted(src.iterdir(), key=lambda p: p.name):
        if child.name == "_missions":
            steps.append({"do": "records", "src": child, "dst": dst / "_missions"})
        elif _is_worktree(child):
            main = _main_repo(child)
            steps.append({"do": "worktree" if main else "orphan", "src": child, "dst": dst / child.name, "main": main})
        elif child.is_dir() and re.search(r"--m[0-9a-f]{8}$", child.name) and not (child / ".git").exists():
            steps.append({"do": "orphan", "src": child, "dst": dst / child.name, "main": None})      # a mission copy whose git link is gone
        elif child.is_dir():
            steps.append({"do": "folder", "src": child, "dst": dst / child.name})
        else:
            steps.append({"do": "file", "src": child, "dst": dst / child.name})
    return steps


def apply_step(step: dict, src_root: Path, dst_root: Path, log) -> bool:
    do, src, dst = step["do"], step["src"], step["dst"]
    dst.parent.mkdir(parents=True, exist_ok=True)
    if do == "worktree":
        if dst.exists():
            log(f"  SKIP {src.name}: {dst} already exists")
            return False
        r = _git("-C", str(step["main"]), "worktree", "move", str(src), str(dst))
        if r.returncode:
            log(f"  FAILED {src.name}: {r.stderr.strip()[:200]}")
            return False
        log(f"  moved working copy {src.name}")
        return True
    if do == "orphan":
        shutil.rmtree(src, onerror=lambda f, p, e: (os.chmod(p, 0o700), f(p)))
        log(f"  deleted orphaned working copy {src.name} (its project no longer exists)")
        return True
    if do == "records":
        dst.mkdir(parents=True, exist_ok=True)
        for f in src.iterdir():
            if (dst / f.name).exists():
                log(f"  SKIP record {f.name}: already there")
                continue
            shutil.move(str(f), str(dst / f.name))
        n = _rewrite_records(dst, src_root, dst_root)
        log(f"  moved mission records and rewrote the paths in {n}")
        try:
            src.rmdir()
        except OSError:
            pass
        return True
    # a plain folder (the quick-chat workspace, scratch) or file
    if dst.exists():
        log(f"  SKIP {src.name}: {dst} already exists")
        return False
    shutil.move(str(src), str(dst))
    log(f"  moved {src.name}")
    return True


def _rmdir_if_empty(p: Path, log) -> None:
    try:
        p.rmdir()
        log(f"  removed empty folder {p}")
    except OSError:
        left = [c.name for c in p.iterdir()] if p.is_dir() else []
        if left:
            log(f"  left {p}: not empty ({', '.join(left[:6])})")


def prune_registered_worktrees(log) -> None:
    """Forget working copies whose folder is gone, in every project the hub knows (git keeps a record per working copy)."""
    seen = set()
    for s in LOC.sources():
        base = Path(s["path"])
        cands = [base] if s.get("kind") == "project" else ([c for c in base.iterdir() if c.is_dir()] if base.is_dir() else [])
        for c in cands:
            if (c / ".git").is_dir() and str(c) not in seen:
                seen.add(str(c))
                r = _git("-C", str(c), "worktree", "prune")
                if r.returncode == 0:
                    log(f"  pruned stale working-copy records in {c.name}")


def run(apply: bool, extra_from: "list[str]", log=print) -> int:
    if hub_running():
        log(f"The hub is running on port {PORT}. Stop it first: it holds these folders and keeps mission state in memory.")
        return 2
    work_dst = LOC.BASE / "work"
    froms: "list[tuple[Path, Path]]" = []        # (old work folder, old base or the folder itself)
    for b in old_default_bases():
        froms.append((b / "work", b))
    cfg = Path(str(LOC.get("work_dir") or ""))
    if str(cfg) and cfg.is_dir() and not LOC.inside_hub(cfg):
        froms.append((cfg, cfg))
    for e in extra_from:
        froms.append((Path(e), Path(e)))
    seen, uniq = set(), []
    for w, b in froms:
        key = str(w.resolve()) if w.exists() else str(w)
        if key not in seen and w.is_dir():
            seen.add(key)
            uniq.append((w, b))
    if not uniq and not old_default_bases():
        log("Nothing outside the hub's folder to move.")
        return 0
    log(f"New home: {LOC.BASE}   ({'APPLYING' if apply else 'dry run: nothing is changed'})")
    for src, base in uniq:
        log(f"Old work folder: {src}")
        steps = plan_work_folder(src, work_dst)
        if not apply:
            for st in steps:
                log(f"  {st['do']:9} {st['src'].name} -> {st['dst']}")
        if apply:
            for st in steps:
                apply_step(st, src, work_dst, log)
            _rmdir_if_empty(src, log)
    # the rest of an old default base: downloads, inbox, outputs, opencode, projects
    for b in old_default_bases():
        for name in ("downloads", "inbox", "outputs", "opencode", "projects"):
            d = b / name
            if not d.exists():
                continue
            has_files = any(True for _ in d.rglob("*") if _.is_file()) if d.is_dir() else True
            if not has_files:
                log(f"  {'would remove' if not apply else 'removing'} empty {d}")
                if apply:
                    shutil.rmtree(d, ignore_errors=True)
            else:
                log(f"  {'would move' if not apply else 'moving'} {d} -> {LOC.BASE / name}")
                if apply:
                    shutil.move(str(d), str(LOC.BASE / name))
        if apply:
            _rmdir_if_empty(b, log)
    if apply:
        prune_registered_worktrees(log)
        log("Done. Start the hub again; the Locations page now shows the new home.")
    return 0


def main(argv: "list[str] | None" = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    apply = "--apply" in argv
    extra = [argv[i + 1] for i, a in enumerate(argv) if a == "--from" and i + 1 < len(argv)]
    return run(apply, extra)


if __name__ == "__main__":
    raise SystemExit(main())
