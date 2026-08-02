"""
File Browser — browse, view, and download files on N:\\ from any device on the
tailnet, in-browser (images/video preview inline, everything else downloads).

Standalone aiohttp app, spawned on demand by Agent Hub exactly like Movie
Clipper. Read-only: no delete/rename/upload — just browse and view.

Run:  python app.py
Env:  FB_WEB_HOST (default 0.0.0.0), FB_WEB_PORT (default 8092),
      FB_BASE_PATH (default "" — set by Agent Hub when reverse-proxied)
"""
from __future__ import annotations

import mimetypes
import os
from pathlib import Path

from aiohttp import web

ROOT = Path(os.getenv("FB_ROOT", "N:/")).resolve()

HOST = os.getenv("FB_WEB_HOST", "0.0.0.0")
PORT = int(os.getenv("FB_WEB_PORT", "8092"))
BASE_PATH = os.getenv("FB_BASE_PATH", "").rstrip("/")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".heic", ".heif"}
_MIME_OVERRIDES = {".heic": "image/heic", ".heif": "image/heif"}
VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v"}
AUDIO_EXTS = {".mp3", ".m4a", ".flac", ".wav", ".ogg", ".aac", ".wma", ".opus", ".aiff"}
# Rendered inline in the viewer overlay as text. Anything not image/video/text
# gets a download panel instead — the page itself never navigates away, which
# is what used to strand the iPad PWA (no browser chrome = no way back).
TEXT_EXTS = {".txt", ".srt", ".vtt", ".sub", ".md", ".json", ".log", ".csv", ".ini",
             ".cfg", ".conf", ".toml", ".yaml", ".yml", ".xml", ".html", ".htm",
             ".nfo", ".py", ".js", ".ts", ".css", ".bat", ".ps1", ".sh"}


def _safe_resolve(rel: str) -> Path:
    """Resolve a client-supplied relative path against ROOT, refusing to leave it."""
    candidate = (ROOT / rel.lstrip("/\\")).resolve()
    if candidate != ROOT and ROOT not in candidate.parents:
        raise web.HTTPForbidden()
    return candidate


def _kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in TEXT_EXTS:
        return "text"
    return "file"


def _human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


routes = web.RouteTableDef()


@routes.get("/status")
async def status(request: web.Request) -> web.Response:
    return web.json_response({"busy": False})


@routes.get("/list")
async def list_dir(request: web.Request) -> web.Response:
    rel = request.query.get("path", "")
    target = _safe_resolve(rel)
    if not target.is_dir():
        raise web.HTTPNotFound()

    folders, files = [], []
    try:
        with os.scandir(target) as it:
            for entry in it:
                try:
                    st = entry.stat()
                    if entry.is_dir():
                        folders.append({
                            "name": entry.name,
                            "abs_path": str(Path(entry.path)),
                            "mtime": st.st_mtime,
                        })
                    else:
                        p = Path(entry.path)
                        files.append({
                            "name": entry.name,
                            "size": st.st_size,
                            "size_h": _human_size(st.st_size),
                            "kind": _kind(p),
                            "mtime": st.st_mtime,
                            "abs_path": str(p),
                        })
                except OSError:
                    continue
    except PermissionError:
        raise web.HTTPForbidden()

    folders.sort(key=lambda f: f["name"].lower())
    files.sort(key=lambda f: f["name"].lower())

    rel_display = target.relative_to(ROOT).as_posix()
    if rel_display == ".":
        rel_display = ""

    return web.json_response({"path": rel_display, "folders": folders, "files": files})


