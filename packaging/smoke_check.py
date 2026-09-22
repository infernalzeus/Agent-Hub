"""Does the staged Hub actually start?

Run by build-core.ps1 against the staged tree, under a disposable profile, before
anything is frozen. Kept as a file rather than a `python -c` one-liner because
Windows PowerShell strips the quotes out of an inline string when handing it to
a native executable, which silently turned this check into a syntax error.
"""
import sys

import app

application = app.create_app()
app._selfcheck()
routes = len(list(application.router.routes()))
if routes < 100:
    print("Only %d routes registered - the staged tree is incomplete." % routes, file=sys.stderr)
    raise SystemExit(1)
print("Core import and optional-app startup: OK (%d routes)" % routes)
