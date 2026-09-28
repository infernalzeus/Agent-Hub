"""A command that works in a shell must be one the hub can actually spawn.

Found by ingesting a Node app and pressing APPLY:

    install error: [WinError 2] The system cannot find the file specified

`npm` on Windows is `npm.CMD`. A shell finds it through PATHEXT; CreateProcess
does not, so `create_subprocess_exec("npm", ...)` fails on a machine where npm
works everywhere else. It affected the install step and the launch step, so
every Node, yarn and pnpm app was ingestable but not startable.
"""
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from hub import runtime as RT  # noqa: E402


def test_a_bare_name_becomes_a_real_file():
    got = RT.resolve_argv0(["python", "-c", "pass"])
    assert Path(got[0]).is_file(), got[0]
    assert got[1:] == ["-c", "pass"], "the arguments must be untouched"


@pytest.mark.skipif(os.name != "nt", reason="PATHEXT resolution is the Windows case")
def test_a_windows_script_resolves_to_its_extension():
    """The actual bug: npm is npm.CMD, and only `which` knows that."""
    if not shutil.which("npm"):
        pytest.skip("npm is not installed on this machine")
    got = RT.resolve_argv0(["npm", "install"])
    assert got[0].lower().endswith((".cmd", ".bat", ".exe")), got[0]
    assert Path(got[0]).is_file()


def test_a_path_is_left_alone():
    for given in (r"C:\tools\thing.exe", "/usr/bin/thing", "./thing"):
        assert RT.resolve_argv0([given, "x"]) == [given, "x"]


def test_an_unknown_command_keeps_its_name():
    """So the error names what the user asked for, not something invented."""
    assert RT.resolve_argv0(["definitely-not-a-real-binary", "x"]) == \
        ["definitely-not-a-real-binary", "x"]


def test_empty_and_non_string_arguments():
    assert RT.resolve_argv0([]) == []
    assert RT.resolve_argv0(["python", 8110]) == RT.resolve_argv0(["python", "8110"])


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
