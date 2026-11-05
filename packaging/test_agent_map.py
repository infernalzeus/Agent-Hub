"""The agent list is exhaustive and every member has been decided on for the learners: nothing joins the Hub unseen by the RL checklist."""
from test_ui_lifecycle import hub  # noqa: F401  (the isolated Hub fixture)
from hub import agent_knowledge as AK
from hub.features import agent_map as M


def test_every_persona_and_helper_is_a_node_and_has_a_coverage_decision():
    m = M.build()
    ids = {n["id"] for n in m["nodes"]}
    assert {a["name"] for a in AK.list_agents()} <= ids                 # every persona file
    assert {"smith", "neo", "doctor", "desktop", "router", "yard", "bandit-model", "bandit-rung", "recorder"} <= ids
    assert m["complete"] and m["unasked"] == [], m["unasked"]           # a new agent with no decision fails here


def test_coverage_has_no_stale_entries_and_edges_join_real_nodes():
    m = M.build()
    ids = {n["id"] for n in m["nodes"]}
    assert set(M.COVERAGE) <= ids, set(M.COVERAGE) - ids               # an entry for an agent that no longer exists
    assert all(e["from"] in ids and e["to"] in ids for e in m["edges"])
    pairs = {(e["from"], e["to"]) for e in m["edges"]}
    assert ("smith", "neo") in pairs and ("doctor", "neo") in pairs and ("smith", "doctor") in pairs
    assert ("orchestrator", "coder") in pairs and ("recorder", "bandit-model") in pairs


def test_no_decision_is_left_unrecorded_and_a_new_gap_would_be_named():
    m = M.build()
    assert m["gaps"] == []                                              # since 5 Nov every decision is at least recorded; a new gap must be named in COVERAGE
    assert M.COVERAGE["doctor"]["state"] == "logged" and M.COVERAGE["orchestrator"]["state"] == "logged"
    assert all(c["state"] in ("learned", "logged", "gap", "by-design") and c["note"] for c in m["coverage"].values())


def test_the_agents_page_has_the_how_they_work_together_tab(hub):
    import os
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(channel=os.environ.get("PW_CHANNEL") or None)
        pg = b.new_page()
        pg.goto(hub + "/agents#map")
        pg.wait_for_selector("[data-fam=map].on", timeout=15000)
        txt = pg.inner_text("#list")
        assert "WHO CALLS WHOM" in txt.upper() and "neo" in txt.lower() and "doctor" in txt.lower() and "orchestrator" in txt.lower()
        assert "WHAT THE LEARNERS CAN SEE" in txt and "gap" in txt.lower()
        b.close()
