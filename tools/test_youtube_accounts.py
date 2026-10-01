"""A YouTube channel is its credential folder, added and removed in Settings.

Channels used to be hand-edited entries in hub/local_settings.py, so a fresh
install inherited a tag naming somebody else's account and adding one meant
editing Python. These pin the behaviour the Settings card relies on.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hub.features import youtube_accounts as YTA       # noqa: E402

GOOD = json.dumps({"installed": {"client_id": "x.apps.googleusercontent.com",
                                 "client_secret": "s", "redirect_uris": ["http://localhost"]}})


@pytest.fixture()
def creds(tmp_path, monkeypatch):
    d = tmp_path / "credentials"
    d.mkdir()
    monkeypatch.setattr(YTA, "YT_CRED_DIR", str(d))
    monkeypatch.setattr(YTA, "_legacy", lambda: {})
    return d


# ── a fresh install has nothing ───────────────────────────────────────────────
def test_a_fresh_install_lists_no_channels(creds):
    assert YTA.accounts() == []


def test_a_missing_credentials_folder_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(YTA, "YT_CRED_DIR", str(tmp_path / "never-created"))
    monkeypatch.setattr(YTA, "_legacy", lambda: {})
    assert YTA.accounts() == []


# ── adding, listing, forgetting ───────────────────────────────────────────────
def test_add_then_list(creds):
    YTA.add("IZ17-G", GOOD)
    assert YTA.accounts() == [{"tag": "IZ17-G", "authorized": False, "where": "folder"}]
    assert (creds / "IZ17-G" / "client_secrets.json").is_file()


def test_a_second_channel_joins_the_first(creds):
    YTA.add("IZ17-G", GOOD)
    YTA.add("Second Channel", GOOD)
    assert [a["tag"] for a in YTA.accounts()] == ["IZ17-G", "Second Channel"]


def test_authorized_follows_the_token_file(creds):
    YTA.add("IZ17-G", GOOD)
    assert YTA.accounts()[0]["authorized"] is False
    (creds / "IZ17-G" / "youtube_token.pickle").write_bytes(b"x")
    assert YTA.accounts()[0]["authorized"] is True


def test_forget_removes_the_sign_in_too(creds):
    YTA.add("IZ17-G", GOOD)
    (creds / "IZ17-G" / "youtube_token.pickle").write_bytes(b"x")
    assert YTA.forget("IZ17-G") is True
    assert YTA.accounts() == []
    assert not (creds / "IZ17-G").exists()


def test_forget_an_unknown_channel_says_so(creds):
    assert YTA.forget("nope") is False


def test_adding_twice_does_not_silently_replace(creds):
    YTA.add("IZ17-G", GOOD)
    with pytest.raises(ValueError, match="already has credentials"):
        YTA.add("IZ17-G", GOOD)


# ── a folder with no secrets is not a channel ─────────────────────────────────
def test_an_empty_folder_is_not_offered_as_a_channel(creds):
    (creds / "half-done").mkdir()
    assert YTA.accounts() == [], "a folder without client_secrets.json cannot upload"


# ── the tag names a folder, so it is guarded ──────────────────────────────────
@pytest.mark.parametrize("tag", ["../escape", "a/b", "a\b", "", "   ", ".hidden.",
                                 "con", "COM1", "x" * 41, "he:re"])
def test_a_tag_that_cannot_be_a_folder_is_refused(creds, tag):
    assert YTA.bad_tag(tag), f"{tag!r} should be refused"
    with pytest.raises(ValueError):
        YTA.add(tag, GOOD)


def test_surrounding_space_is_trimmed_not_refused(creds):
    """Typing a trailing space is a slip, not a different channel."""
    YTA.add("  Spaced  ", GOOD)
    assert [a["tag"] for a in YTA.accounts()] == ["Spaced"]
    # and looking it up the way it was typed still finds it
    assert YTA.paths("Spaced ")["secrets_file"] == str(creds / "Spaced" / "client_secrets.json")


def test_traversal_cannot_write_outside_the_credentials_folder(creds):
    with pytest.raises(ValueError):
        YTA.add("../../pwned", GOOD)
    assert not (creds.parent.parent / "pwned").exists()


def test_paths_refuses_a_bad_tag_instead_of_walking_out(creds):
    assert YTA.paths("../../etc") is None


# ── the wrong Google JSON is caught now, not mid-upload ───────────────────────
def test_a_service_account_key_is_refused_by_name(creds):
    key = json.dumps({"type": "service_account", "client_email": "x@y.iam.gserviceaccount.com"})
    with pytest.raises(ValueError, match="service-account"):
        YTA.add("svc", key)


def test_a_web_client_is_refused_with_the_fix(creds):
    web = json.dumps({"web": {"client_id": "x", "client_secret": "s"}})
    with pytest.raises(ValueError, match="Desktop app"):
        YTA.add("webby", web)


def test_a_non_json_file_is_refused(creds):
    with pytest.raises(ValueError, match="not valid JSON"):
        YTA.add("junk", "this is not json")


def test_an_api_key_json_is_refused(creds):
    with pytest.raises(ValueError, match="client_secrets"):
        YTA.add("apikey", json.dumps({"api_key": "AIzaSy"}))


def test_a_refused_file_leaves_no_half_made_channel(creds):
    with pytest.raises(ValueError):
        YTA.add("junk", "nope")
    assert YTA.accounts() == []
    assert not (creds / "junk").exists(), "a rejected add must not leave a folder behind"


# ── the old hand-edited config keeps working ──────────────────────────────────
def test_a_local_settings_channel_still_appears(creds, monkeypatch, tmp_path):
    old = tmp_path / "elsewhere"
    old.mkdir()
    (old / "client_secrets.json").write_text(GOOD, encoding="utf-8")
    monkeypatch.setattr(YTA, "_legacy", lambda: {
        "Legacy": {"secrets_file": str(old / "client_secrets.json"),
                   "token_file": str(old / "youtube_token.pickle")}})
    got = YTA.accounts()
    assert got == [{"tag": "Legacy", "authorized": False, "where": "local_settings.py"}]
    assert YTA.paths("Legacy")["secrets_file"] == str(old / "client_secrets.json")


def test_a_local_settings_channel_whose_files_are_gone_is_not_offered(creds, monkeypatch):
    monkeypatch.setattr(YTA, "_legacy", lambda: {
        "Stale": {"secrets_file": r"C:\gone\client_secrets.json"}})
    assert YTA.accounts() == [], "a channel whose credentials vanished cannot upload"


def test_the_folder_wins_over_local_settings(creds, monkeypatch):
    monkeypatch.setattr(YTA, "_legacy", lambda: {
        "IZ17-G": {"secrets_file": r"C:\old\client_secrets.json"}})
    YTA.add("IZ17-G", GOOD)
    assert YTA.paths("IZ17-G")["secrets_file"] == str(creds / "IZ17-G" / "client_secrets.json")
    assert [a["where"] for a in YTA.accounts()] == ["folder"]


# ── what the uploader asks for ────────────────────────────────────────────────
def test_paths_is_none_for_a_channel_that_was_never_added(creds):
    assert YTA.paths("ghost") is None


def test_paths_points_at_the_token_the_uploader_will_write(creds):
    YTA.add("IZ17-G", GOOD)
    got = YTA.paths("IZ17-G")
    assert got["token_file"] == str(creds / "IZ17-G" / "youtube_token.pickle")
