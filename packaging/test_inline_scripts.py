"""Every inline <script> in the Python-embedded pages must be valid JavaScript.
5 Nov: a backslash-n written inside a Python string became a real newline inside a JS string and killed a whole page (twice)."""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

node = shutil.which("node")


@pytest.mark.skipif(not node, reason="node is not installed")
def test_inline_scripts_of_the_embedded_pages_parse():
    from hub import ui
    from hub.yard import ui as yard_ui, teach
    pages = {"offline": ui._OFFLINE_HTML, "yard": yard_ui._HTML, "teach": teach._HTML}
    bad = []
    for name, html in pages.items():
        for i, src in enumerate(re.findall(r"<script>(.*?)</script>", html, re.S)):
            f = Path(tempfile.mkdtemp()) / f"{name}{i}.js"
            f.write_text(src, encoding="utf-8")
            r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
            if r.returncode:
                bad.append((name, i, r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "?"))
    assert not bad, bad
