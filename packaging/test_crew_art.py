"""The four core agents have vector pictures (the website's): Orchestrator, Neo, Smith and the Doctor. The Agency page shows them, large, animated. Small places (the Talk button, the dashboard's Doctor
block) keep the light PNG: an animated vector redrawn every frame on a 28 px button slowed the move into the dashboard. The landing page carries Smith's vector inside the page itself."""
import base64
import re
import urllib.request

import pytest

from test_ui_lifecycle import hub  # noqa: F401  (an isolated Hub on its own state folder)


def _get(url, referer=""):
    req = urllib.request.Request(url, headers={"Referer": referer} if referer else {})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.headers["Content-Type"], r.read()


@pytest.mark.parametrize("name", ["orchestrator", "neo", "smith", "doctor"])
def test_the_agency_page_gets_the_vector_art_and_everything_else_the_light_png(hub, name):
    kind, body = _get(f"{hub}/static/agent-icons/{name}.png", referer=hub + "/agents?embed=1")
    assert kind.startswith("image/svg+xml") and body.lstrip().startswith(b"<svg")
    kind, body = _get(f"{hub}/static/agent-icons/{name}.png", referer=hub + "/")
    assert kind == "image/png" and len(body) < 200_000


def test_the_talk_button_picture_is_the_light_png(hub):
    kind, body = _get(hub + "/smith-icon.png")
    assert kind == "image/png" and len(body) < 40_000


def test_the_landing_page_carries_smiths_animated_vector_and_a_still_picture_for_the_move_to_the_dashboard(hub):
    _, page = _get(hub + "/offline.html")
    html = page.decode("utf-8", "replace")
    m = re.search(r"data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)", html)
    assert m
    svg = base64.b64decode(m.group(1)).decode("utf-8", "replace")
    assert "lens-glint" in svg and "@keyframes glint" in svg and "prefers-reduced-motion" in svg           # the glasses glisten
    assert "data:image/png;base64," in html and "SM.still" in html                                       # the still one, swapped in at ENTER
