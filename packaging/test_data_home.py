"""The hub keeps what it creates inside its own folder: no drive is ever picked automatically, and any location set outside raises a warning."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(code, **env):
    e = {**os.environ, "PYTHONUTF8": "1", **env}
    for k in ("AGENTHUB_WORK_ROOT", "AGENTHUB_STATE_DIR"):
        if k not in env:
            e.pop(k, None)
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=e, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-800:]
    return r.stdout.strip().splitlines()[-1]


def test_from_source_the_default_data_folder_is_inside_the_hub_folder():
    out = run("from hub import locations as L; print(L.BASE)", AGENTHUB_NO_LEGACY="1")
    assert Path(out) == ROOT / "data"


def test_a_hub_with_its_own_state_folder_keeps_its_data_under_it(tmp_path):
    out = run("from hub import locations as L; print(L.BASE); print(L.get('work_dir'))", AGENTHUB_NO_LEGACY="1", AGENTHUB_STATE_DIR=str(tmp_path / "state"))
    assert Path(out).is_relative_to(tmp_path)                      # the last line is work_dir
    assert not (Path(out).drive and Path(out).drive != tmp_path.drive)


def test_no_default_is_ever_derived_from_a_drive_scan():
    src = (ROOT / "hub" / "locations.py").read_text(encoding="utf-8")
    assert "free space" not in src.split("def _default_base")[1].split("WRITE_KEYS")[0] or "picked the drive" in src
    assert 'for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ"' not in src.split("def _default_base")[1].split("WRITE_KEYS")[0]
    assert "disk_usage" not in src.split("def _default_base")[1].split("WRITE_KEYS")[0]


def test_a_write_location_outside_the_hub_folder_raises_a_warning_and_an_inside_one_does_not():
    out = run("""
from hub import locations as L
import json, tempfile
outside = L.validate('work_dir', r'%s')
inside = L.validate('work_dir', str(L.BASE / 'work'))
print(json.dumps({'outside': outside['level'], 'flag': outside.get('outside'), 'inside': inside['level'], 'msg': outside['msg'][:30], 'ins': L.inside_hub(L.BASE / 'work'), 'out': L.inside_hub(r'%s')}))
""" % (tempfile.gettempdir() if False else r"C:\Windows_not_real_but_outside" if os.name != "nt" else str(Path(os.environ.get("TEMP", "C:/Temp")) / "somewhere"), str(Path(os.environ.get("TEMP", "C:/Temp")) / "somewhere")), AGENTHUB_NO_LEGACY="1")
    import json
    d = json.loads(out)
    assert d["outside"] == "warn" and d["flag"] is True and d["msg"].startswith("outside the Agent Hub folder")
    assert d["inside"] != "error" and d["ins"] is True and d["out"] is False


def test_setup_check_lists_every_outside_write_location(monkeypatch, tmp_path):
    from hub import locations as L
    from hub.features import setup_check as SC
    monkeypatch.setattr(L, "get", lambda k: str(tmp_path / "elsewhere" / k) if k in L.WRITE_KEYS else "")
    monkeypatch.setattr(L, "source", lambda k: "saved")
    titles = [i["title"] for i in SC._check() if "outside the Agent Hub folder" in i["title"]]
    assert len(titles) == len(L.WRITE_KEYS)
