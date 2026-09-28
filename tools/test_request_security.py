"""Every write on the Hub must prove it came from the Hub.

Found by auditing the route table rather than by a failing test: seven
state-changing endpoints under /api/onboarding/ were exempt from the CSRF guard,
including install/{capability}, which downloads and runs software. A
cross-origin POST reached the handler; only a bogus capability name stopped it.

The exemption was defensible for reads - but GET is never blocked here, so it
only ever applied to writes. These tests pin the rule that replaced it: a write
needs a same-origin request or an integration token, with no exceptions.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from hub import request_security as RS  # noqa: E402


def test_nothing_is_exempt():
    """The specific regression. If a prefix is added here again, say why in the
    comment above EXEMPT_PREFIXES and change this test deliberately."""
    assert RS.EXEMPT_PREFIXES == (), \
        f"a CSRF exemption came back: {RS.EXEMPT_PREFIXES}"


def test_reads_are_never_blocked():
    """Which is why no exemption is needed for a bootstrap read."""
    assert RS.SAFE_METHODS == {"GET", "HEAD", "OPTIONS"}


def test_no_write_route_escapes_the_guard():
    """Walks the real route table, so a new unguarded write is caught here."""
    import app as hub_app
    application = hub_app.create_app()
    escaped = [
        f"{r.method} {getattr(r.resource, 'canonical', r.resource)}"
        for r in application.router.routes()
        if r.method not in RS.SAFE_METHODS
        and str(getattr(r.resource, "canonical", r.resource)).startswith(RS.EXEMPT_PREFIXES or ("\0",))
    ]
    assert not escaped, "these writes skip the CSRF guard:\n  " + "\n  ".join(escaped)


def test_the_guard_is_actually_installed():
    import app as hub_app
    application = hub_app.create_app()
    assert any(getattr(m, "__name__", "") == "middleware" and m.__module__.endswith("request_security")
               for m in application.middlewares), "the CSRF middleware is not installed"


@pytest.mark.parametrize("host,origin,ok", [
    ("localhost:8081", "http://localhost:8081", True),
    ("127.0.0.1:8081", "http://127.0.0.1:8081", True),
    ("localhost:8081", "http://localhost:9999", False),   # right name, wrong port
    ("localhost:8081", "https://evil.example", False),
    ("localhost:8081", "http://localhost.evil.example", False),   # suffix trick
])
def test_origin_matching(host, origin, ok):
    """A DNS-rebinding host must not count as same-origin just because the
    headers agree with each other."""
    class FakeRequest:
        def __init__(self):
            self.headers = {"Origin": origin, "Host": host}
            self.host = host
    assert RS._origin_ok(FakeRequest()) is ok, f"{origin} vs {host}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
