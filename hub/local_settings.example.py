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

# ── Optional: YouTube channels you can upload to ─────────────────────────────
# The tag is the label the uploader shows. Put each channel's OAuth files under
# youtube/credentials/<tag>/ (that folder is gitignored). Omit for no uploading.
#
# import os.path as _p
# _CRED = _p.join(_p.dirname(_p.dirname(_p.abspath(__file__))), "youtube", "credentials")
# YOUTUBE_ACCOUNTS = {
#     "my-channel": {
#         "secrets_file": _p.join(_CRED, "my-channel", "client_secrets.json"),
#         "token_file":   _p.join(_CRED, "my-channel", "youtube_token.pickle"),
#     },
# }

# ── Optional: pre-existing folder layout on THIS machine ─────────────────────
# Only useful if you had folders in place before setting up Locations. Omit both
# and the Hub uses its own defaults (an AgentHub folder on the drive with the
# most free space). A value is used only while the path still exists, and
# anything you save in the Locations UI always wins over it.
#
# LEGACY_PATHS = {
#     "opencode_home": r"C:\path\to\opencode",
#     "work_dir":      r"C:\path\to\opencode\worktrees",
#     "wiki_root":     r"C:\path\to\your\wiki",
#     "dl_audio":      r"C:\path\to\downloads\audio",
#     "dl_video":      r"C:\path\to\downloads\video",
#     "dl_cookies":    r"C:\path\to\cookies.txt",
#     "inbox":         r"C:\path\to\taildrop",
#     "outputs":       r"C:\path\to\finished\videos",
#     "tailscale_exe": r"C:\Program Files\Tailscale\tailscale.exe",
# }
#
# Project folders to offer. "project" = one repo, "collection" = a folder of repos.
# LEGACY_SOURCES = [
#     {"kind": "project", "path": r"C:\Code\my-repo", "slug": "my-repo", "name": "My Repo"},
#     {"kind": "collection", "path": r"C:\Code\repos", "new_projects_here": True},
# ]
