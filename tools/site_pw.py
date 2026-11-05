"""Helpers for checking the website headless: serve docs/ on 127.0.0.1:8098 while a check runs, and open Edge through Playwright."""
import functools
import http.server
import threading
from pathlib import Path

DOCS = str(Path(__file__).resolve().parent.parent / "docs")
PORT = 8098


def serve():
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass
    h = functools.partial(QuietHandler, directory=DOCS)
    s = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


def browser(p, **kw):
    return p.chromium.launch(channel="msedge", headless=True, **kw)