@routes.get("/view")
async def view_file(request: web.Request) -> web.StreamResponse:
    rel = request.query.get("path", "")
    target = _safe_resolve(rel)
    if not target.is_file():
        raise web.HTTPNotFound()

    ext = target.suffix.lower()
    ctype = _MIME_OVERRIDES.get(ext) or mimetypes.guess_type(str(target))[0] or "application/octet-stream"

    # Manual chunked read instead of web.FileResponse: FileResponse uses Windows'
    # TransmitFile sendfile path internally, which silently fails (connection
    # closes with zero body bytes) on single ranges over ~2GB — exactly the
    # size of a full-length movie. Plain buffered reads have no such ceiling.
    file_size = target.stat().st_size
    start, end, status = 0, file_size - 1, 200

    range_header = request.headers.get("Range", "")
    if range_header.startswith("bytes="):
        start_s, _, end_s = range_header[len("bytes="):].partition("-")
        if start_s == "" and end_s:
            start = max(0, file_size - int(end_s))
            end = file_size - 1
        else:
            start = int(start_s) if start_s else 0
            end = int(end_s) if end_s else file_size - 1
        start = max(0, min(start, file_size - 1))
        end = max(start, min(end, file_size - 1))
        status = 206

    length = end - start + 1

    resp = web.StreamResponse(status=status)
    resp.content_type = ctype
    resp.headers["Accept-Ranges"] = "bytes"
    resp.content_length = length
    if status == 206:
        resp.headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    if _kind(target) == "file":
        resp.headers["Content-Disposition"] = f'attachment; filename="{target.name}"'

    await resp.prepare(request)

    chunk_size = 1024 * 1024
    with open(target, "rb") as f:
        f.seek(start)
        remaining = length
        while remaining > 0:
            data = f.read(min(chunk_size, remaining))
            if not data:
                break
            await resp.write(data)
            remaining -= len(data)

    await resp.write_eof()
    return resp


@routes.get("/")
async def index(request: web.Request) -> web.Response:
    return web.Response(text=_render_html(), content_type="text/html", charset="utf-8")


@routes.get("/favicon.png")
async def favicon_png(request: web.Request) -> web.Response:
    path = Path(__file__).parent / "favicon.png"
    if not path.exists():
        raise web.HTTPNotFound()
    return web.Response(body=path.read_bytes(), content_type="image/png")


@routes.get("/favicon.svg")
async def favicon_svg(request: web.Request) -> web.Response:
    return web.Response(text=_render_favicon_svg(), content_type="image/svg+xml", charset="utf-8")


def create_app() -> web.Application:
    app = web.Application()
    app.add_routes(routes)
    return app


def main() -> None:
    app = create_app()
    print(f"File Browser -> http://{HOST}:{PORT}  (root: {ROOT})")
    web.run_app(app, host=HOST, port=PORT, print=None)


_FAVICON_SVG = """\
<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <clipPath id="c"><circle cx="32" cy="32" r="32"/></clipPath>
  </defs>
  <image href="__BASE_PATH__/favicon.png" x="0" y="0" width="64" height="64"
         clip-path="url(#c)" preserveAspectRatio="xMidYMid meet"/>
</svg>
"""

_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#080c28">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>File Browser</title>
<link rel="icon" type="image/svg+xml" href="__BASE_PATH__/favicon.svg">
<link rel="apple-touch-icon" href="__BASE_PATH__/favicon.png">
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600&family=Orbitron:wght@400;700;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#080c28;--panel:rgba(8,12,40,0.88);
  --border-dim:rgba(0,230,118,0.22);--border-bright:rgba(0,230,118,0.55);
  --accent:#00e676;--text:rgba(0,230,118,0.90);--text-muted:rgba(0,230,118,0.52);--text-faint:rgba(0,230,118,0.22);
}
html{background:#080c28;min-height:100dvh}
html,body{min-height:100%;min-height:100dvh;background:linear-gradient(150deg,#080c28 0%,#0d1050 45%,#18095c 100%);
  font-family:'Outfit',system-ui,sans-serif;color:var(--text);
  padding:env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left)}
body{padding:0 0 40px;max-width:720px;margin:0 auto}
header{padding:18px 16px 14px;border-bottom:1px solid var(--border-dim);display:flex;align-items:center;gap:12px}
.brand{font-family:'Orbitron',monospace;font-size:14px;font-weight:900;color:var(--accent);letter-spacing:3px;flex:1;min-width:0}
.up-btn{font-family:'Orbitron',monospace;font-size:11px;letter-spacing:1px;color:var(--accent);background:transparent;
  border:1px solid var(--border-bright);border-radius:8px;padding:9px 15px;cursor:pointer;flex-shrink:0;transition:all .15s}
.up-btn:hover:not(:disabled){background:rgba(0,230,118,.1);box-shadow:0 0 10px rgba(0,230,118,.18)}
.up-btn:disabled{opacity:.35;cursor:default}
#crumbs{padding:12px 16px 6px;font-size:12px;color:var(--text-muted);word-break:break-all}
#crumbs a{color:var(--accent);text-decoration:none;cursor:pointer}
#crumbs a:hover{text-decoration:underline}
#toolbar{display:flex;align-items:center;gap:8px;padding:4px 16px 12px}
#toolbar label{font-family:'Orbitron',monospace;font-size:9px;letter-spacing:1px;color:var(--text-faint)}
#toolbar select{background:var(--bg);border:1px solid var(--border-dim);border-radius:6px;color:var(--text);
  padding:6px 8px;font-size:12px;font-family:'Outfit',inherit;outline:none;cursor:pointer}
