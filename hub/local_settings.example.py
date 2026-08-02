"""Template for hub/local_settings.py — copy this file to `local_settings.py`
(same folder) and fill in your own values. `local_settings.py` is gitignored.

Only include the names you actually want to override; anything you omit keeps the
safe default from config.py.
"""

# PC power-menu PIN. Leave empty / omit to keep the power menu DISABLED.
# Set a PIN before exposing the power menu on any network.
HUB_POWER_PIN = "0000"

# Optional header shortcuts (e.g. an smb:// link to your NAS). Omit for none.
SHORTCUTS = [
    {
        "name": "SMB",
        "emoji": "🗂️",
        "href": "smb://YOUR-HOST-OR-TAILNET-IP/YourShare",
        "title": "Open your share in the Files app",
    },
]

# Absolute path to the interpreter that has yt_dlp installed (YouTube download).
# Omit to use whatever "python3.11" resolves to on PATH.
YT_DL_PYTHON = r"C:\path\to\python3.11.exe"
