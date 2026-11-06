"""The personal learning layer is optional: the Hub starts and answers without hub/yard/, and the R button and its switches are off and hidden by default."""
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from test_ui_lifecycle import hub  # noqa: F401  (an isolated Hub on its own state folder)

ROOT = Path(__file__).resolve().parents[1]


def test_the_hub_builds_and_its_learning_hooks_stay_quiet_when_the_learning_layer_is_not_installed(tmp_path):
    code = textwrap.dedent('''
        import importlib.abc, sys
        class Block(importlib.abc.MetaPathFinder):
            def find_spec(self, name, path, target=None):
                if name == "hub.yard" or name.startswith("hub.yard."):
                    raise ImportError("hub.yard is not installed")
        sys.meta_path.insert(0, Block())
        import app
        assert app.YARD_FEATURES == [], app.YARD_FEATURES
        a = app.create_app()
        paths = {r.resource.canonical for r in a.router.routes() if hasattr(r.resource, "canonical")}
        assert "/api/status" in paths, "the Hub itself must still answer"
        assert not any(p.startswith("/api/yard") or p == "/yard" for p in paths)
        from hub.features import learning
        assert learning.enabled() is False
        learning.note("route", "x", "y")                       # a hook with nothing behind it does nothing and does not raise
        assert learning.status()["learning"]
        print("OK")
    ''')
    env = {**__import__("os").environ, "AGENTHUB_STATE_DIR": str(tmp_path), "AGENTHUB_NO_LEGACY": "1", "PYTHONUTF8": "1"}
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=90)
    assert out.returncode == 0 and "OK" in out.stdout, out.stderr[-1500:]


def test_the_settings_page_has_the_experimental_switch_and_the_api_takes_it_and_fresh_start(hub):
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_context(service_workers="block").new_page()
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        post = lambda body: pg.evaluate("b=>fetch('/api/yard/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}).then(async r=>({status:r.status,body:await r.json().catch(()=>null)}))", body)
        pg.goto(hub + "/setup#tools")
        got = post({"experimental": False})
        if got["body"] and got["body"].get("experimental", {}).get("forced_on_by_environment"):
            b.close()
            pytest.skip("held on by an environment variable")
        assert got["status"] == 200 and got["body"]["experimental"]["on"] is False and got["body"]["shadow"]["on"] is False
        pg.goto(hub + "/setup#tools")
        pg.reload()
        pg.wait_for_selector("#exp-box")
        pg.wait_for_function("document.getElementById('exp-toggle')")
        assert "Experimental" in pg.inner_text("#exp-box") and "off" in pg.inner_text("#exp-box")
        pg.once("dialog", lambda d: d.accept())
        pg.click("#exp-toggle")
        pg.wait_for_function("document.getElementById('exp-box').innerText.includes('ON')")
        assert pg.evaluate("fetch('/api/yard/settings').then(r=>r.json())")["experimental"]["on"] is True
        fresh = post({"fresh": True})                                                     # the button the STATUS tab uses: it used to be refused
        assert fresh["status"] == 200 and fresh["body"]["fresh_since"] > 0
        assert post({"nonsense": 1})["status"] == 400
        post({"experimental": False})
        b.close()
    assert errors == []
