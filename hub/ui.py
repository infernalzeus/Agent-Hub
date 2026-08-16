"""Frontend: menu page, offline page, service worker, favicons + routing."""
from __future__ import annotations

import base64
import json

from aiohttp import web

from .config import APPS, SHORTCUTS, HERE

routes = web.RouteTableDef()


def _build_favicon_svg() -> str:
    """Self-contained circular favicon.

    The raster is inlined as a data: URI rather than referenced via
    `<image href="/favicon.png">`: browsers render SVG favicons in a sandbox
    that does NOT fetch external resources, so an external href silently fails
    and the tab shows no icon at all. A small 64x64 embedded PNG keeps the SVG
    tiny (the source favicon.png is multi-MB).
    """
    small = HERE / "favicon-64.png"
    full = HERE / "favicon.png"
    data = (small.read_bytes() if small.exists()
            else full.read_bytes() if full.exists() else b"")
    b64 = base64.b64encode(data).decode("ascii")
    return (
        '<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">'
        '<defs><clipPath id="c"><circle cx="32" cy="32" r="32"/></clipPath></defs>'
        f'<image href="data:image/png;base64,{b64}" x="0" y="0" width="64" height="64" '
        'clip-path="url(#c)" preserveAspectRatio="xMidYMid meet"/>'
        '</svg>'
    )


_FAVICON_SVG = _build_favicon_svg()

# ── Offline fallback (served by the service worker when Hub is unreachable) ───

