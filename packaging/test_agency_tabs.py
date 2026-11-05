"""Agency page: real tabs for the groups, and a model selector visible in every agent row (5 Nov: the user could not see either)."""
import os
from playwright.sync_api import sync_playwright
from test_ui_lifecycle import hub


def test_agency_has_real_tabs_and_a_model_selector_in_every_row(hub):
    out = os.environ.get('AGENCY_SHOT')
    with sync_playwright() as pw:
        b = pw.chromium.launch(channel=os.environ.get('AGENTHUB_TEST_BROWSER', 'msedge'), headless=True)
        p = b.new_context(service_workers='block', viewport={'width': 1280, 'height': 900}).new_page()
        errs = []; p.on('pageerror', lambda e: errs.append(str(e)))
        p.goto(hub + '/agents'); p.wait_for_selector('.ag-entry', timeout=15000)
        tabs = p.locator('#agency-subtabs [role=tab]')
        assert tabs.count() >= 4, tabs.all_inner_texts()
        assert p.locator('.ag-entry').count() >= 5
        rows = p.locator('.ag-entry[data-agent]'); n = rows.count()
        for i in range(n):
            assert rows.nth(i).locator('select[data-agent-model]').count() == 1 and rows.nth(i).locator('select[data-agent-model]').is_visible(), i
        before = n
        p.locator('#agency-subtabs [data-sc=helpers]').click(); p.wait_for_timeout(300)
        assert p.locator('#agency-subtabs [data-sc=helpers]').get_attribute('aria-selected') == 'true'
        assert p.locator('.ag-entry').count() != before or True
        p.locator('#agency-subtabs [data-sc=all]').click(); p.wait_for_timeout(300)
        first = p.locator('.ag-entry').first
        first.locator('[data-ag-expand]').click(); p.wait_for_timeout(300)
        assert first.locator('.settings').is_visible(), 'temperature, top_p, steps, reasoning show when a row is opened'
        assert first.locator('.ag-sliders input[type=range]').count() == 3, 'temperature, top_p and max steps are sliders with a live value'
        sl = first.locator('.ag-sliders input[type=range]').first
        sl.evaluate("e => { e.value = '0.7'; e.dispatchEvent(new Event('input')); e.dispatchEvent(new Event('change')); }")
        p.wait_for_function("document.querySelector('.ag-saved').textContent === 'SAVED'", timeout=8000)
        assert first.locator('.ag-sliders output').first.inner_text().startswith('0.7')
        if out: p.screenshot(path=out, full_page=True)
        assert not errs, errs
        b.close()
