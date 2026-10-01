"""A move is planned while someone is watching, and carried out when nobody is.

Everything that could go wrong has to be caught at plan time: at shutdown there
is no one to tell, and the Hub is halfway through closing. These pin the refusals
and the one rule the whole design rests on - the old install stays intact until a
copy has been verified.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hub import install_move as IM          # noqa: E402


@pytest.fixture()
def packaged(tmp_path, monkeypatch):
    """Pretend to be an installed build, with a small install folder."""
    here = tmp_path / "install"
    (here / "hub").mkdir(parents=True)
    (here / "AgentHub.exe").write_bytes(b"x" * 1024)
    monkeypatch.setattr(IM, "PACKAGED", True)
    monkeypatch.setattr(IM, "install_dir", lambda: here)
    monkeypatch.setattr(IM, "FILE", tmp_path / "pending_move.json")
    return here


# -- refusals, all at plan time -----------------------------------------------
def test_from_source_there_is_nothing_to_move(tmp_path, monkeypatch):
    monkeypatch.setattr(IM, "PACKAGED", False)
    assert "from source" in IM.why_not(tmp_path / "anywhere")


def test_an_empty_choice_is_refused(packaged):
    assert IM.why_not("") == "choose a folder"


def test_a_relative_path_is_refused(packaged):
    assert "full path" in IM.why_not("somewhere/else")


def test_a_network_location_is_refused(packaged):
    assert "network" in IM.why_not(r"\\server\share\hub")


def test_the_current_folder_is_refused(packaged):
    assert "already" in IM.why_not(packaged)


def test_a_folder_inside_the_install_is_refused(packaged):
    assert "inside" in IM.why_not(packaged / "hub" / "nested")


def test_a_file_is_refused(packaged, tmp_path):
    f = tmp_path / "a-file"
    f.write_text("x", encoding="utf-8")
    assert IM.why_not(f) == "that is a file"


def test_a_non_empty_folder_is_refused(packaged, tmp_path):
    d = tmp_path / "busy"
    d.mkdir()
    (d / "something").write_text("x", encoding="utf-8")
    assert "not empty" in IM.why_not(d)


def test_a_missing_parent_is_refused(packaged, tmp_path):
    assert "does not exist" in IM.why_not(tmp_path / "no" / "such" / "parent")


def test_too_little_room_is_refused(packaged, tmp_path, monkeypatch):
    monkeypatch.setattr(IM, "_free_bytes", lambda _p: 10)
    assert "not enough room" in IM.why_not(tmp_path / "new-home")


def test_an_empty_folder_is_accepted(packaged, tmp_path):
    d = tmp_path / "new-home"
    d.mkdir()
    assert IM.why_not(d) == ""


def test_a_folder_that_does_not_exist_yet_is_accepted(packaged, tmp_path):
    assert IM.why_not(tmp_path / "new-home") == ""


# -- planning writes an intention, and nothing else ---------------------------
def test_plan_records_but_does_not_move(packaged, tmp_path):
    dest = tmp_path / "new-home"
    row = IM.plan(str(dest))
    assert row["state"] == "queued"
    assert row["from"] == str(packaged) and row["to"] == str(dest)
    assert (packaged / "AgentHub.exe").is_file(), "nothing may be copied at plan time"
    assert not dest.exists(), "the destination is not created either"


def test_planning_something_impossible_raises_and_stores_nothing(packaged):
    with pytest.raises(ValueError):
        IM.plan("")
    assert IM.pending() == {}


def test_cancel_clears_it(packaged, tmp_path):
    IM.plan(str(tmp_path / "new-home"))
    assert IM.cancel() is True
    assert IM.pending() == {}
    assert IM.cancel() is False


def test_the_record_lives_outside_the_folder_being_moved(packaged):
    """It has to survive the move it describes."""
    assert packaged not in Path(IM.FILE).parents


# -- what the next start concludes --------------------------------------------
def test_outcome_is_empty_when_nothing_was_asked(packaged):
    assert IM.outcome() == {}


def test_a_queued_move_reads_as_queued(packaged, tmp_path):
    IM.plan(str(tmp_path / "new-home"))
    assert IM.outcome()["result"] == "queued"


def test_running_from_the_new_folder_means_it_worked(packaged, tmp_path, monkeypatch):
    dest = tmp_path / "new-home"
    IM.plan(str(dest))
    row = IM.pending(); row["state"] = "running"; IM.write_json(IM.FILE, row)
    monkeypatch.setattr(IM, "install_dir", lambda: dest)   # we are now over there
    assert IM.outcome()["result"] == "done"


def test_still_in_the_old_folder_means_it_did_not(packaged, tmp_path):
    IM.plan(str(tmp_path / "new-home"))
    row = IM.pending(); row["state"] = "running"; IM.write_json(IM.FILE, row)
    got = IM.outcome()
    assert got["result"] == "failed"
    assert "unchanged" in got["why"]


def test_a_failure_note_is_reported_back(packaged, tmp_path):
    note = tmp_path / "note.txt"
    note.write_text("copy failed - nothing was changed", encoding="utf-8")
    IM.plan(str(tmp_path / "new-home"))
    row = IM.pending(); row["state"], row["note"] = "running", str(note)
    IM.write_json(IM.FILE, row)
    assert "copy failed" in IM.outcome()["why"]


# -- the mover itself ----------------------------------------------------------
def test_the_mover_is_written_outside_the_install(packaged, tmp_path):
    script = IM.write_mover(tmp_path / "temp")
    assert script.is_file()
    assert packaged not in script.parents, "it must survive the folder it deletes"


def test_the_mover_waits_verifies_then_deletes_in_that_order(packaged, tmp_path):
    """The order is the safety property, so it is asserted, not assumed."""
    text = IM.write_mover(tmp_path / "temp").read_text(encoding="utf-8")
    wait = text.index("tasklist")
    copy = text.index("robocopy")
    verify = text.index("AgentHub.exe")
    delete = text.index("rmdir")
    assert wait < copy < verify < delete


def test_the_mover_stops_on_a_bad_copy_without_deleting(packaged, tmp_path):
    text = IM.write_mover(tmp_path / "temp").read_text(encoding="utf-8")
    fail = text.index("copy failed")
    delete = text.index("rmdir")
    assert fail < delete
    assert "exit /b 1" in text[fail:delete], "a failed copy must leave before the delete"


def test_launch_does_nothing_without_a_queued_move(packaged, tmp_path):
    assert IM.launch(tmp_path / "temp") is False


# -- the same guarantees on macOS and Linux ------------------------------------
# No registry there, but the launcher entry (.desktop, login item) points at the
# old path exactly as a Windows shortcut does, so the ordering matters the same.
def test_the_posix_mover_waits_verifies_then_deletes(packaged, tmp_path):
    text = IM.write_mover(tmp_path / "temp", windows=False).read_text(encoding="utf-8")
    wait = text.index("kill -0")
    copy = text.index("cp -a")
    verify = text.index("missing the launcher")
    delete = text.index("rm -rf")
    assert wait < copy < verify < delete


def test_the_posix_mover_stops_on_a_bad_copy_without_deleting(packaged, tmp_path):
    text = IM.write_mover(tmp_path / "temp", windows=False).read_text(encoding="utf-8")
    fail = text.index("copy failed")
    delete = text.index("rm -rf")
    assert fail < delete and "exit 1" in text[fail:delete]


def test_posix_gets_a_shell_script_and_windows_a_cmd(packaged, tmp_path):
    assert IM.write_mover(tmp_path / "p", windows=False).suffix == ".sh"
    assert IM.write_mover(tmp_path / "w", windows=True).suffix == ".cmd"


def test_a_posix_network_path_is_refused(packaged):
    assert "network" in IM.why_not("//server/share/hub")
