"""The Doctor can see what the 0.2.0 installer test found by hand: data files missing from a copy, a library the optional parts need, an installed copy that has no source to edit."""
import importlib.util

from hub import runtime as RT
from hub.features import diagnose as D, support as S


def test_a_whole_copy_has_no_problems_and_the_check_is_part_of_the_facts():
    c = D.install_check()
    assert c["problems"] == [] and c["data_files"] == {"commands.json": True, "media_sources.json": True, "apps.default.json": True} and c["voice_commands"] > 8
    assert '"install"' in S.facts()


def test_a_missing_library_is_named_with_what_it_costs(monkeypatch):
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda n, *a, **k: None if n == "numpy" else real(n, *a, **k))
    c = D.install_check()
    assert any("numpy" in p and "learning layer" in p for p in c["problems"])


def test_an_installed_copy_says_it_cannot_edit_code_and_the_doctor_is_told_what_to_do_then(monkeypatch):
    monkeypatch.setattr(RT, "FROZEN", True)
    monkeypatch.setattr(RT, "PACKAGED", True)
    assert D.install_check()["can_edit_code"] is False
    brief = S.brief_for("the hand function is not working")
    assert "INSTALLED copy" in brief and "Do not pretend to have changed anything" in brief
    for knowledge in ("MAP OF THE HUB", "hub/hand_tracking.py", "unshipped_surprises", "payloads.json", "Orbitron", "agent-art", "Anything the owner wants changed"):
        assert knowledge in brief
