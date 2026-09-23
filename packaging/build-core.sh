#!/usr/bin/env bash
# macOS / Linux counterpart of build-core.ps1.
#
# Same three stages: stage an allowlisted tree, run the behaviour tests against
# it under a disposable profile, then freeze it. PyInstaller cannot
# cross-compile, so this runs on the target OS — in practice a GitHub Actions
# runner (see .github/workflows/release.yml).
#
#   packaging/build-core.sh --candidate      real build, for testing
#   packaging/build-core.sh --test-only      throwaway
#   packaging/build-core.sh --release-evidence path/to/evidence.json
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
TEST_ONLY=0
CANDIDATE=0
EVIDENCE=""
VERSION=""

while [ $# -gt 0 ]; do
  case "$1" in
    --test-only) TEST_ONLY=1 ;;
    --candidate) CANDIDATE=1 ;;
    --release-evidence) EVIDENCE="$2"; shift ;;
    --version) VERSION="$2"; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

PYTHON="${PYTHON:-python3}"
[ -n "$VERSION" ] || VERSION="$("$PYTHON" -c "import json,sys;print(json.load(open(sys.argv[1]))['version'])" "$HERE/release-manifest.json")"

if [ "$TEST_ONLY" -eq 0 ] && [ "$CANDIDATE" -eq 0 ]; then
  # Same gate as the Windows script: no public build without recorded evidence.
  [ -n "$EVIDENCE" ] || { echo "Public release is gated. Use --test-only, or supply --release-evidence." >&2; exit 1; }
  "$PYTHON" - "$EVIDENCE" "$VERSION" <<'PY'
import json, sys
evidence = json.load(open(sys.argv[1]))
required = ("clean_windows_profile", "all_now_passed", "deferred_passed", "no_private_data", "notes")
if evidence.get("version") != sys.argv[2] or not all(evidence.get(k) for k in required):
    raise SystemExit("Release evidence must identify this version and record every check.")
PY
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
WORK="$ROOT/.release-work/$STAMP"
STAGE="$WORK/source"
VENV="$ROOT/.release-venv-posix"
case "$(uname -s)" in
  Darwin) PLATFORM="macOS-$(uname -m)" ;;
  *)      PLATFORM="linux-$(uname -m)" ;;
esac
MODE=release
[ "$TEST_ONLY" -eq 1 ] && MODE=test
[ "$CANDIDATE" -eq 1 ] && MODE=candidate
OUT="$ROOT/release/$MODE-$VERSION-$STAMP"

mkdir -p "$WORK"
[ -x "$VENV/bin/python" ] || "$PYTHON" -m venv "$VENV"
CORE="$VENV/bin/python"
"$CORE" -m pip install --disable-pip-version-check -r "$HERE/requirements-core.txt" 'pyinstaller>=6,<7'

"$CORE" "$HERE/fetch_payloads.py"
"$CORE" "$HERE/stage_release.py" --root "$ROOT" --destination "$STAGE"

# Verification runs against a disposable profile, never the developer's own.
SMOKE="$WORK/smoke"
mkdir -p "$SMOKE"
env AGENTHUB_STATE_DIR="$SMOKE/state" AGENTHUB_WORK_ROOT="$SMOKE/data" \
    HOME="$SMOKE" PYTHONPATH="$STAGE" PYTHONDONTWRITEBYTECODE=1 \
    "$CORE" "$HERE/smoke_check.py"
env AGENTHUB_STATE_DIR="$SMOKE/state" AGENTHUB_WORK_ROOT="$SMOKE/data" \
    HOME="$SMOKE" PYTHONDONTWRITEBYTECODE=1 \
    "$CORE" "$HERE/test_release.py" --source "$STAGE"

"$CORE" -m PyInstaller --noconfirm --clean --onedir --windowed --name AgentHub --optimize 2 \
  --paths "$STAGE" --distpath "$OUT" --workpath "$WORK/build" --specpath "$WORK" \
  --exclude-module hub.local_settings --exclude-module PyQt5 --exclude-module PySide6 --exclude-module tkinter \
  --add-data "$STAGE/favicon.png:." --add-data "$STAGE/favicon-64.png:." --add-data "$STAGE/favicon-256.png:." \
  --add-data "$STAGE/hub/apps.default.json:hub" --add-data "$STAGE/hub/static:hub/static" \
  --add-data "$STAGE/hub/agent_knowledge:hub/agent_knowledge" --add-data "$STAGE/file-browser:file-browser" \
  --add-data "$STAGE/youtube:youtube" --add-data "$STAGE/packaging/speech_worker.py:packaging" \
  --add-data "$STAGE/requirements-youtube.txt:." \
  --add-data "$STAGE/payloads:payloads" "$STAGE/packaging/agenthub_launcher.py"

PACKAGE="$OUT/AgentHub"
cp "$HERE/release-manifest.json" "$PACKAGE/"
if [ "$TEST_ONLY" -eq 1 ]; then
  echo 'LOCAL TEST BUILD ONLY. Not clean-machine verified. Not for publication.' > "$PACKAGE/TEST-ONLY.txt"
elif [ "$CANDIDATE" -eq 1 ]; then
  # Real build, for installing and testing. Mirrors build-core.ps1's candidate mode.
  echo "RELEASE CANDIDATE $VERSION. Clean-machine validation not yet recorded." > "$PACKAGE/RELEASE-CANDIDATE.txt"
else
  cp "$EVIDENCE" "$OUT/release-evidence.json"
fi

cd "$OUT"
if [ "$(uname -s)" = "Darwin" ]; then
  # Unsigned: notarization needs a paid Apple Developer account, so first launch
  # needs right-click -> Open. Said plainly on the download page.
  hdiutil create -volname "Agent Hub" -srcfolder AgentHub -ov -format UDZO \
    "Agent-Hub-macOS.dmg"
else
  tar -czf "Agent-Hub-Linux.tar.gz" AgentHub
fi

echo "Package: $PACKAGE"
echo "No upload, publication, commit, or changes to the working Hub were performed."