_OFFLINE_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#080c28">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>AGENT HUB — Dormant</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600&family=Orbitron:wght@400;700;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --accent:#00e676;
  --text:rgba(0,230,118,0.90);--text-muted:rgba(0,230,118,0.52);--text-faint:rgba(0,230,118,0.30);
}
html{height:100%;min-height:100dvh;background:linear-gradient(150deg,#080c28 0%,#0d1050 45%,#18095c 100%) fixed}
html,body{min-height:100%;min-height:100dvh;font-family:'Outfit',system-ui,sans-serif;color:var(--text);
  display:flex;align-items:center;justify-content:center;
  padding:env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left)}
.wrap{text-align:center;padding:20px}
/* clip-path forces a true circle (radius < half-width) so NO square edge — top,
   bottom, or corners — can ever show. The soft mask feathers the rim within it. */
.hero-icon{width:220px;height:220px;object-fit:cover;mix-blend-mode:screen;opacity:.97;margin:0 auto 26px;display:block;
  clip-path:circle(47% at 50% 50%);
  -webkit-mask-image:radial-gradient(circle at 50% 50%,#000 86px,transparent 103px);
  mask-image:radial-gradient(circle at 50% 50%,#000 86px,transparent 103px)}
.brand{font-family:'Orbitron',monospace;font-size:22px;font-weight:900;color:var(--accent);
  letter-spacing:6px;text-shadow:0 0 20px rgba(0,230,118,.4)}
.status{font-family:'Orbitron',monospace;font-size:12px;letter-spacing:3px;color:var(--text-faint);margin-top:12px}
.hint{font-size:12.5px;color:var(--text-muted);margin-top:22px;max-width:280px;margin-left:auto;margin-right:auto;line-height:1.55}
.wake-btn{margin-top:26px;font-family:'Orbitron',monospace;font-size:14px;font-weight:700;letter-spacing:2px;
  padding:15px 40px;border-radius:12px;cursor:pointer;color:#04140b;
  background:linear-gradient(180deg,#00ff8f 0%,#00c766 100%);
  border:1px solid rgba(255,255,255,.35);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.55),0 4px 18px rgba(0,230,118,.45);
  transition:transform .15s,box-shadow .2s,opacity .2s}
.wake-btn:hover{transform:translateY(-1px);box-shadow:inset 0 1px 0 rgba(255,255,255,.65),0 6px 24px rgba(0,230,118,.6)}
.wake-btn:active{transform:scale(.97)}
.wake-btn:disabled{opacity:.6;cursor:default}
/* External (non-PC) devices can't start a stopped hub — greyed button, green
   text, no glow, not actionable. Placed after :disabled so it wins on opacity. */
.wake-btn.external{opacity:1;cursor:default;transform:none;color:var(--accent);
  background:linear-gradient(180deg,#3a3f4b 0%,#2a2e39 100%);
  border:1px solid rgba(0,230,118,.28);box-shadow:none}
.wake-btn.external:hover{transform:none;box-shadow:none}
.wake-sub{display:none;margin-top:14px;font-family:'Orbitron',monospace;font-size:11px;letter-spacing:1.5px;
  color:var(--text-muted);line-height:1.6;max-width:280px;margin-left:auto;margin-right:auto}
</style>
</head>
<body>
<div class="wrap">
  <img class="hero-icon" src="/favicon.png" alt="Agent Hub">
  <div class="brand">AGENT HUB</div>
  <div class="status">DORMANT</div>
  <button type="button" id="wake-btn" class="wake-btn">▶ START</button>
  <div class="wake-sub" id="wake-sub">Agent Hub is dormant. Initiate from PC.</div>
</div>
<script>
async function isUp() {
  try {
    const res = await fetch('/api/status', {cache: 'no-store', signal: AbortSignal.timeout(3000)});
    return res.ok;
  } catch (err) { return false; }
}
async function checkOnline() { if (await isUp()) window.location.reload(); }
setInterval(checkOnline, 5000);

// Trigger a custom URL protocol via a hidden iframe — if a handler is registered
// (on the PC) Windows runs it; if not (e.g. on the phone) it fails SILENTLY with
// no "cannot open page" error.
function triggerProtocol(url) {
  try {
    const f = document.createElement('iframe');
    f.style.display = 'none';
    f.src = url;
    document.body.appendChild(f);
    setTimeout(() => f.remove(), 1500);
  } catch (e) {}
}

const wakeBtn = document.getElementById('wake-btn');
const wakeSub = document.getElementById('wake-sub');

// Only the PC can start a stopped hub (the agenthub:// protocol is registered
// there). The address can't tell us the device — PC and phone both load the same
// tailnet URL — so detect the platform.
function isWindows() {
  const uad = navigator.userAgentData;
  if (uad && uad.platform) return uad.platform === 'Windows';
  return /Windows/i.test(navigator.userAgent);
}

if (isWindows()) {
  // PC: green, functional START.
  wakeBtn.onclick = async () => {
    wakeBtn.textContent = 'STARTING…';
    wakeBtn.disabled = true;
    // Hand Windows the agenthub:// link → it runs the launcher (.vbs) in
    // server-only mode and this same window reconnects. (Register it once with
    // register-agenthub-protocol.reg.)
    triggerProtocol('agenthub://start');
    let n = 0;
    const t = setInterval(async () => {
      n += 1;
      if (await isUp()) { clearInterval(t); window.location.reload(); return; }
      if (n > 30) { clearInterval(t); wakeBtn.textContent = '▶ START'; wakeBtn.disabled = false; }
    }, 2000);
  };
} else {
  // External device: START can't wake the PC from here. Grey it out (green text),
  // no action, and explain. The page still auto-reconnects once the hub is up.
  wakeBtn.classList.add('external');
  wakeBtn.disabled = true;
  wakeSub.style.display = 'block';
}
</script>
</body>
</html>
"""

_SW_JS = """\
const CACHE_NAME = 'agent-hub-offline-v7';
const OFFLINE_URL = '/offline.html';
const PRECACHE = [OFFLINE_URL, '/favicon.png', '/favicon-256.png', '/favicon.svg'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  event.respondWith(
    fetch(event.request).then((response) => {
      // tailscale serve stays up even when Agent Hub itself is down, so a dead
      // backend shows up as a real HTTP response (502/503/504), not a network
      // error — .catch() alone never sees it. Applies to every request, not
      // just the page navigation — an <img> asset gets the same bad-gateway
      // response and needs the same cache fallback, or it shows as broken.
      if (response.ok) return response;
      return caches.match(event.request).then((cached) => {
        if (cached) return cached;
        if (event.request.mode === 'navigate') return caches.match(OFFLINE_URL);
        return response;
      });
    }).catch(() =>
      caches.match(event.request).then((cached) => {
        if (cached) return cached;
        if (event.request.mode === 'navigate') return caches.match(OFFLINE_URL);
        return new Response('', {status: 504, statusText: 'Agent Hub unreachable'});
      })
    )
  );
});
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
<title>AGENT HUB</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="icon" type="image/png" sizes="64x64" href="/favicon-64.png">
<link rel="icon" type="image/png" sizes="256x256" href="/favicon-256.png">
<link rel="apple-touch-icon" href="/favicon-256.png">
<link rel="manifest" href="/manifest.webmanifest">
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600&family=Orbitron:wght@400;700;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#080c28;--bg-mid:#0d1050;--bg-deep:#18095c;
  --panel:rgba(8,12,40,0.88);
  --border-dim:rgba(0,230,118,0.22);--border-bright:rgba(0,230,118,0.55);
  --accent:#00e676;
  --text:rgba(0,230,118,0.90);--text-muted:rgba(0,230,118,0.52);--text-faint:rgba(0,230,118,0.22);
}
/* Gradient lives on <html> as a viewport-fixed fill so it covers the WHOLE
   screen on tablet/desktop. The 520px content column (body) is transparent, so
   there's no visible panel edge/seam around it. */
html{min-height:100dvh;background:linear-gradient(150deg,#080c28 0%,#0d1050 45%,#18095c 100%) fixed}
html,body{min-height:100%;min-height:100dvh;font-family:'Outfit',system-ui,sans-serif;color:var(--text)}
body{max-width:520px;margin:0 auto;background:transparent;
  padding:env(safe-area-inset-top) env(safe-area-inset-right) calc(104px + env(safe-area-inset-bottom)) env(safe-area-inset-left)}
header{display:flex;align-items:center;gap:14px;padding:22px 20px 24px;border-bottom:1px solid var(--border-dim)}
.conn-indicator{margin-left:auto;display:flex;align-items:center;gap:6px}
.conn-label{font-family:'Orbitron',monospace;font-size:9px;letter-spacing:1.5px;color:var(--text-faint);transition:color .3s}
.conn-label.live{color:var(--accent)}
.conn-label.down{color:#ff5c5c}
#conn-dot{width:7px;height:7px;border-radius:50%;background:#c0392b;transition:background .3s,box-shadow .3s;flex-shrink:0}
#conn-dot.live{background:var(--accent);box-shadow:0 0 8px var(--accent)}
.header-shortcuts{display:flex;gap:8px}
#setup-banner:empty{display:none}
.setup-issue{margin:14px 20px 0;padding:12px 14px;border-radius:10px;font-size:12.5px;line-height:1.5;
  border:1px solid;cursor:default}
.setup-issue.info{background:rgba(0,230,118,.06);border-color:var(--border-dim);color:var(--text-muted)}
.setup-issue.warn{background:rgba(245,200,66,.08);border-color:rgba(245,200,66,.4);color:#f5c842}
.setup-issue b{color:var(--text);font-weight:600}
.setup-issue .detail{display:block;margin-top:3px;color:var(--text-muted);font-size:11.5px}
.shortcut-btn{width:38px;height:38px;border-radius:8px;border:1px solid var(--border-bright);
  background:transparent;display:flex;align-items:center;justify-content:center;font-size:18px;
  cursor:pointer;text-decoration:none;transition:all .15s;flex-shrink:0}
.shortcut-btn:hover{background:rgba(0,230,118,.1);box-shadow:0 0 10px rgba(0,230,118,.18)}
/* Header buttons (⟳ restart / ✕ shutdown): ELECTRIC-BLUE metal with a soft CONIC
   spun sheen (rotational lustre, no lines). Coloured glow ONLY while active
   (hover / press / .working); resting = plain spun-blue metal. Icons are SVG
   (centred, crisp). */
.restart-btn,.shutdown-btn{width:40px;height:40px;border-radius:12px;
  display:flex;align-items:center;justify-content:center;flex-shrink:0;cursor:pointer;
  background:
    conic-gradient(from 218deg at 50% 50%,rgba(150,175,255,.12),rgba(0,0,0,.10) 25%,rgba(140,165,255,.09) 50%,rgba(0,0,0,.10) 75%,rgba(150,175,255,.12) 100%),
    linear-gradient(180deg,#1a2170 0%,#0d1050 46%,#0a0c3e 54%,#160b54 100%);
  border:1px solid rgba(110,140,235,.32);
  box-shadow:inset 0 1px 0 rgba(140,165,255,.40),inset 0 -1px 2px rgba(0,0,0,.42),0 2px 6px rgba(0,0,0,.5);
  transition:transform .15s ease,box-shadow .2s ease}
.restart-btn svg,.shutdown-btn svg{width:20px;height:20px;display:block;fill:none;
  stroke-width:2.2;stroke-linecap:round;stroke-linejoin:round;transition:filter .2s ease}
.restart-btn{--g:rgba(0,230,118,.85)}
.restart-btn svg{stroke:var(--accent)}
.shutdown-btn{--g:rgba(255,92,92,.85)}
.shutdown-btn svg{stroke:#ff6b6b}
.restart-btn:hover,.shutdown-btn:hover,.restart-btn:active,.shutdown-btn:active,
.restart-btn.working,.shutdown-btn.working{
  box-shadow:inset 0 1px 0 rgba(210,225,255,.5),inset 0 -1px 2px rgba(0,0,0,.4),
    0 2px 6px rgba(0,0,0,.5),0 0 16px var(--g)}
.restart-btn:hover svg,.shutdown-btn:hover svg,.restart-btn:active svg,.shutdown-btn:active svg,
.restart-btn.working svg,.shutdown-btn.working svg{filter:drop-shadow(0 0 5px var(--g))}
.restart-btn:active,.shutdown-btn:active{transform:scale(.95)}
.restart-btn.working,.shutdown-btn.working{animation:btnPulse 1s ease-in-out infinite}
@keyframes btnPulse{
  0%,100%{box-shadow:inset 0 1px 0 rgba(210,225,255,.5),inset 0 -1px 2px rgba(0,0,0,.4),0 2px 6px rgba(0,0,0,.5),0 0 8px var(--g)}
  50%{box-shadow:inset 0 1px 0 rgba(210,225,255,.5),inset 0 -1px 2px rgba(0,0,0,.4),0 2px 6px rgba(0,0,0,.5),0 0 24px var(--g)}}
.restart-btn:disabled,.shutdown-btn:disabled{cursor:default}
.card-emoji svg{display:block}

/* ── PC power control (center-bottom) ────────────────────────────────────── */
.power-wrap{position:fixed;left:50%;bottom:calc(16px + env(safe-area-inset-bottom));
  transform:translateX(-50%);z-index:60;display:flex;flex-direction:column;align-items:center;gap:12px}
.power-btn{width:66px;height:66px;border-radius:50%;display:flex;align-items:center;justify-content:center;cursor:pointer;
  background:
    conic-gradient(from 218deg at 50% 50%,rgba(150,175,255,.12),rgba(0,0,0,.10) 25%,rgba(140,165,255,.09) 50%,rgba(0,0,0,.10) 75%,rgba(150,175,255,.12) 100%),
    linear-gradient(180deg,#1a2170 0%,#0d1050 46%,#0a0c3e 54%,#160b54 100%);
  border:1px solid rgba(110,140,235,.32);
  box-shadow:inset 0 1px 0 rgba(140,165,255,.40),inset 0 -1px 2px rgba(0,0,0,.42),0 4px 20px rgba(0,0,0,.5);
  transition:transform .15s,box-shadow .2s}
.power-btn svg{width:44px;height:44px;filter:drop-shadow(0 0 6px rgba(0,208,192,.55))}
.power-btn:hover{transform:scale(1.06);
  box-shadow:inset 0 1px 0 rgba(140,165,255,.40),inset 0 -1px 2px rgba(0,0,0,.42),0 6px 26px rgba(0,0,0,.5),0 0 20px rgba(0,208,192,.35)}
.power-btn:active{transform:scale(.95)}
.power-menu{display:flex;flex-direction:column;gap:8px;width:196px;opacity:0;pointer-events:none;
  transform:translateY(10px);transition:opacity .18s,transform .18s}
.power-menu.open{opacity:1;pointer-events:auto;transform:translateY(0)}
.power-scrim{position:fixed;inset:0;z-index:55;background:rgba(4,6,20,.5);
  -webkit-backdrop-filter:blur(2px);backdrop-filter:blur(2px);
  opacity:0;pointer-events:none;transition:opacity .2s}
.power-scrim.show{opacity:1;pointer-events:auto}
.power-item{font-family:'Orbitron',monospace;font-size:11px;letter-spacing:1.5px;padding:12px 14px;border-radius:10px;
  border:1.5px solid #00e676;background:rgba(8,12,40,.92);color:#00e676;cursor:pointer;
  text-align:center;transition:all .15s;box-shadow:0 0 12px rgba(0,230,118,.35)}
.power-item:hover{background:rgba(0,230,118,.14);box-shadow:0 0 18px rgba(0,230,118,.6)}
.power-item.sleep{border-color:#22d3ee;color:#22d3ee;box-shadow:0 0 12px rgba(34,211,238,.4)}
.power-item.sleep:hover{background:rgba(34,211,238,.14);box-shadow:0 0 18px rgba(34,211,238,.65)}
.power-item.warn{border-color:#ffc147;color:#ffc147;box-shadow:0 0 12px rgba(255,193,71,.4)}
.power-item.warn:hover{background:rgba(255,193,71,.14);box-shadow:0 0 18px rgba(255,193,71,.65)}
.power-item.danger{border-color:#ff5c5c;color:#ff5c5c;box-shadow:0 0 12px rgba(255,92,92,.42)}
.power-item.danger:hover{background:rgba(255,92,92,.14);box-shadow:0 0 18px rgba(255,92,92,.65)}
.power-overlay{position:fixed;inset:0;z-index:100;display:none;align-items:center;justify-content:center;
  background:rgba(4,6,20,.82);-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px);padding:24px}
.power-overlay.show{display:flex}
.power-card{max-width:340px;width:100%;text-align:center;background:var(--panel);border:1px solid var(--border-bright);
  border-radius:16px;padding:28px 24px;box-shadow:0 10px 40px rgba(0,0,0,.5)}
.power-card h2{font-family:'Orbitron',monospace;font-size:14px;letter-spacing:2px;color:#ff8a8a;margin-bottom:4px}
.power-count{font-family:'Orbitron',monospace;font-size:60px;font-weight:900;color:var(--text);line-height:1;margin:10px 0 4px}
.power-sub{font-size:12.5px;color:var(--text-muted);margin-bottom:22px}
.power-abort{width:100%;font-family:'Orbitron',monospace;font-size:13px;letter-spacing:2px;padding:14px;
  border-radius:10px;border:1px solid var(--accent);background:rgba(0,230,118,.12);color:var(--accent);
  cursor:pointer;transition:all .15s}
.power-abort:hover{background:rgba(0,230,118,.2);box-shadow:0 0 16px rgba(0,230,118,.3)}
.brand-icon{width:40px;height:40px;flex-shrink:0;object-fit:cover;mix-blend-mode:screen;opacity:.97;
  clip-path:circle(47% at 50% 50%);
  -webkit-mask-image:radial-gradient(circle at 50% 50%,#000 15px,transparent 18px);
  mask-image:radial-gradient(circle at 50% 50%,#000 15px,transparent 18px)}
.brand{font-family:'Orbitron',monospace;font-size:15px;font-weight:900;color:var(--accent);
  letter-spacing:4px;text-shadow:0 0 20px rgba(0,230,118,.4)}
.sub{font-size:11px;color:var(--text-faint);letter-spacing:.5px;margin-top:2px}
#apps{padding:18px 16px}
.card{display:flex;align-items:center;gap:14px;background:var(--panel);border:1px solid var(--border-dim);
  border-radius:10px;padding:16px;margin-bottom:12px;transition:border-color .15s}
.card:hover{border-color:var(--border-bright)}
.card-emoji{font-size:26px;flex-shrink:0}
.card-body{flex:1;min-width:0}
.card-name{font-size:14.5px;font-weight:600;color:var(--text)}
.card-status{font-family:'Orbitron',monospace;font-size:8.5px;letter-spacing:1px;margin-top:3px;
  display:flex;align-items:center;gap:5px}
.status-dot{width:6px;height:6px;border-radius:50%;background:var(--text-faint)}
.status-dot.running{background:var(--accent);box-shadow:0 0 6px var(--accent)}
.card-actions{display:flex;gap:8px;flex-shrink:0}
.btn{font-family:'Orbitron',monospace;font-size:9px;letter-spacing:1px;padding:8px 14px;border-radius:6px;
  border:1px solid var(--border-bright);background:transparent;color:var(--accent);cursor:pointer;
  transition:all .15s;white-space:nowrap}
.btn:hover:not(:disabled){background:rgba(0,230,118,.1);box-shadow:0 0 10px rgba(0,230,118,.18)}
.btn:disabled{opacity:.4;cursor:not-allowed}
.btn.stop{border-color:rgba(255,92,92,.4);color:#ff5c5c}
.btn.stop:hover:not(:disabled){background:rgba(255,92,92,.08)}
.oc-btn{font-family:'Orbitron',monospace;font-size:8.5px;letter-spacing:1px;padding:6px 11px;border-radius:6px;
  border:1px solid var(--border-bright);background:transparent;color:var(--accent);cursor:pointer;transition:all .15s;
  white-space:nowrap;text-decoration:none;display:inline-flex;align-items:center;line-height:1}
.oc-btn:hover:not(.disabled){background:rgba(0,230,118,.1);box-shadow:0 0 10px rgba(0,230,118,.18)}
.oc-btn.stop{border-color:rgba(255,92,92,.5);color:#ff5c5c}
.oc-btn.stop:hover{background:rgba(255,92,92,.1);box-shadow:0 0 10px rgba(255,92,92,.2)}
.oc-btn.disabled{opacity:.35;cursor:not-allowed;pointer-events:none}
#empty{padding:40px 20px;text-align:center;color:var(--text-faint);font-size:12.5px}

.yt-card{background:var(--panel);border:1px solid var(--border-dim);border-radius:10px;
  margin-bottom:12px;overflow:hidden;transition:border-color .15s}
.yt-card:hover{border-color:var(--border-bright)}
.yt-header{display:flex;align-items:center;gap:14px;padding:16px;cursor:pointer}
.yt-expanded{display:none;padding:0 16px 16px;border-top:1px solid var(--border-dim)}
.yt-expanded.open{display:block}
.yt-section{margin-top:14px}
.yt-section label{display:block;font-family:'Orbitron',monospace;font-size:8.5px;letter-spacing:1px;
  color:var(--text-faint);margin-bottom:6px}
.yt-section select,.yt-section input[type=text],.yt-section textarea{
  width:100%;background:var(--bg);border:1px solid var(--border-dim);border-radius:6px;
  color:var(--text);padding:9px 10px;font-size:13px;font-family:'Outfit',inherit;outline:none}
.yt-section select:focus,.yt-section input:focus,.yt-section textarea:focus{border-color:var(--accent)}
.yt-section textarea{min-height:70px;resize:vertical}
.yt-sources{max-height:220px;overflow-y:auto;border:1px solid var(--border-dim);border-radius:6px}
.yt-source-row{display:flex;align-items:center;gap:10px;padding:10px;cursor:pointer;
  border-bottom:1px solid var(--border-dim);transition:background .1s}
.yt-source-row:last-child{border-bottom:none}
.yt-source-row:hover{background:rgba(0,230,118,.05)}
.yt-source-row.selected{background:rgba(0,230,118,.1)}
.yt-source-thumb{width:44px;height:44px;border-radius:5px;object-fit:cover;flex-shrink:0;background:#000}
.yt-source-thumb.yt-no-thumb{display:flex;align-items:center;justify-content:center;font-size:18px}
.yt-source-info{flex:1;min-width:0}
.yt-source-title{font-size:12.5px;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.yt-source-meta{font-size:10.5px;color:var(--text-faint);margin-top:2px}
.yt-thumb-preview{width:100%;max-width:200px;border-radius:8px;display:block;margin:0 auto 8px}
.yt-progress-bar{height:6px;border-radius:3px;background:var(--border-dim);overflow:hidden;margin-top:8px}
.yt-progress-fill{height:100%;background:var(--accent);width:0%;transition:width .3s}
.yt-progress-text{font-family:'Orbitron',monospace;font-size:10px;color:var(--text-muted);margin-top:6px;text-align:center}
.yt-result{margin-top:12px;font-size:12.5px;text-align:center}
.yt-result a{color:var(--accent)}
.yt-manual-btn{margin-top:8px}
</style>
</head>
<body>

<header>
  <img class="brand-icon" src="/favicon.png" alt="Agent Hub">
  <div>
    <div class="brand">AGENT HUB</div>
  </div>
  <div class="conn-indicator">
    <span class="conn-label" id="conn-label">CONNECTING</span>
    <div id="conn-dot"></div>
  </div>
  <div class="header-shortcuts" id="header-shortcuts"></div>
  <button type="button" class="restart-btn" id="restart-btn" title="Restart Agent Hub" aria-label="Restart Agent Hub">
    <svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-2.6-6.36"/><path d="M21 4v5h-5"/></svg>
  </button>
  <button type="button" class="shutdown-btn" id="shutdown-btn" title="Turn off Agent Hub" aria-label="Turn off Agent Hub">
    <svg viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></svg>
  </button>
</header>

<div id="setup-banner"></div>

<div id="apps-before"></div>

<div id="yt-app-area">
<div class="yt-card">
  <div class="yt-header" id="yt-header">
    <div class="card-emoji">📺</div>
    <div class="card-body">
      <div class="card-name">YouTube Upload</div>
      <div class="card-status" id="yt-status-line"><span class="status-dot"></span>IDLE</div>
    </div>
    <div class="card-actions">
      <button type="button" class="btn" id="yt-toggle-btn">EXPAND</button>
    </div>
  </div>
  <div class="yt-expanded" id="yt-expanded">

    <div class="yt-section">
      <label>Account</label>
      <select id="yt-account"></select>
    </div>

    <div class="yt-section">
      <label>Source (Movie Clipper output)</label>
      <div class="yt-sources" id="yt-sources"></div>
      <button type="button" class="mini-btn yt-manual-btn" id="yt-manual-btn">+ Enter path manually</button>
    </div>

    <div class="yt-section" id="yt-manual-wrap" style="display:none">
      <label>Video path</label>
      <input type="text" id="yt-manual-path" placeholder="N:/path/to/video.mp4">
    </div>

    <div id="yt-details" style="display:none">
      <img class="yt-thumb-preview" id="yt-thumb-preview" style="display:none">
      <div class="yt-section">
        <label>Title</label>
        <input type="text" id="yt-title">
      </div>
      <div class="yt-section">
        <label>Description</label>
        <textarea id="yt-description"></textarea>
      </div>
      <div class="yt-section">
        <label>Tags (comma separated)</label>
        <input type="text" id="yt-tags">
      </div>
      <div class="yt-section">
        <label>Privacy</label>
        <select id="yt-privacy">
          <option value="private">Private</option>
          <option value="unlisted" selected>Unlisted</option>
          <option value="public">Public</option>
        </select>
      </div>
      <button type="button" class="btn" id="yt-upload-btn" style="width:100%;margin-top:14px">UPLOAD</button>
    </div>

    <div id="yt-progress-wrap" style="display:none">
      <div class="yt-progress-bar"><div class="yt-progress-fill" id="yt-progress-fill"></div></div>
      <div class="yt-progress-text" id="yt-progress-text">0%</div>
    </div>

    <div class="yt-result" id="yt-result" style="display:none"></div>

  </div>
</div>
</div>

<div id="ytdl-app-area">
<div class="yt-card">
  <div class="yt-header" id="ytdl-header">
    <div class="card-emoji">⬇️</div>
    <div class="card-body">
      <div class="card-name">YouTube Download</div>
      <div class="card-status" id="ytdl-status-line"><span class="status-dot"></span>IDLE</div>
    </div>
    <div class="card-actions">
      <button type="button" class="btn" id="ytdl-toggle-btn">EXPAND</button>
    </div>
  </div>
  <div class="yt-expanded" id="ytdl-expanded">

    <div class="yt-section">
      <label>YouTube URL</label>
      <input type="text" id="ytdl-url" placeholder="https://youtube.com/watch?v=...">
    </div>

    <div class="yt-section">
      <label>Format</label>
      <select id="ytdl-format">
        <option value="video" selected>🎬 Video (1080p MP4)</option>
        <option value="audio">🎵 Audio (MP3 320k)</option>
      </select>
    </div>

    <button type="button" class="btn" id="ytdl-download-btn" style="width:100%;margin-top:14px">DOWNLOAD</button>

    <div id="ytdl-progress-wrap" style="display:none">
      <div class="yt-progress-bar"><div class="yt-progress-fill" id="ytdl-progress-fill"></div></div>
      <div class="yt-progress-text" id="ytdl-progress-text">0%</div>
    </div>

    <div class="yt-result" id="ytdl-result" style="display:none"></div>

  </div>
</div>
</div>

<div id="apps-after"></div>

<div id="opencode-app-area">
<div class="yt-card">
  <div class="yt-header" id="oc-header">
    <div class="card-emoji" aria-hidden="true">
      <svg viewBox="0 0 24 24" width="27" height="27" fill="none" stroke-width="2"
           stroke-linecap="round" stroke-linejoin="round">
        <defs><linearGradient id="brainGrad" x1="2" y1="3" x2="22" y2="21" gradientUnits="userSpaceOnUse">
          <stop offset="0" stop-color="#3ba7ff"/><stop offset="1" stop-color="#ffcf47"/>
        </linearGradient></defs>
        <g stroke="url(#brainGrad)">
          <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/>
          <path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/>
          <path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"/>
          <path d="M17.599 6.5a3 3 0 0 0 .399-1.375"/>
          <path d="M6.003 5.125A3 3 0 0 0 6.401 6.5"/>
          <path d="M3.477 10.896a4 4 0 0 1 .585-.396"/>
          <path d="M19.938 10.5a4 4 0 0 1 .585.396"/>
          <path d="M6 18a4 4 0 0 1-1.967-.516"/>
          <path d="M19.967 17.484A4 4 0 0 1 18 18"/>
        </g>
      </svg>
    </div>
    <div class="card-body">
      <div class="card-name">OpenCode</div>
      <div class="card-status" id="oc-status-line"><span class="status-dot"></span>0 SESSIONS</div>
    </div>
    <div class="card-actions">
      <button type="button" class="btn" id="oc-graph-btn" title="Project status graph">GRAPH</button>
      <button type="button" class="btn" id="oc-toggle-btn">EXPAND</button>
    </div>
  </div>
  <div class="yt-expanded" id="oc-expanded">

    <div class="yt-section">
      <label>Folder to work on</label>
      <input type="text" id="oc-source" placeholder="N:\\Code\\...\\your-repo">
    </div>
    <div class="yt-section">
      <label>Session name (optional)</label>
      <input type="text" id="oc-name" placeholder="defaults to folder name">
    </div>
    <button type="button" class="btn" id="oc-create-btn" style="width:100%">+ NEW SESSION</button>

    <div class="yt-section" style="margin-top:16px">
      <label>Resume a previous folder (no copy)</label>
      <div style="display:flex;gap:8px;align-items:center">
        <select id="oc-folders" style="flex:1;min-width:0"></select>
        <button type="button" class="oc-btn" id="oc-resume-btn">RESUME</button>
      </div>
    </div>

    <div class="yt-result" id="oc-auth" style="display:none;margin-top:12px"></div>
    <div id="oc-session-list" style="margin-top:14px"></div>

  </div>
</div>
</div>

<div class="power-scrim" id="power-scrim"></div>
<div class="power-wrap" id="power-wrap">
  <div class="power-menu" id="power-menu">
    <button type="button" class="power-item" data-action="lock">🔒 LOCK</button>
    <button type="button" class="power-item sleep" data-action="sleep">🌙 SLEEP</button>
    <button type="button" class="power-item warn" data-action="restart">↻ RESTART</button>
    <button type="button" class="power-item danger" data-action="shutdown">⏻ SHUT DOWN</button>
  </div>
  <button type="button" class="power-btn" id="power-btn" title="Power" aria-label="Power menu">
    <svg viewBox="0 0 32 32" fill="none" stroke-linecap="round" stroke-linejoin="round">
      <defs><linearGradient id="pwrGrad" x1="4" y1="4" x2="28" y2="28" gradientUnits="userSpaceOnUse">
        <stop offset="0" stop-color="#00e676"/><stop offset=".5" stop-color="#00d0c0"/><stop offset="1" stop-color="#2b9bff"/>
      </linearGradient></defs>
      <circle cx="16" cy="16" r="14.2" stroke="url(#pwrGrad)" stroke-width="2"/>
      <g stroke="url(#pwrGrad)" stroke-width="3.4" transform="translate(9.5,9.5) scale(0.54)">
        <path d="M12 2v10"/>
        <path d="M18.4 6.6a9 9 0 1 1-12.77.04"/>
      </g>
    </svg>
  </button>
</div>

<div class="power-overlay" id="power-overlay">
  <div class="power-card">
    <h2 id="power-title">⚠ PC SHUTTING DOWN</h2>
    <div class="power-count" id="power-count">30</div>
    <div class="power-sub">Tap abort to cancel.</div>
    <button type="button" class="power-abort" id="power-abort">ABORT</button>
  </div>
</div>

<script>
const APPS = __APPS_JSON__;
const SHORTCUTS = __SHORTCUTS_JSON__;
const appsBefore = document.getElementById('apps-before');
const appsAfter  = document.getElementById('apps-after');
const ytAppArea   = document.getElementById('yt-app-area');
const ytdlAppArea = document.getElementById('ytdl-app-area');
const ocAppArea   = document.getElementById('opencode-app-area');
const powerWrap   = document.getElementById('power-wrap');
let downCount = 0;   // consecutive failed status polls → surface the dormant page
const shortcutsEl = document.getElementById('header-shortcuts');

// SMB (and any other static shortcut) now lives inside its app's card, not the
// header — the header's top-right is the power/shutdown control.
const SMB_SHORTCUT = SHORTCUTS.find(s => s.name === 'SMB') || null;

// Turn Agent Hub off from the header X. Tailscale serve stays up when the
// backend dies, so after shutdown the service worker serves the dormant page —
// reloading a moment later lands there.
const shutdownBtn = document.getElementById('shutdown-btn');
shutdownBtn.onclick = async () => {
  if (!confirm('Turn off Agent Hub?\\n\\nRunning apps will be stopped and this page goes dormant until you start it again on the PC.')) return;
  shutdownBtn.disabled = true;
  shutdownBtn.classList.add('working');
  try { await fetch('/api/shutdown', {method: 'POST'}); } catch (e) {}
  setConn(false);
  document.title = 'AGENT HUB — Dormant';
  setTimeout(() => window.location.reload(), 1500);
};

// Restart from the header ⟳. The launcher's supervisor loop relaunches the
// server; we poll /api/status and reload this window as soon as it's back.
const restartBtn = document.getElementById('restart-btn');
restartBtn.onclick = async () => {
  if (!confirm('Restart Agent Hub?')) return;
  restartBtn.disabled = true;
  shutdownBtn.disabled = true;
  restartBtn.classList.add('working');
  try { await fetch('/api/restart', {method: 'POST'}); } catch (e) {}
  setConn(false);
  connLabel.textContent = 'RESTARTING';
  document.title = 'AGENT HUB — Restarting…';
  let tries = 0;
  const poll = setInterval(async () => {
    tries += 1;
    try {
      const r = await fetch('/api/status', {cache: 'no-store', signal: AbortSignal.timeout(2000)});
      if (r.ok) { clearInterval(poll); window.location.reload(); return; }
    } catch (e) {}
    if (tries > 40) { clearInterval(poll); connLabel.textContent = 'DISCONNECTED'; }  // ~60s give-up
  }, 1500);
};

async function openApp(id, name) {
  try {
    const res = await fetch(`/api/start/${id}`, {method: 'POST'});
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    window.location.href = data.base_path + '/';
  } catch (err) {
    alert(`Failed to start ${name}: ${err.message}`);
  }
}

function renderShortcuts() {
  shortcutsEl.innerHTML = '';
  for (const id of Object.keys(APPS)) {
    const info = APPS[id];
    if (!info.pinned) continue;
    const btn = document.createElement('button');
    btn.className = 'shortcut-btn';
    btn.title = info.name;
    btn.textContent = info.emoji;
    btn.onclick = () => openApp(id, info.name);
    shortcutsEl.appendChild(btn);
  }
}
renderShortcuts();

// Setup-prerequisite banner: detection only, never auto-installs anything —
// just says plainly what's missing instead of letting a card fail silently
// the first time you click it. Checked once on load, not polled.
async function loadSetupStatus() {
  const el = document.getElementById('setup-banner');
  try {
    const res = await fetch('/api/setup-status');
    const {issues} = await res.json();
    el.innerHTML = (issues || []).map(i => `
      <div class="setup-issue ${i.severity}">
        <b>${i.title}</b>
        <span class="detail">${i.detail}${i.readme_anchor ? ` — see README${i.readme_anchor}` : ''}</span>
      </div>`).join('');
  } catch (e) { /* setup status is non-critical — fail silent */ }
}
loadSetupStatus();

function render(status) {
  appsBefore.innerHTML = '';
  appsAfter.innerHTML = '';
  const ids = Object.keys(APPS);
  if (!ids.length) {
    appsBefore.innerHTML = '<div id="empty">No apps registered yet.</div>';
    return;
  }
  for (const id of ids) {
    // YouTube Upload's static card sits between the two — everything up to and
    // including movie-clipper renders before it, the rest render after.
    const container = id === 'movie-clipper' ? appsBefore : appsAfter;
    const info = APPS[id];
    const running = status[id] && status[id].running;

    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `
      <div class="card-emoji">${info.emoji}</div>
      <div class="card-body">
        <div class="card-name">${info.name}</div>
        <div class="card-status"><span class="status-dot ${running ? 'running' : ''}"></span>${running ? 'RUNNING' : 'IDLE'}</div>
      </div>
      <div class="card-actions"></div>
    `;
    const actions = card.querySelector('.card-actions');

    const openBtn = document.createElement('button');
    openBtn.className = 'btn';
    openBtn.textContent = running ? 'OPEN' : 'START';
    openBtn.onclick = async () => {
      openBtn.disabled = true;
      openBtn.textContent = running ? 'OPENING…' : 'STARTING…';
      try {
        const res = await fetch(`/api/start/${id}`, {method: 'POST'});
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        window.location.href = data.base_path + '/';
      } catch (err) {
        alert(`Failed to start ${info.name}: ${err.message}`);
        openBtn.disabled = false;
        openBtn.textContent = running ? 'OPEN' : 'START';
      }
    };
    actions.appendChild(openBtn);

    // File Browser also gets a direct SMB link — opens the N: drive in the OS Files app.
    // It's its own <a>, kept separate from OPEN so tapping one never triggers
    // the other.
    if (id === 'file-browser' && SMB_SHORTCUT) {
      const smbBtn = document.createElement('a');
      smbBtn.className = 'btn';
      smbBtn.textContent = SMB_SHORTCUT.emoji + ' SMB';
      smbBtn.href = SMB_SHORTCUT.href;
      smbBtn.title = SMB_SHORTCUT.title;
      actions.appendChild(smbBtn);
    }

    if (running) {
      const stopBtn = document.createElement('button');
      stopBtn.className = 'btn stop';
      stopBtn.textContent = 'STOP';
      stopBtn.onclick = async () => {
        stopBtn.disabled = true;
        await fetch(`/api/stop/${id}`, {method: 'POST'});
        refresh();
      };
      actions.appendChild(stopBtn);
    }

    container.appendChild(card);
  }
}

const connLabel = document.getElementById('conn-label');
const connDot   = document.getElementById('conn-dot');

function setConn(live) {
  connLabel.textContent = live ? 'LIVE' : 'DISCONNECTED';
  connLabel.classList.toggle('live', live);
  connLabel.classList.toggle('down', !live);
  connDot.classList.toggle('live', live);
}

async function refresh() {
  try {
    const res = await fetch('/api/status', {signal: AbortSignal.timeout(4000)});
    if (!res.ok) throw new Error('bad status');
    const status = await res.json();
    setConn(true);
    downCount = 0;
    ytAppArea.style.display = '';
    ytdlAppArea.style.display = '';
    ocAppArea.style.display = '';
    powerWrap.style.display = '';
    render(status);
  } catch (err) {
    setConn(false);
    ytAppArea.style.display = 'none';
    ytdlAppArea.style.display = 'none';
    ocAppArea.style.display = 'none';
    powerWrap.style.display = 'none';   // the power button can't work with the hub down
    appsBefore.innerHTML = '<div id="empty">Could not reach Agent Hub API.</div>';
    appsAfter.innerHTML = '';
    // Hub is down → flip to the DORMANT screen. Reloading lets the service worker
    // serve offline.html (it does when the backend errors). Wait for a couple of
    // failed polls so a brief blip doesn't reload, and rate-limit so a flapping
    // API can't loop.
    downCount += 1;
    const lastReload = +(sessionStorage.getItem('hubReloadAt') || 0);
    if (downCount >= 2 && Date.now() - lastReload > 20000) {
      sessionStorage.setItem('hubReloadAt', String(Date.now()));
      location.reload();
    }
  }
}

refresh();
setInterval(refresh, 5000);

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}

// ── YouTube Upload (expandable card, not a spawned app) ─────────────────────

const ytHeader     = document.getElementById('yt-header');
const ytToggleBtn  = document.getElementById('yt-toggle-btn');
const ytExpanded   = document.getElementById('yt-expanded');
const ytStatusLine = document.getElementById('yt-status-line');
const ytSourcesEl  = document.getElementById('yt-sources');
const ytManualBtn  = document.getElementById('yt-manual-btn');
const ytManualWrap = document.getElementById('yt-manual-wrap');
const ytManualPath = document.getElementById('yt-manual-path');
const ytDetails    = document.getElementById('yt-details');
const ytThumbImg   = document.getElementById('yt-thumb-preview');
const ytTitle      = document.getElementById('yt-title');
const ytDesc       = document.getElementById('yt-description');
const ytTags       = document.getElementById('yt-tags');
const ytPrivacy    = document.getElementById('yt-privacy');
const ytUploadBtn  = document.getElementById('yt-upload-btn');
const ytProgWrap   = document.getElementById('yt-progress-wrap');
const ytProgFill   = document.getElementById('yt-progress-fill');
const ytProgText   = document.getElementById('yt-progress-text');
const ytResultEl   = document.getElementById('yt-result');

let ytOpen = false;
let ytSelected = null;
// True only between starting an upload here and handling its completion. The
// server replays the last upload's 'done' event to every socket that connects
// (so a reloaded page can still see the result) — without this guard, merely
// EXPANDING the card would receive that stale 'done' and auto-collapse the card
// ~4s later, making it impossible to set up a new upload.
let ytUploadActive = false;

function ytSetStatus(text, running) {
  ytStatusLine.innerHTML = `<span class="status-dot ${running ? 'running' : ''}"></span>${text}`;
}

async function ytToggle() {
  if (ytOpen) { ytCollapse(); return; }
  ytOpen = true;
  ytExpanded.classList.add('open');
  ytToggleBtn.textContent = 'COLLAPSE';
  ytConnectWs();

  const [accounts, sources] = await Promise.all([
    fetch('/api/youtube/accounts').then(r => r.json()),
    fetch('/api/youtube/sources').then(r => r.json()),
  ]);

  const accSel = document.getElementById('yt-account');
  accSel.innerHTML = accounts.map(a => `<option value="${a}">${a}</option>`).join('');

  ytSourcesEl.innerHTML = '';
  if (!sources.length) {
    ytSourcesEl.innerHTML = '<div style="padding:14px;font-size:12px;color:var(--text-faint)">No finished Movie Clipper edits found.</div>';
  }
  for (const s of sources) {
    const row = document.createElement('div');
    row.className = 'yt-source-row';
    row.innerHTML = `
      ${s.has_thumbnail
        ? `<img class="yt-source-thumb" src="/api/youtube/thumbnail/${encodeURIComponent(s.id)}">`
        : `<div class="yt-source-thumb yt-no-thumb">🎬</div>`}
      <div class="yt-source-info">
        <div class="yt-source-title">${s.title}</div>
        <div class="yt-source-meta">${s.size_mb} MB · ${s.date}${s.has_thumbnail ? ' · has thumbnail' : ''}</div>
      </div>
    `;
    row.onclick = () => ytSelectSource(s, row);
    ytSourcesEl.appendChild(row);
  }
}

function ytSelectSource(s, rowEl) {
  ytSelected = {
    video_path: s.video_path,
    source_id: s.id,
  };
  document.querySelectorAll('.yt-source-row').forEach(r => r.classList.remove('selected'));
  if (rowEl) rowEl.classList.add('selected');
  ytManualWrap.style.display = 'none';

  ytTitle.value = s.title || '';
  ytDesc.value = s.description || '';
  ytTags.value = (s.tags || []).join(', ');

  if (s.has_thumbnail) {
    ytThumbImg.src = `/api/youtube/thumbnail/${encodeURIComponent(s.id)}`;
    ytThumbImg.style.display = 'block';
  } else {
    ytThumbImg.style.display = 'none';
  }
  ytDetails.style.display = 'block';
}

ytManualBtn.onclick = () => {
  ytManualWrap.style.display = 'block';
  document.querySelectorAll('.yt-source-row').forEach(r => r.classList.remove('selected'));
  ytSelected = {manual: true};
  ytThumbImg.style.display = 'none';
  ytTitle.value = '';
  ytDesc.value = '';
  ytTags.value = '';
  ytDetails.style.display = 'block';
};

ytUploadBtn.onclick = async () => {
  let videoPath = ytSelected && ytSelected.manual ? ytManualPath.value.trim() : (ytSelected && ytSelected.video_path);
  if (!videoPath) { alert('Pick a source or enter a path first.'); return; }
  if (!ytTitle.value.trim()) { alert('Title is required.'); return; }

  const payload = {
    account: document.getElementById('yt-account').value,
    video_path: videoPath,
    title: ytTitle.value.trim(),
    description: ytDesc.value,
    tags: ytTags.value,
    privacy: ytPrivacy.value,
    source_id: ytSelected && ytSelected.source_id ? ytSelected.source_id : null,
  };

  ytUploadBtn.disabled = true;
  ytDetails.style.display = 'none';
  ytProgWrap.style.display = 'block';
  ytResultEl.style.display = 'none';
  ytSetStatus('UPLOADING', true);

  try {
    const res = await fetch('/api/youtube/upload', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    ytUploadActive = true;
  } catch (err) {
    ytProgWrap.style.display = 'none';
    ytResultEl.style.display = 'block';
    ytResultEl.textContent = `Failed to start: ${err.message}`;
    ytUploadBtn.disabled = false;
    ytSetStatus('IDLE', false);
  }
};

function ytCollapse() {
  ytOpen = false;
  ytUploadActive = false;
  ytDisconnectWs();
  ytExpanded.classList.remove('open');
  ytDetails.style.display = 'none';
  ytManualWrap.style.display = 'none';
  ytProgWrap.style.display = 'none';
  ytResultEl.style.display = 'none';
  ytUploadBtn.disabled = false;
  ytSelected = null;
  ytToggleBtn.textContent = 'EXPAND';
  ytSetStatus('IDLE', false);
}

ytHeader.onclick = ytToggle;

const ytWsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
// The websocket lives only while the card is expanded — opened on EXPAND,
// closed on collapse (which auto-fires a few seconds after success). A
// persistent always-open socket would hold the server's graceful shutdown
// hostage for nothing. Progress made while collapsed isn't lost: the server
// replays all lines on connect.
let ytWs = null;
function ytConnectWs() {
  if (ytWs) return;
  const ws = new WebSocket(`${ytWsProto}//${location.host}/ws/youtube`);
  ytWs = ws;
  ws.onmessage = ev => {
    const d = JSON.parse(ev.data);
    if (d.type === 'line') {
      ytProgFill.style.width = d.progress + '%';
      ytProgText.textContent = d.progress + '%';
    } else if (d.type === 'done') {
      // Ignore a replayed 'done' from a prior upload (e.g. on card expand) —
      // only react to the completion of an upload started in this session.
      if (!ytUploadActive) return;
      ytUploadActive = false;
      ytProgWrap.style.display = 'none';
      ytResultEl.style.display = 'block';
      ytUploadBtn.disabled = false;
      if (d.ok && d.result && d.result.url) {
        ytResultEl.innerHTML = `✅ Uploaded — <a href="${d.result.url}" target="_blank">watch it</a>`;
        ytSetStatus('DONE', false);
        setTimeout(ytCollapse, 4000);
      } else {
        ytResultEl.textContent = '❌ Upload failed — check the account/credentials and try again.';
        ytSetStatus('FAILED', false);
      }
    }
  };
  ws.onclose = () => {
    if (ytWs !== ws) return;  // closed on purpose by ytDisconnectWs
    ytWs = null;
    if (ytOpen) setTimeout(() => { if (ytOpen) ytConnectWs(); }, 3000);
  };
}
function ytDisconnectWs() {
  const ws = ytWs;
  ytWs = null;
  if (ws) ws.close();
}

// ── YouTube Download (expandable card, same shape as Upload) ────────────────

const ytdlHeader     = document.getElementById('ytdl-header');
const ytdlToggleBtn  = document.getElementById('ytdl-toggle-btn');
const ytdlExpanded   = document.getElementById('ytdl-expanded');
const ytdlStatusLine = document.getElementById('ytdl-status-line');
const ytdlUrl        = document.getElementById('ytdl-url');
const ytdlFormat     = document.getElementById('ytdl-format');
const ytdlDownloadBtn = document.getElementById('ytdl-download-btn');
const ytdlProgWrap   = document.getElementById('ytdl-progress-wrap');
const ytdlProgFill   = document.getElementById('ytdl-progress-fill');
const ytdlProgText   = document.getElementById('ytdl-progress-text');
const ytdlResultEl   = document.getElementById('ytdl-result');

let ytdlOpen = false;
let ytdlActive = false;  // see ytUploadActive — guards against replayed 'done' on expand

function ytdlSetStatus(text, running) {
  ytdlStatusLine.innerHTML = `<span class="status-dot ${running ? 'running' : ''}"></span>${text}`;
}

function ytdlToggle() {
  if (ytdlOpen) { ytdlCollapse(); return; }
  ytdlOpen = true;
  ytdlExpanded.classList.add('open');
  ytdlToggleBtn.textContent = 'COLLAPSE';
  ytdlConnectWs();
}

function ytdlCollapse() {
  ytdlOpen = false;
  ytdlActive = false;
  ytdlDisconnectWs();
  ytdlExpanded.classList.remove('open');
  ytdlProgWrap.style.display = 'none';
  ytdlResultEl.style.display = 'none';
  ytdlDownloadBtn.disabled = false;
  ytdlToggleBtn.textContent = 'EXPAND';
  ytdlUrl.value = '';
  ytdlSetStatus('IDLE', false);
}

ytdlHeader.onclick = ytdlToggle;

ytdlDownloadBtn.onclick = async () => {
  const url = ytdlUrl.value.trim();
  if (!url) { alert('Paste a YouTube URL first.'); return; }

  const payload = {url, format: ytdlFormat.value};

  ytdlDownloadBtn.disabled = true;
  ytdlProgWrap.style.display = 'block';
  ytdlResultEl.style.display = 'none';
  ytdlProgFill.style.width = '0%';
  ytdlProgText.textContent = '0%';
  ytdlSetStatus('DOWNLOADING', true);

  try {
    const res = await fetch('/api/youtube-dl/download', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    ytdlActive = true;
  } catch (err) {
    ytdlProgWrap.style.display = 'none';
    ytdlResultEl.style.display = 'block';
    ytdlResultEl.textContent = `Failed to start: ${err.message}`;
    ytdlDownloadBtn.disabled = false;
    ytdlSetStatus('IDLE', false);
  }
};

// Same expand-only lifecycle as the upload card's socket.
let ytdlWs = null;
function ytdlConnectWs() {
  if (ytdlWs) return;
  const ws = new WebSocket(`${ytWsProto}//${location.host}/ws/youtube-dl`);
  ytdlWs = ws;
  ws.onmessage = ev => {
    const d = JSON.parse(ev.data);
    if (d.type === 'line') {
      ytdlProgFill.style.width = d.progress + '%';
      ytdlProgText.textContent = d.progress.toFixed(0) + '%';
    } else if (d.type === 'done') {
      if (!ytdlActive) return;  // ignore a replayed 'done' from a prior download
      ytdlActive = false;
      ytdlProgWrap.style.display = 'none';
      ytdlResultEl.style.display = 'block';
      ytdlDownloadBtn.disabled = false;
      if (d.ok) {
        ytdlResultEl.textContent = `✅ Saved: ${(d.result && d.result.saved_to) || 'done'}`;
        ytdlSetStatus('DONE', false);
        setTimeout(ytdlCollapse, 4000);
      } else {
        const why = d.result && d.result.error;
        ytdlResultEl.textContent = why ? ('❌ ' + why) : '❌ Download failed — check the URL and try again.';
        ytdlSetStatus('FAILED', false);
      }
    }
  };
  ws.onclose = () => {
    if (ytdlWs !== ws) return;  // closed on purpose by ytdlDisconnectWs
    ytdlWs = null;
    if (ytdlOpen) setTimeout(() => { if (ytdlOpen) ytdlConnectWs(); }, 3000);
  };
}
function ytdlDisconnectWs() {
  const ws = ytdlWs;
  ytdlWs = null;
  if (ws) ws.close();
}
</script>

<script>
// ── OpenCode (expandable card; multi-session, one per copied folder) ─────────
// No persistent hub websocket: the list is fetched on expand and after actions.
(function () {
  const header    = document.getElementById('oc-header');
  const toggleBtn = document.getElementById('oc-toggle-btn');
  const graphBtn  = document.getElementById('oc-graph-btn');
  const expanded  = document.getElementById('oc-expanded');
  const statusEl  = document.getElementById('oc-status-line');
  const authEl    = document.getElementById('oc-auth');
  const listEl    = document.getElementById('oc-session-list');
  const sourceEl  = document.getElementById('oc-source');
  const nameEl    = document.getElementById('oc-name');
  const createBtn = document.getElementById('oc-create-btn');
  const foldersEl = document.getElementById('oc-folders');
  const resumeBtn = document.getElementById('oc-resume-btn');
  let ocOpen = false;

  async function loadFolders() {
    let list;
    try { list = await (await fetch('/api/opencode/folders', {cache: 'no-store'})).json(); }
    catch (e) { return; }
    foldersEl.innerHTML = list.length
      ? list.map((f) => `<option value="${esc(f.folder)}">${esc(f.folder)}${f.active_session ? ' (running)' : ''}</option>`).join('')
      : '<option value="">— no previous folders —</option>';
  }

  resumeBtn.onclick = async () => {
    const folder = foldersEl.value;
    if (!folder) { alert('No previous folder to resume.'); return; }
    resumeBtn.disabled = true; resumeBtn.textContent = '…';
    try {
      const res = await fetch('/api/opencode/sessions/resume', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({folder}),
      });
      if (!res.ok) throw new Error(await res.text());
    } catch (e) { alert('Resume failed: ' + e.message); }
    resumeBtn.disabled = false; resumeBtn.textContent = 'RESUME';
    refresh();
  };

  // Decode percent-encoded paths on paste so the field shows the real path
  // immediately (no visible %5C / %20), whatever the clipboard handed over.
  sourceEl.addEventListener('input', () => {
    if (/%[0-9A-Fa-f]{2}/.test(sourceEl.value)) {
      try { sourceEl.value = decodeURIComponent(sourceEl.value); } catch (e) {}
    }
  });

  const esc = (s) => (s || '').replace(/[&<>"']/g, (c) =>
    ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

  function ocToggle() {
    ocOpen = !ocOpen;
    expanded.classList.toggle('open', ocOpen);
    toggleBtn.textContent = ocOpen ? 'COLLAPSE' : 'EXPAND';
    if (ocOpen) refresh();
  }
  header.onclick = ocToggle;   // EXPAND button sits inside the header and bubbles up

  // GRAPH also sits inside the header (bubbles to ocToggle) — stop that here
  // and open /graph in a new tab instead. New tab, not top-level navigation:
  // navigating the PWA's own top-level page away from / has stranded it before.
  graphBtn.onclick = (e) => { e.stopPropagation(); window.open('/graph', '_blank'); };

  async function refresh() {
    loadFolders();
    let data;
    try {
      data = await (await fetch('/api/opencode/sessions', {cache: 'no-store'})).json();
    } catch (e) {
      listEl.innerHTML = '<div class="yt-result">Could not reach the hub.</div>';
      return;
    }
    const rows = data.sessions || [];
    const live = rows.filter((r) => r.running).length;
    statusEl.innerHTML = `<span class="status-dot ${live ? 'running' : ''}"></span>${rows.length} SESSION(S)`;

    if (rows.length && data.auth) {
      authEl.style.display = 'block';
      authEl.innerHTML = `When the OpenCode tab asks to log in — user <b>${esc(data.auth.username)}</b> · pass <b>${esc(data.auth.password)}</b>`;
    } else {
      authEl.style.display = 'none';
    }

    if (!rows.length) {
      listEl.innerHTML = '<div style="opacity:.6;font-size:13px">No sessions yet. Give a folder above and hit NEW SESSION.</div>';
      return;
    }
    listEl.innerHTML = rows.map((s) => `
      <div style="display:flex;align-items:center;gap:8px;padding:10px 0;border-top:1px solid var(--border-dim)">
        <span class="status-dot ${s.running ? 'running' : ''}"></span>
        <div style="flex:1;min-width:0">
          <div style="font-weight:600">${esc(s.name)}</div>
          <div style="font-size:11px;opacity:.55;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(s.cwd)}</div>
        </div>
        ${s.running
          ? `<a class="oc-btn" href="${esc(s.open_url)}" target="_blank" rel="noopener">OPEN</a>
             <button class="oc-btn stop" onclick="ocStop('${s.id}')">STOP</button>`
          : `<button class="oc-btn" onclick="ocStart(this,'${s.id}','${esc(s.folder)}')">START</button>`}
        <button class="oc-btn stop" onclick="ocRemove('${s.id}', '${esc(s.name)}')">✕</button>
      </div>`).join('');
  }

  createBtn.onclick = async () => {
    let source = sourceEl.value.trim();
    // Paths pasted from the file-browser / address bar arrive percent-encoded
    // (%5C = '\', %20 = space). Decode so the real path reaches the hub.
    if (/%[0-9A-Fa-f]{2}/.test(source)) {
      try { source = decodeURIComponent(source); sourceEl.value = source; } catch (e) {}
    }
    if (!source) { alert('Enter a folder path to work on first.'); return; }
    createBtn.disabled = true;
    createBtn.textContent = 'COPYING + STARTING…';
    try {
      const res = await fetch('/api/opencode/sessions', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({source, name: nameEl.value.trim()}),
      });
      if (!res.ok) throw new Error(await res.text());
      sourceEl.value = '';
      nameEl.value = '';
    } catch (e) {
      alert('Failed to start session: ' + e.message);
    }
    createBtn.disabled = false;
    createBtn.textContent = '+ NEW SESSION';
    refresh();
  };

  window.ocStop = async (id) => {
    await fetch(`/api/opencode/sessions/${id}/stop`, {method: 'POST'});
    refresh();
  };
  // Restart a stopped session: drop the dead entry (keeps its folder) then resume
  // that folder, so you get one live row instead of a dead one + a duplicate.
  window.ocStart = async (btn, id, folder) => {
    if (btn) { btn.textContent = 'STARTING…'; btn.classList.add('disabled'); }
    try {
      await fetch(`/api/opencode/sessions/${id}`, {method: 'DELETE'});
      const res = await fetch('/api/opencode/sessions/resume', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({folder}),
      });
      if (!res.ok) throw new Error(await res.text());
    } catch (e) { alert('Failed to start: ' + e.message); }
    refresh();
  };
  window.ocRemove = async (id, name) => {
    if (!confirm(`Remove session "${name}"?\n\nThis STOPS it and DELETES its copied working folder.\nYour original folder is NOT touched.`)) return;
    if (!confirm(`Confirm: permanently delete the copied folder for "${name}"? This cannot be undone.`)) return;
    await fetch(`/api/opencode/sessions/${id}?purge=1`, {method: 'DELETE'});
    refresh();
  };
})();
</script>

<script>
// ── PC power menu (center-bottom button) ─────────────────────────────────────
(function () {
  const btn      = document.getElementById('power-btn');
  const menu     = document.getElementById('power-menu');
  const overlay  = document.getElementById('power-overlay');
  const titleEl  = document.getElementById('power-title');
  const countEl  = document.getElementById('power-count');
  const abortBtn = document.getElementById('power-abort');
  let timer = null;

  // confirm text + (for destructive actions) the countdown banner verb
  const CFG = {
    lock:     {confirm: '',                        banner: ''},
    sleep:    {confirm: 'Put this PC to sleep?',   banner: ''},
    restart:  {confirm: 'Restart this PC?',        banner: 'PC RESTARTING'},
    shutdown: {confirm: 'Shut down this PC?',      banner: 'PC SHUTTING DOWN'},
  };

  // The PIN is asked every time the panel is OPENED (not per shutdown). The
  // entered pin is held only until the panel closes and sent with each action.
  const scrim = document.getElementById('power-scrim');
  let pin = '';

  function openMenu() { menu.classList.add('open'); scrim.classList.add('show'); }
  function closeMenu() { menu.classList.remove('open'); scrim.classList.remove('show'); }

  menu.addEventListener('click', (e) => e.stopPropagation());
  scrim.addEventListener('click', closeMenu);
  document.addEventListener('click', closeMenu);

  btn.onclick = async (e) => {
    e.stopPropagation();
    if (menu.classList.contains('open')) { closeMenu(); return; }
    // Authenticate on every open. Try no-PIN first; a 403 means one is set → ask.
    let res = await fetch('/api/power/unlock', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: '{}',
    });
    if (res.status === 403) {
      const entered = prompt('Enter the power PIN:');
      if (!entered) return;
      res = await fetch('/api/power/unlock', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({pin: entered}),
      });
      if (!res.ok) { alert('Wrong PIN.'); return; }
      pin = entered;
    } else if (res.ok) {
      pin = '';   // no PIN configured
    } else {
      alert('Could not reach the hub.'); return;
    }
    openMenu();
  };

  async function runPower(action) {
    const res = await fetch('/api/power/' + action, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(pin ? {pin} : {}),
    });
    return res.ok;
  }

  function startCountdown(banner) {
    let n = 30;
    titleEl.textContent = '⚠ ' + banner;
    countEl.textContent = n;
    overlay.classList.add('show');
    timer = setInterval(() => {
      n -= 1;
      countEl.textContent = Math.max(0, n);
      if (n <= 0) { clearInterval(timer); timer = null; }
    }, 1000);
  }

  menu.querySelectorAll('.power-item').forEach((item) => {
    item.onclick = async () => {
      const action = item.dataset.action;
      const cfg = CFG[action];
      closeMenu();
      const prompt2 = cfg.banner ? (cfg.confirm + ' It powers off in 30s — you can abort.') : cfg.confirm;
      if (cfg.confirm && !confirm(prompt2)) return;
      let ok = false;
      try { ok = await runPower(action); } catch (e) {}
      if (!ok) { alert('Could not ' + action + ' the PC.'); return; }
      if (cfg.banner) startCountdown(cfg.banner);
    };
  });

  abortBtn.onclick = async () => {
    try { await fetch('/api/power/abort', {method: 'POST'}); } catch (e) {}
    if (timer) { clearInterval(timer); timer = null; }
    overlay.classList.remove('show');
  };
})();
</script>
</body>
</html>
"""


def _render_menu() -> str:
    import json
    apps_json = json.dumps({
        aid: {"name": cfg["name"], "emoji": cfg["emoji"], "pinned": cfg.get("pinned", False)}
        for aid, cfg in APPS.items()
    })
    shortcuts_json = json.dumps(SHORTCUTS)
    return (_HTML
            .replace("__APPS_JSON__", apps_json)
            .replace("__SHORTCUTS_JSON__", shortcuts_json))


@routes.get("/")
async def index(request: web.Request) -> web.Response:
    return web.Response(text=_render_menu(), content_type="text/html", charset="utf-8")


@routes.get("/favicon.png")
async def favicon_png(request: web.Request) -> web.Response:
    path = HERE / "favicon.png"
    if not path.exists():
        raise web.HTTPNotFound()
    return web.Response(body=path.read_bytes(), content_type="image/png")


@routes.get("/favicon-64.png")
async def favicon_64_png(request: web.Request) -> web.Response:
    # Small raster icon for browsers that don't render SVG favicons; falls back
    # to the full-size png if the downscaled one isn't present.
    path = HERE / "favicon-64.png"
    if not path.exists():
        path = HERE / "favicon.png"
    if not path.exists():
        raise web.HTTPNotFound()
    return web.Response(body=path.read_bytes(), content_type="image/png")


@routes.get("/favicon-256.png")
async def favicon_256_png(request: web.Request) -> web.Response:
    path = HERE / "favicon-256.png"
    if not path.exists():
        path = HERE / "favicon.png"
    if not path.exists():
        raise web.HTTPNotFound()
    return web.Response(body=path.read_bytes(), content_type="image/png")


@routes.get("/favicon.svg")
async def favicon_svg(request: web.Request) -> web.Response:
    return web.Response(text=_FAVICON_SVG, content_type="image/svg+xml", charset="utf-8")


@routes.get("/manifest.webmanifest")
async def manifest(request: web.Request) -> web.Response:
    """Web app manifest so Agent Hub can be installed as its own app (own window +
    its own taskbar icon, instead of the generic Edge icon)."""
    import json
    return web.json_response({
        "name": "Agent Hub",
        "short_name": "Agent Hub",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#080c28",
        "theme_color": "#080c28",
        "icons": [
            {"src": "/favicon-64.png", "sizes": "64x64", "type": "image/png"},
            {"src": "/favicon-256.png", "sizes": "256x256", "type": "image/png", "purpose": "any"},
            {"src": "/favicon-256.png", "sizes": "256x256", "type": "image/png", "purpose": "maskable"},
        ],
    }, content_type="application/manifest+json")


@routes.get("/offline.html")
async def offline_page(request: web.Request) -> web.Response:
    return web.Response(text=_OFFLINE_HTML, content_type="text/html", charset="utf-8")


@routes.get("/sw.js")
async def service_worker(request: web.Request) -> web.Response:
    return web.Response(text=_SW_JS, content_type="application/javascript", charset="utf-8")

