"""Populate packaging/payloads/ so the installer can set tools up offline.

Run before freezing. Everything already present and matching its recorded hash
is skipped, so a rebuild costs nothing and a rebuild on a metered connection
does not re-download the world.

What it produces:

    packaging/payloads/python/python-3.13.7-amd64.exe   installed only if the
                                                        machine has no Python 3.13
    packaging/payloads/wheels/*.whl                     one shared wheelhouse
                                                        for media, mcp and apps

It also writes the real size and SHA-256 of each download back into
payloads.json, so the manifest describes what was actually fetched rather than
what someone believed at the time. Those values are then what the installer
verifies against at setup time.

    python packaging/fetch_payloads.py              # bundled payloads
    python packaging/fetch_payloads.py --check      # report only, download nothing
    python packaging/fetch_payloads.py --also-on-request
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "payloads.json"
PAYLOADS = HERE / "payloads"


def _human(n: int | None) -> str:
    if not n:
        return "?"
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(entry: dict, target_dir: Path, check_only: bool) -> tuple[bool, str]:
    target = target_dir / entry["filename"]
    if target.is_file():
        actual = _sha256(target)
        if entry.get("sha256") in (None, actual):
            entry["sha256"], entry["size"] = actual, target.stat().st_size
            return True, "have  " + _human(entry["size"])
        return False, "MISMATCH against the recorded hash; delete it to re-fetch"
    if check_only:
        return False, "missing"
    target_dir.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".part")
    try:
        with urllib.request.urlopen(entry["url"], timeout=120) as response, open(temporary, "wb") as out:
            shutil.copyfileobj(response, out)
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        return False, "download failed: " + str(exc)[:80]
    temporary.replace(target)
    entry["sha256"], entry["size"] = _sha256(target), target.stat().st_size
    return True, "fetched " + _human(entry["size"])


def _wheels(capability: str, packages: list[str], check_only: bool) -> tuple[bool, str]:
    """Download into ONE shared wheelhouse, not one folder per capability.

    The capabilities share most of their dependency trees — cryptography,
    pillow, pydantic and friends appear under several — so per-capability
    folders cost real megabytes to store the same files repeatedly. pip resolves
    from the whole directory, and runtime.wheelhouse() falls back to it, so a
    single folder serves every capability.
    """
    folder = PAYLOADS / "wheels"
    before = {w.name for w in folder.glob("*.whl")} if folder.is_dir() else set()
    marker = folder / (".fetched-" + capability)
    if marker.is_file():
        return True, "have"
    if check_only:
        return False, "missing"
    folder.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [sys.executable, "-m", "pip", "download", "--only-binary=:all:",
         "--dest", str(folder), *packages],
        capture_output=True, text=True)
    if result.returncode:
        return False, "pip download failed: " + (result.stderr or result.stdout).strip()[-160:]
    added = [w for w in folder.glob("*.whl") if w.name not in before]
    marker.write_text("\n".join(packages), encoding="utf-8")
    return True, f"+{len(added)} new wheels, {_human(sum(w.stat().st_size for w in added))}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="report what is present; download nothing")
    parser.add_argument("--also-on-request", action="store_true",
                        help="also pre-fetch the large third-party installers")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    ok = True
    print("Bundled payloads (ship inside the installer)")
    good, note = _download(manifest["bundled"]["python"], PAYLOADS / "python", args.check)
    print(f"  {'python':22} {note}")
    ok &= good
    for capability, packages in manifest["bundled"]["wheels"].items():
        if capability.startswith("_"):
            continue
        good, note = _wheels(capability, packages, args.check)
        print(f"  {('wheels/' + capability):22} {note}")
        ok &= good

    if args.also_on_request:
        print("On-request payloads")
        for key, entry in manifest["on_request"].items():
            if key.startswith("_") or not isinstance(entry, dict) or "url" not in entry:
                continue
            good, note = _download(entry, PAYLOADS / "installers", args.check)
            print(f"  {key:22} {note}")
            ok &= good

    if not args.check:
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    total = sum(f.stat().st_size for f in PAYLOADS.rglob("*") if f.is_file()) if PAYLOADS.is_dir() else 0
    print(f"\npayloads/ total: {_human(total)}")
    if not ok:
        print("Some payloads are missing. Run without --check to fetch them.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