#toolbar select:focus{border-color:var(--accent)}
#sort-dir{background:transparent;border:1px solid var(--border-bright);border-radius:6px;color:var(--accent);
  width:32px;height:32px;font-size:13px;cursor:pointer;flex-shrink:0;transition:all .15s}
#sort-dir:hover{background:rgba(0,230,118,.1)}
#list{padding:0 12px}
.entry{display:flex;align-items:center;gap:12px;padding:12px 10px;border-bottom:1px solid var(--border-dim);cursor:pointer;
  -webkit-user-select:none;user-select:none;-webkit-touch-callout:none}
.entry:hover{background:rgba(0,230,118,.05)}
.entry-icon{font-size:20px;width:26px;text-align:center;flex-shrink:0}
.entry-icon svg{display:block;margin:0 auto;filter:drop-shadow(0 0 4px currentColor);opacity:.95}
.entry-name{flex:1;font-size:13.5px;word-break:break-all}
.entry-size{font-size:11px;color:var(--text-faint);flex-shrink:0}
#empty{padding:30px 16px;text-align:center;color:var(--text-faint);font-size:12.5px}
#viewer{display:none;position:fixed;inset:0;background:rgba(0,0,0,.92);z-index:200;
  align-items:center;justify-content:center;padding:20px}
#viewer.open{display:flex}
#viewer img, #viewer video{max-width:100%;max-height:100%;border-radius:6px}
#viewer-close{position:absolute;top:16px;right:20px;font-size:22px;color:var(--text);cursor:pointer;
  background:none;border:none;z-index:210}
.text-view{width:min(92vw,680px);max-height:82dvh;overflow:auto;background:var(--panel);
  border:1px solid var(--border-dim);border-radius:8px;padding:14px;font-size:12px;line-height:1.5;
  color:var(--text);white-space:pre-wrap;word-break:break-word;
  font-family:ui-monospace,Consolas,monospace;-webkit-overflow-scrolling:touch}
.dl-panel{background:var(--panel);border:1px solid var(--border-dim);border-radius:10px;
  padding:24px 26px;text-align:center;max-width:min(92vw,340px)}
.dl-icon{font-size:34px}
.dl-name{font-size:13px;margin-top:10px;word-break:break-all;color:var(--text)}
.dl-size{font-size:11px;color:var(--text-faint);margin-top:4px}
.panel-btn{font-family:'Orbitron',monospace;font-size:10px;letter-spacing:1px;margin-top:16px;
  padding:10px 20px;border-radius:6px;border:1px solid var(--border-bright);background:transparent;
  color:var(--accent);cursor:pointer}
.panel-btn:hover{background:rgba(0,230,118,.1)}
.copy-panel{background:var(--panel);border:1px solid var(--border-dim);border-radius:10px;
  padding:18px;width:min(92vw,480px);text-align:center}
.copy-panel-label{font-family:'Orbitron',monospace;font-size:9px;letter-spacing:1.5px;
  color:var(--text-faint);margin-bottom:10px}
.copy-input{width:100%;background:var(--bg);border:1px solid var(--border-dim);border-radius:6px;
  color:var(--text);padding:9px 10px;font-size:12px;font-family:ui-monospace,Consolas,monospace}
