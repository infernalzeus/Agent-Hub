"""The release must never lose a new feature's files without saying so. Staging copies hub/ by rule, so new code, pages and skills ship by existing; what it cannot decide for itself
(a new kind of file, a new folder next to hub/, code under a name treated as private) stops the build with the file's name."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import stage_release as S  # noqa: E402


def _tree(tmp_path, files):
    for rel in files:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
    return tmp_path


def test_the_real_tree_has_nothing_undecided():
    assert S.unshipped_surprises(Path(__file__).resolve().parents[1]) == []


def test_a_new_file_kind_a_new_folder_and_code_in_a_private_name_are_each_reported(tmp_path):
    root = _tree(tmp_path, ["hub/ok.py", "hub/page.html", "hub/new_sound.flac", "hub/features/data/helper.py", "assets/logo.png", "hub/models/hands/blob.task"])
    found = " | ".join(S.unshipped_surprises(root))
    assert "new_sound.flac" in found and "'assets'" in found and "hub/features/data/helper.py" in found
    assert "ok.py" not in found and "page.html" not in found and "blob.task" not in found          # shipped kinds and decided kinds are quiet


def test_staging_refuses_to_continue_when_something_would_be_lost_silently(tmp_path):
    import pytest
    root = _tree(tmp_path / "src", ["hub/new_sound.flac"])
    with pytest.raises(ValueError, match="silently leave these out"):
        S.stage(root, tmp_path / "out")


def test_what_the_repository_ignores_is_never_staged(tmp_path):
    """The Hub writes its own state beside its code (dashboard layout, agent settings). Those files are git-ignored, so the release leaves them out without anyone naming them."""
    import shutil
    import subprocess

    import pytest
    if not shutil.which("git"):
        pytest.skip("git is not available")
    root = _tree(tmp_path / "src", ["hub/ok.py", "hub/apps.default.json", "hub/my_layout.json", "app.py", "favicon.png", "favicon-64.png", "favicon-256.png", "favicon.ico", "requirements-youtube.txt",
                                    "youtube/ytdl.py", "youtube/yt_upload.py", "packaging/agenthub_launcher.py", "packaging/speech_worker.py", "packaging/vision_worker.py"])
    (root / "hub" / "apps.default.json").write_text('[{"id": "file-browser"}]', encoding="utf-8")
    (root / "hub" / "config.py").write_text("x", encoding="utf-8")
    (root / "hub" / "locations.py").write_text("x", encoding="utf-8")
    (root / ".gitignore").write_text("hub/my_layout.json\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    assert "hub/my_layout.json" in S.git_ignored(root)
    out = tmp_path / "out"
    S.stage(root, out, root / "packaging")
    staged = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}
    assert "hub/ok.py" in staged and "hub/my_layout.json" not in staged
