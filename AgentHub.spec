# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['packaging/agenthub_launcher.py'],
    pathex=[],
    binaries=[],
    datas=[('favicon.png', '.'), ('favicon-64.png', '.'), ('favicon-256.png', '.'), ('hub/apps.default.json', 'hub'), ('hub/agent_knowledge', 'hub/agent_knowledge'), ('file-browser', 'file-browser'), ('youtube/ytdl.py', 'youtube'), ('youtube/yt_upload.py', 'youtube'), ('youtube/credentials/README.md', 'youtube/credentials')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['hub.local_settings', 'PyQt5', 'PySide6', 'tkinter'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AgentHub',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['favicon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AgentHub',
)