.copy-toast{position:fixed;left:50%;bottom:calc(28px + env(safe-area-inset-bottom));
  transform:translateX(-50%);background:rgba(8,12,40,.97);border:1px solid var(--accent);
  color:var(--accent);font-family:'Orbitron',monospace;font-size:11px;letter-spacing:1px;
  padding:10px 18px;border-radius:8px;z-index:300;box-shadow:0 0 20px rgba(0,230,118,.2);
  animation:toastPop .15s ease}
@keyframes toastPop{from{opacity:0;transform:translateX(-50%) translateY(8px)}to{opacity:1;transform:translateX(-50%) translateY(0)}}
</style>
</head>
<body>

<header>
  <div class="brand">📁 FILE BROWSER</div>
  <button type="button" id="up-btn" class="up-btn" title="Up one folder">⬆ UP</button>
</header>
<div id="crumbs"></div>
<div id="toolbar">
  <label for="sort-by">SORT</label>
  <select id="sort-by">
    <option value="name">Name</option>
    <option value="type">Type</option>
    <option value="size">Size</option>
    <option value="date">Date modified</option>
  </select>
  <button type="button" id="sort-dir" title="Ascending / descending">▲</button>
</div>
<div id="list"></div>

<div id="viewer">
  <button id="viewer-close">✕</button>
  <div id="viewer-content"></div>
</div>

<script>
const BASE_PATH = '__BASE_PATH__';
const crumbsEl = document.getElementById('crumbs');
const listEl   = document.getElementById('list');
const upBtn    = document.getElementById('up-btn');
const sortSel  = document.getElementById('sort-by');
const sortDirBtn = document.getElementById('sort-dir');
let currentPath = '';
let sortDir = localStorage.getItem('fbSortDir') || 'asc';
sortSel.value = localStorage.getItem('fbSortBy') || 'name';
sortDirBtn.textContent = sortDir === 'asc' ? '▲' : '▼';
sortSel.onchange = () => { localStorage.setItem('fbSortBy', sortSel.value); renderList(); };
sortDirBtn.onclick = () => {
  sortDir = sortDir === 'asc' ? 'desc' : 'asc';
  localStorage.setItem('fbSortDir', sortDir);
  sortDirBtn.textContent = sortDir === 'asc' ? '▲' : '▼';
  renderList();
};
const viewer   = document.getElementById('viewer');
const viewerContent = document.getElementById('viewer-content');

