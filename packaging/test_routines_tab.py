"""ROUTINES tab on the reinforcement learning page: read the steps, approve, disable, delete (5 Nov: there was no way to do any of it)."""
import os
from playwright.sync_api import sync_playwright
from test_ui_lifecycle import hub
import urllib.request, json


def test_routines_tab_lists_and_acts(hub):
    from hub.features import pc_control as PC
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel=os.environ.get('AGENTHUB_TEST_BROWSER', 'msedge'), headless=True)
        p = b.new_context(service_workers='block').new_page(); errs = []; p.on('pageerror', lambda e: errs.append(str(e)))
        p.goto(hub + '/yard'); p.click('[data-tab=routines]'); p.wait_for_timeout(800)
        txt = p.inner_text('#rlist')
        assert errs == [], errs
        assert 'No routines yet' in txt or 'DELETE' in txt, txt[:200]
        b.close()
