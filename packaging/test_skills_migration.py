"""skills_sync calls _migrate_user_skills at every start; a clean-up removed it as unused (14 Nov log: "user-skill migration skipped: cannot import name")."""
from hub import agent_knowledge as AK
from hub.agent_knowledge import skills_sync as SS


def test_the_migration_exists_and_is_a_no_op_from_source():
    assert callable(AK._migrate_user_skills)
    AK._migrate_user_skills()                                   # not packaged: nothing is moved, nothing raises


def test_an_installed_build_moves_a_skill_the_build_did_not_ship_into_the_users_folder(tmp_path, monkeypatch):
    shipped_dir, user_dir = tmp_path / "program" / "skills", tmp_path / "state" / "skills"
    for n in ("from-build", "my-own"):
        (shipped_dir / n).mkdir(parents=True)
        (shipped_dir / n / "SKILL.md").write_text("x", encoding="utf-8")
    (shipped_dir / ".shipped").write_text("from-build\n", encoding="utf-8")
    monkeypatch.setattr(AK, "SKILLS_DIR", shipped_dir)
    monkeypatch.setattr(AK, "SHIPPED_LIST", shipped_dir / ".shipped")
    monkeypatch.setattr(AK, "USER_SKILLS_DIR", user_dir)
    monkeypatch.setattr(AK._RT, "PACKAGED", True)
    AK._migrate_user_skills()
    assert (user_dir / "my-own" / "SKILL.md").is_file() and not (shipped_dir / "my-own").exists()       # moved out of the program folder
    assert (shipped_dir / "from-build").is_dir() and not (user_dir / "from-build").exists()             # what the build shipped stays


def test_sync_all_no_longer_warns_about_the_migration(caplog, monkeypatch):
    monkeypatch.setattr(SS, "compile_wiki_skills", lambda: None)
    monkeypatch.setattr(SS, "publish_skills", lambda: {"skills": 0, "targets": {}})
    with caplog.at_level("WARNING"):
        SS.sync_all()
    assert not [r for r in caplog.records if "migration skipped" in r.getMessage()]