// ── Stylish per-type icons (inline SVG, neon on dark; some in the theme accent)
// Folder + code use the theme green; the rest use complementary neon colours.
const ICONS = {
  folder:  {c: '#00e676', p: '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>'},
  image:   {c: '#f472b6', p: '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.09-3.09a2 2 0 0 0-2.82 0L6 21"/>'},
  video:   {c: '#a78bfa', p: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="m10 8 6 4-6 4Z"/>'},
  audio:   {c: '#22d3ee', p: '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>'},
  pdf:     {c: '#ff6b6b', p: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v5h5"/><path d="M9 15h6"/><path d="M9 18h6"/>'},
  doc:     {c: '#7dd3fc', p: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v5h5"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/>'},
  code:    {c: '#00e676', p: '<path d="m16 18 6-6-6-6"/><path d="m8 6-6 6 6 6"/>'},
  archive: {c: '#ffc147', p: '<rect x="2" y="4" width="20" height="5" rx="1"/><path d="M4 9v10a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1V9"/><path d="M10 13h4"/>'},
  file:    {c: '#8aa0b6', p: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/>'},
};
const EXT_ICON = {};
(function () {
  const grp = (cat, exts) => exts.split(' ').forEach((e) => { EXT_ICON[e] = cat; });
  grp('image',   'png jpg jpeg gif webp bmp svg heic heif avif ico tif tiff');
  grp('video',   'mp4 mkv mov avi webm m4v wmv flv mpg mpeg');
  grp('audio',   'mp3 m4a flac wav ogg aac wma opus aiff');
  grp('pdf',     'pdf');
  grp('doc',     'txt md rtf doc docx odt xls xlsx csv ppt pptx srt vtt sub log nfo');
  grp('code',    'py js ts jsx tsx json html htm css c cpp h hpp java go rs rb php sh bat ps1 yaml yml toml xml ini cfg conf ipynb');
  grp('archive', 'zip rar 7z tar gz bz2 xz iso');
})();

function _svg(cat) {
  const ic = ICONS[cat] || ICONS.file;
  // color via style + stroke:currentColor so the CSS drop-shadow glow matches.
  return `<svg viewBox="0 0 24 24" width="20" height="20" fill="none" style="color:${ic.c}" `
       + `stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ic.p}</svg>`;
}
function folderIcon() { return _svg('folder'); }
function iconForFile(name, kind) {
  let cat = EXT_ICON[extOf(name)];
  if (!cat) cat = (kind === 'image' || kind === 'video' || kind === 'audio') ? kind
                 : (kind === 'text' ? 'doc' : 'file');
  return _svg(cat);
}

function renderCrumbs(path) {
  crumbsEl.innerHTML = '';
  const rootLink = document.createElement('a');
  rootLink.textContent = 'N:\\\\';
  rootLink.onclick = () => load('');
  crumbsEl.appendChild(rootLink);

  if (!path) return;
  const parts = path.split('/');
  let acc = '';
  for (const part of parts) {
    acc = acc ? acc + '/' + part : part;
    crumbsEl.appendChild(document.createTextNode(' / '));
    const a = document.createElement('a');
    a.textContent = part;
    const target = acc;
    a.onclick = () => load(target);
    crumbsEl.appendChild(a);
  }
}

let currentData = {path: '', folders: [], files: []};

async function load(path) {
  const res = await fetch(`${BASE_PATH}/list?path=${encodeURIComponent(path)}`);
  if (!res.ok) { listEl.innerHTML = '<div id="empty">Could not open that folder.</div>'; return; }
  const data = await res.json();
  currentData = data;
  currentPath = data.path || '';
  upBtn.disabled = !currentPath;   // nothing above the root
  // Folder navigation deliberately does NOT push history: the UP button handles
  // going up, so the phone's swipe-back stays a single step that exits back to
  // Agent Hub (the page that opened the file browser) instead of walking folders.
  renderCrumbs(data.path);
  renderList();
}

function extOf(name) { const i = name.lastIndexOf('.'); return i > 0 ? name.slice(i + 1).toLowerCase() : ''; }

// Sort a folder/file group by the chosen key; name is always the tiebreaker so
// order is stable. Folders have no size/kind, so those keys fall back to name.
function sortEntries(arr, key, dir, isFolder) {
  const byName = (a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase());
  const primary = {
    name: byName,
    size: (a, b) => (a.size || 0) - (b.size || 0),
    date: (a, b) => (a.mtime || 0) - (b.mtime || 0),
    type: (a, b) => isFolder ? 0
      : ((a.kind || '').localeCompare(b.kind || '') || extOf(a.name).localeCompare(extOf(b.name))),
  }[key] || byName;
  const mul = dir === 'desc' ? -1 : 1;
  return arr.slice().sort((a, b) => { const c = primary(a, b); return (c !== 0 ? c : byName(a, b)) * mul; });
}

function renderList() {
  const key = sortSel.value, dir = sortDir, data = currentData;
  listEl.innerHTML = '';
  if (!data.folders.length && !data.files.length) {
    listEl.innerHTML = '<div id="empty">Empty folder.</div>';
    return;
  }
  for (const folder of sortEntries(data.folders, key, dir, true)) {
    const row = document.createElement('div');
    row.className = 'entry';
    const childPath = data.path ? data.path + '/' + folder.name : folder.name;
    row.innerHTML = `<div class="entry-icon">${folderIcon()}</div><div class="entry-name">${folder.name}</div>`;
    attachLongPress(row, () => copyPath(folder.abs_path), () => load(childPath));
    listEl.appendChild(row);
  }
  for (const f of sortEntries(data.files, key, dir, false)) {
    const row = document.createElement('div');
    row.className = 'entry';
    const filePath = data.path ? data.path + '/' + f.name : f.name;
    row.innerHTML = `<div class="entry-icon">${iconForFile(f.name, f.kind)}</div>
      <div class="entry-name">${f.name}</div><div class="entry-size">${f.size_h}</div>`;
    attachLongPress(row, () => copyPath(f.abs_path), () => openFile(filePath, f));
    listEl.appendChild(row);
  }
}

// ── Long-press to copy absolute path ─────────────────────────────────────────

function attachLongPress(el, onLongPress, onTap) {
  // The long-press action runs in the touchend/mouseup handler, NOT in the
  // timer callback: Safari only honors clipboard writes made inside a user
  // gesture's call stack, and a setTimeout callback doesn't count. The timer
  // just marks "this press was long enough"; releasing the finger executes it.
  // `moved` distinguishes a scroll from a tap — without it, dragging past a row
  // and lifting fired that row's tap (the "sticky touch" bug).
  let timer = null, fired = false, moved = false, pressing = false, sx = 0, sy = 0;
  const pt = (e) => (e.touches && e.touches[0]) ? e.touches[0] : e;
  const start = (e) => {
    fired = false; moved = false; pressing = true;
    const p = pt(e); sx = p.clientX; sy = p.clientY;
    timer = setTimeout(() => { if (!moved) fired = true; }, 550);
  };
  const move = (e) => {
    if (!pressing) return;
    const p = pt(e);
    if (Math.abs(p.clientX - sx) > 10 || Math.abs(p.clientY - sy) > 10) {
      moved = true;
      if (timer) { clearTimeout(timer); timer = null; }
    }
  };
  const cancel = () => { pressing = false; if (timer) { clearTimeout(timer); timer = null; } };
  const end = (e) => {
    const didMove = moved;
    cancel();
    if (didMove) return;              // it was a scroll/drag, not a tap
    if (fired) {
      // Suppress the compatibility mouse/click events a touch also generates,
      // so the long-press doesn't ALSO fire the tap action.
      if (e.cancelable) e.preventDefault();
      onLongPress();
    } else if (onTap) {
      onTap();
    }
  };
  el.addEventListener('touchstart', start, {passive: true});
  el.addEventListener('touchmove', move, {passive: true});
  el.addEventListener('touchend', end);
  el.addEventListener('touchcancel', cancel);
  el.addEventListener('mousedown', start);
  el.addEventListener('mousemove', move);
  el.addEventListener('mouseup', end);
  el.addEventListener('mouseleave', cancel);
}

function showToast(msg) {
  const t = document.createElement('div');
  t.className = 'copy-toast';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 1600);
}

function copyPathFallback(text) {
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.readOnly = true;  // iOS: stops the keyboard popping up on focus
  ta.style.position = 'fixed';
  ta.style.top = '-1000px';
  ta.style.left = '-1000px';
  document.body.appendChild(ta);
  ta.focus({preventScroll: true});
  ta.select();
  ta.setSelectionRange(0, text.length);
  let ok = false;
  try { ok = document.execCommand('copy'); } catch (err) { ok = false; }
  document.body.removeChild(ta);
  return ok;
}

function copyPath(absPath) {
  // Deliberately synchronous-first: this is called from inside the touchend
  // gesture, and execCommand('copy') only works while that gesture's call
  // stack is live. An await before it would void the gesture. The modern
  // navigator.clipboard API needs a secure context (HTTPS/localhost) so over
  // plain HTTP it's the execCommand path that does the real work.
  if (copyPathFallback(absPath)) {
    showToast('Path copied');
    return;
  }
  if (window.isSecureContext && navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(absPath).then(
      () => showToast('Path copied'),
      () => showCopyPanel(absPath),
    );
    return;
  }
  // Last resort: show the path in a panel with its own COPY button (a plain
  // button tap is always a clean gesture) — never a dead "copy failed".
  showCopyPanel(absPath);
}

function showCopyPanel(text) {
  viewerContent.innerHTML = '';
  const panel = document.createElement('div');
  panel.className = 'copy-panel';
  const label = document.createElement('div');
  label.className = 'copy-panel-label';
  label.textContent = 'FILE PATH';
  const input = document.createElement('input');
  input.className = 'copy-input';
  input.type = 'text';
  input.value = text;
  input.readOnly = true;
  const btn = document.createElement('button');
  btn.className = 'panel-btn';
  btn.textContent = 'COPY';
  btn.onclick = () => {
    input.focus({preventScroll: true});
    input.setSelectionRange(0, text.length);
    let ok = false;
    try { ok = document.execCommand('copy'); } catch (err) { ok = false; }
    if (ok) { showToast('Path copied'); closeViewer(); }
    else { showToast('Select the text and copy manually'); }
  };
  panel.append(label, input, btn);
  viewerContent.appendChild(panel);
  viewer.classList.add('open');
}

// Rule: NOTHING here may navigate the top-level page (window.location).
// In the installed-PWA case there's no browser chrome, so navigating the page
// to a raw file response left no way back — the app had to be force-killed.
// Every kind opens inside the overlay viewer instead.
const TEXT_PREVIEW_MAX = 2 * 1024 * 1024;  // bigger than this → download panel

function openFile(path, f) {
  const url = `${BASE_PATH}/view?path=${encodeURIComponent(path)}`;
  if (f.kind === 'image') {
    viewerContent.innerHTML = `<img src="${url}">`;
    viewer.classList.add('open');
  } else if (f.kind === 'video') {
    viewerContent.innerHTML = `<video src="${url}" controls autoplay></video>`;
    viewer.classList.add('open');
  } else if (f.kind === 'audio') {
    viewerContent.innerHTML = `<audio src="${url}" controls autoplay style="width:min(88vw,420px)"></audio>`;
    viewer.classList.add('open');
  } else if (f.kind === 'text' && f.size <= TEXT_PREVIEW_MAX) {
    showTextPreview(url, f);
  } else {
    showDownloadPanel(url, f);
  }
}

async function showTextPreview(url, f) {
  viewerContent.innerHTML = '<div class="dl-panel">Loading…</div>';
  viewer.classList.add('open');
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const text = await res.text();
    const pre = document.createElement('pre');
    pre.className = 'text-view';
    pre.textContent = text;
    viewerContent.innerHTML = '';
    viewerContent.appendChild(pre);
  } catch (err) {
    showDownloadPanel(url, f);
  }
}

function showDownloadPanel(url, f) {
  viewerContent.innerHTML = '';
  const panel = document.createElement('div');
  panel.className = 'dl-panel';
  const icon = document.createElement('div');
  icon.className = 'dl-icon';
  icon.textContent = iconFor(f.kind);
  const name = document.createElement('div');
  name.className = 'dl-name';
  name.textContent = f.name;
  const size = document.createElement('div');
  size.className = 'dl-size';
  size.textContent = f.size_h;
  const btn = document.createElement('button');
  btn.className = 'panel-btn';
  btn.textContent = 'DOWNLOAD';
  btn.onclick = () => {
    // Anchor click, never location.href — the page stays alive underneath,
    // and target=_blank means even a browser that renders the file inline
    // does it in an escapable view, not over the app.
    const a = document.createElement('a');
    a.href = url;
    a.download = f.name;
    a.target = '_blank';
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    a.remove();
  };
  panel.append(icon, name, size, btn);
  viewerContent.appendChild(panel);
  viewer.classList.add('open');
}

function closeViewer() {
  viewer.classList.remove('open');
  viewerContent.innerHTML = '';
}

document.getElementById('viewer-close').onclick = closeViewer;
// Tapping the dark backdrop also closes — one more way out, never trapped.
viewer.addEventListener('click', (e) => { if (e.target === viewer) closeViewer(); });

// ── Up / back navigation ─────────────────────────────────────────────────────
function goUp() {
  if (!currentPath) return;
  const i = currentPath.lastIndexOf('/');
  load(i >= 0 ? currentPath.slice(0, i) : '');
}
upBtn.onclick = goUp;

load('');
</script>
</body>
</html>
"""


def _render_html() -> str:
    return _HTML.replace("__BASE_PATH__", BASE_PATH)


def _render_favicon_svg() -> str:
    return _FAVICON_SVG.replace("__BASE_PATH__", BASE_PATH)


if __name__ == "__main__":
    main()
