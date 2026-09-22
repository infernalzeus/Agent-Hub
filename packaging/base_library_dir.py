"""Print this interpreter's base Library/bin folder.

A venv built on a Conda base still needs three CPython native runtime DLLs from
there (ffi, sqlite3, libmpdec). build-core.ps1 copies only those.

A file rather than a `python -c` one-liner: Windows PowerShell strips double
quotes out of an inline string before a native executable sees it.
"""
import sys
from pathlib import Path

print(Path(sys.base_prefix) / "Library" / "bin")
