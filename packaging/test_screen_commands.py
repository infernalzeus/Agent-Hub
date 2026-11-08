"""'Open the dashboard' is a request to enter the main screen the ENTER button leads to. It was heard as "open an app called dashboard" and answered "Which app?".
Entered the way it is spoken: through the voice chat endpoint of a real Hub on its own state folder."""
import json
import urllib.request

import pytest

from test_ui_lifecycle import hub  # noqa: F401  (an isolated Hub on its own state folder)

OPEN = ["Open Dashboard for me.", "open the dashboard", "Please open the dashboard.", "take me to the dashboard", "go to the dashboard", "enter the dashboard now",
        "launch the main dashboard", "open my dashboard", "let me in", "open Home"]
NOT_OPEN = ["show the dashboard", "clear the dashboard", "tidy the dashboard", "open the compliance dashboard", "open the sleep dashboard in Edge"]


def _chat(hub, text):
    req = urllib.request.Request(hub + "/api/voice/chat", data=json.dumps({"text": text}).encode(), headers={"Content-Type": "application/json", "Origin": hub})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


@pytest.mark.parametrize("text", OPEN)
def test_these_phrasings_enter_the_main_screen(text):
    from hub.features import home_state as HS
    assert HS.ui_for(text, "")["open"] == "home"


@pytest.mark.parametrize("text", NOT_OPEN)
def test_these_are_not_a_request_to_enter(text):
    from hub.features import home_state as HS
    assert HS.ui_for(text, "")["open"] is None


def test_spoken_open_the_dashboard_reaches_the_screen_as_open_home(hub):
    got = _chat(hub, "Open Dashboard for me.")
    assert got["say"] == "Opening Home." and got["ui"]["open"] == "home" and got["backend"] == "rules"      # no router, no model, no "Which app?"


def test_ingest_an_app_asks_which_app_instead_of_reading_one_called_an(hub):
    got = _chat(hub, "ingest an app")
    assert got["say"] == "Which app should I read?"
    assert "Reading an" not in got["say"]
