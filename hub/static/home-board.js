// Home board (desktop): the overview panels and your app icons as blocks on a canvas.
// The wheel zooms toward the pointer, dragging the background pans, a block is picked up by its title (an app icon by
// its body), double-click a title to focus one block, the corner resizes, the cross hides it into the tray.
// Phones keep the plain list (home-panels.js); the app cards further down the page are untouched.
(function () {
  var EASE = 'cubic-bezier(.2,.8,.2,1)', SPRING = 'cubic-bezier(.34,1.45,.64,1)', KEY = 'agenthub:board:v1';
  var reduce = matchMedia('(prefers-reduced-motion: reduce)');
  var P = {
    att: { t: 'NEEDS ATTENTION', x: -640, y: -330, w: 330, h: 150 }, runs: { t: 'RUNS', x: -290, y: -330, w: 190, h: 112 },
    ses: { t: 'SESSIONS', x: -80, y: -330, w: 250, h: 150 }, hlt: { t: 'HEALTH', x: 190, y: -330, w: 270, h: 170 }, use: { t: 'CLAUDE CODE USAGE', x: -640, y: -130, w: 330, h: 130 }
  };
  var ICON = { move: 'M9 5h.01M9 12h.01M9 19h.01M15 5h.01M15 12h.01M15 19h.01', min: 'M6 12h12', foc: 'M5 9V5h4M19 9V5h-4M5 15v4h4M19 15v4h-4', x: 'M6 6l12 12M18 6 6 18' };
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function svg(d, w) { var s = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('aria-hidden', 'true'); s.style.cssText = 'width:13px;height:13px;fill:none;stroke:currentColor;stroke-width:' + (w || 1.8) + ';stroke-linecap:round;stroke-linejoin:round'; var p = document.createElementNS('http://www.w3.org/2000/svg', 'path'); p.setAttribute('d', d); s.appendChild(p); return s; }
  function ago(s) { return s < 90 ? s + 's' : s < 5400 ? Math.round(s / 60) + 'm' : s < 172800 ? Math.round(s / 3600) + 'h' : Math.round(s / 86400) + 'd'; }
  function li(level, a, b) { var d = el('div', 'hb-li'); d.appendChild(el('i', level || '')); d.appendChild(el('b', '', a)); if (b) d.appendChild(el('span', '', b)); return d; }

  function css() {
    if (document.getElementById('hb-css')) return;
    var s = document.createElement('style'); s.id = 'hb-css';
    s.textContent = [
      '.hb{position:relative;height:clamp(460px,74vh,860px);margin:6px 0 8px;border:1px solid var(--border-dim,rgba(0,230,118,.25));border-radius:14px;overflow:hidden;background:#04061a;cursor:grab;touch-action:none;animation:hbIn .5s ease both}',
      '.hb:active{cursor:grabbing}',
      '@keyframes hbIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}',
      '.hb::before{content:"";position:absolute;inset:0;background-image:radial-gradient(rgba(0,230,118,.09) 1px,transparent 1px);background-size:32px 32px;pointer-events:none}',
      '.hb-world{position:absolute;left:0;top:0;width:0;height:0;transform-origin:0 0;will-change:transform}',
      '.hb-bar{position:absolute;left:12px;top:10px;right:12px;display:flex;gap:6px;align-items:center;z-index:6;pointer-events:none}',
      '.hb-bar>*{pointer-events:auto}.hb-z{font:700 9px Orbitron,monospace;letter-spacing:1.2px;color:var(--text-faint,#6fae92);margin-right:auto;pointer-events:none}',
      '.hb-btn{font:700 9px Orbitron,monospace;letter-spacing:1.2px;color:var(--accent,#00e676);background:rgba(6,10,36,.9);border:1px solid var(--border-dim,rgba(0,230,118,.28));border-radius:7px;padding:7px 11px;min-height:30px;cursor:pointer}',
      '.hb-btn:hover{background:rgba(0,230,118,.14)}',
      '.hb-tray{position:absolute;left:12px;bottom:10px;display:flex;gap:6px;flex-wrap:wrap;z-index:6;max-width:80%}',
      '.hk{position:absolute;background:rgba(6,10,36,.92);border:1px solid var(--border-dim,rgba(0,230,118,.28));border-radius:3px;display:flex;flex-direction:column;min-width:0;transition:border-color .25s,box-shadow .25s,opacity .3s;will-change:transform}',
      '.hk::before,.hk::after{content:"";position:absolute;width:9px;height:9px;pointer-events:none}',
      '.hk::before{left:-2px;top:-2px;border-left:2px solid var(--accent,#00e676);border-top:2px solid var(--accent,#00e676)}.hk::after{right:-2px;bottom:-2px;border-right:2px solid var(--accent,#00e676);border-bottom:2px solid var(--accent,#00e676)}',
      '.hk.amber{border-color:rgba(224,165,60,.6)}.hk.red{border-color:rgba(255,92,92,.6)}',
      '.hk.pick{border-color:var(--accent,#00e676);box-shadow:0 0 0 1px var(--accent,#00e676),0 18px 40px rgba(0,0,0,.6)}.hk.dim{opacity:.12;pointer-events:none}',
      '.hk-h{display:flex;align-items:center;gap:4px;padding:4px 4px 4px 9px;cursor:grab;user-select:none;flex:none}',
      '.hk-h .t{font:700 8.5px Orbitron,monospace;letter-spacing:1.4px;color:var(--text-muted,#8fcfb2);flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
      '.hk-h .n{font:700 9px Orbitron,monospace;color:var(--text-faint,#6fae92)}',
      '.hk-h button{width:24px;height:24px;border:0;background:none;color:var(--text-faint,#6fae92);border-radius:5px;cursor:pointer;display:grid;place-items:center;padding:0}.hk-h button:hover{color:var(--text,#d9ffe9);background:rgba(0,230,118,.12)}',
      '.hk-b{flex:1;min-height:0;display:grid;grid-template-rows:1fr;transition:grid-template-rows .3s ' + EASE + ';overflow:hidden}.hk.min .hk-b{grid-template-rows:0fr}.hk-i{overflow:hidden;min-height:0}',
      '.hk-rz{position:absolute;right:0;bottom:0;width:16px;height:16px;cursor:nwse-resize;touch-action:none}.hk.min .hk-rz{display:none}',
      '.hb-li{display:flex;gap:8px;align-items:baseline;padding:5px 10px;border-top:1px solid rgba(255,255,255,.05);font-size:12.5px;color:var(--text,#d9ffe9)}.hb-li i{width:6px;height:6px;border-radius:50%;background:var(--accent,#00e676);flex:none}.hb-li i.a{background:#e0a53c}.hb-li i.r{background:#ff5c5c}.hb-li i.o{background:var(--text-faint,#6fae92)}.hb-li span{color:var(--text-muted,#8fcfb2);font-size:11.5px;overflow-wrap:anywhere}',
      '.hb-stat{padding:2px 10px 8px}.hb-stat b{display:block;font:900 32px Orbitron,monospace;color:var(--accent,#00e676);line-height:1.1}.hb-stat span{color:var(--text-muted,#8fcfb2);font-size:12px}',
      '.hb-note{padding:2px 10px 9px;font-size:12px;color:var(--text-muted,#8fcfb2);line-height:1.45}',
      '.hk-app{display:flex;align-items:center;gap:10px;padding:4px 10px 8px;cursor:pointer}.hk-app .gi{width:32px;height:32px;flex:none;display:grid;place-items:center;font-size:22px}.hk-app .gi svg{width:30px;height:30px}.hk-app b{font-weight:600;font-size:12.5px;line-height:1.15;color:var(--text,#d9ffe9)}.hk-app small{display:block;font:600 7.5px Orbitron,monospace;letter-spacing:1px;color:var(--text-faint,#6fae92)}.hk-app small.on{color:var(--accent,#00e676)}',
      '@media (prefers-reduced-motion:reduce){.hb{animation:none}.hk-b{transition:none}}'
    ].join('\n');
    document.head.appendChild(s);
  }

  function mount(root) {
    css();
    var L = {}, hid = {}, data = null, V = { x: 0, y: 0, k: 1 }, focusId = null, zTop = 2, blocks = {};
    try { var saved = JSON.parse(localStorage.getItem(KEY) || 'null'); if (saved) { L = saved.L || {}; hid = saved.hid || {}; } } catch (e) {}
    function save() { try { localStorage.setItem(KEY, JSON.stringify({ L: L, hid: hid })); } catch (e) {} }

    root.replaceChildren(); // Home is a 520 px column; the board breaks out of it to the width of the window.
    root.style.width = 'min(96vw,1500px)'; root.style.maxWidth = 'none'; root.style.marginLeft = 'calc((100% - min(96vw,1500px)) / 2)'; root.style.boxSizing = 'border-box';
    var host = el('div', 'hb'), world = el('div', 'hb-world'), bar = el('div', 'hb-bar'), zh = el('div', 'hb-z', '100%'), tray = el('div', 'hb-tray');
    var fitBtn = el('button', 'hb-btn', 'FIT'), tidyBtn = el('button', 'hb-btn', 'TIDY');
    fitBtn.type = tidyBtn.type = 'button'; bar.append(zh, tidyBtn, fitBtn); host.append(bar, world, tray); root.appendChild(host);

    var defs = [['att', P.att], ['runs', P.runs], ['ses', P.ses], ['hlt', P.hlt], ['use', P.use]];
    var apps = (typeof APP_LIST !== 'undefined' ? APP_LIST : []).filter(function (a) { return !a.hidden; });
    // the three built-in cards (Auto-LLM, YouTube Download, YouTube Upload) are page sections, not apps: an icon block scrolls to the card and opens it
    var CARDS = [['oc', 'Auto-LLM', 'oc-header', null], ['ytdl', 'YouTube Download', 'ytdl-header', 'ytdl-toggle-btn'], ['yt', 'YouTube Upload', 'yt-header', 'yt-toggle-btn']].filter(function (c) { return document.getElementById(c[2]); });
    CARDS.forEach(function (c, i) { defs.push(['card:' + c[0], { t: 'APP', x: -640 + (i % 4) * 165, y: 30 + Math.floor(i / 4) * 82, w: 155, h: 72, card: c }]); });
    apps.forEach(function (a, i) { var j = i + CARDS.length; defs.push(['app:' + a.id, { t: 'APP', x: -640 + (j % 4) * 165, y: 30 + Math.floor(j / 4) * 82, w: 155, h: 72, app: a }]); });
    defs.forEach(function (d) { if (!L[d[0]]) L[d[0]] = { x: d[1].x, y: d[1].y, w: d[1].w, h: d[1].h, min: 0 }; });

    function applyBlock(id) { var e = blocks[id], l = L[id]; e.style.left = l.x + 'px'; e.style.top = l.y + 'px'; e.style.width = l.w + 'px'; e.style.height = l.min ? '' : l.h + 'px'; e.classList.toggle('min', !!l.min); e.style.zIndex = l.z || 1; e.hidden = !!hid[id]; }
    function mk(id, d) {
      var e = el('div', 'hk'); e.dataset.id = id;
      var h = el('div', 'hk-h'); h.appendChild(el('span', 't', (d.app || d.card) ? 'APP' : d.t)); h.appendChild(el('span', 'n'));
      [['min', 'Minimise'], ['foc', 'Focus'], ['x', 'Hide']].forEach(function (b) { var bt = el('button'); bt.type = 'button'; bt.dataset.a = b[0]; bt.setAttribute('aria-label', b[1]); bt.appendChild(svg(ICON[b[0]])); h.appendChild(bt); });
      var body = el('div', 'hk-b'), inn = el('div', 'hk-i'); body.appendChild(inn); e.append(h, body, el('div', 'hk-rz')); e._in = inn; e._n = h.querySelector('.n'); e._app = d.app || null; e._open = null; e._name = d.app ? (d.app.name || d.app.id) : d.card ? d.card[1] : d.t;
      if (d.app) {
        var a = d.app, box = el('div', 'hk-app'), gi = el('div', 'gi');
        var ic = (typeof CARD_ICONS !== 'undefined' && CARD_ICONS[a.id]) || null;
        if (ic) gi.innerHTML = ic; else gi.textContent = a.emoji || '';
        var nm = el('div'); nm.appendChild(el('b', '', a.name || a.id)); var st = el('small', a.running ? 'on' : '', a.running ? 'RUNNING' : 'IDLE'); nm.appendChild(st); box.append(gi, nm); inn.appendChild(box); e._st = st;
      }
      if (d.app) e._open = function () { if (typeof openApp === 'function') openApp(d.app.id, d.app.name); };
      if (d.card) {
        var c = d.card, hdr = document.getElementById(c[2]), ci = hdr && hdr.querySelector('.card-emoji'), bx2 = el('div', 'hk-app'), g2 = el('div', 'gi'); if (ci) g2.innerHTML = ci.innerHTML;
        var nm2 = el('div'); nm2.appendChild(el('b', '', c[1])); nm2.appendChild(el('small', '', 'OPEN')); bx2.append(g2, nm2); inn.appendChild(bx2);
        e._open = function () { var t = c[3] && document.getElementById(c[3]); if (t && /EXPAND/.test(t.textContent)) t.click(); hdr.scrollIntoView({ behavior: reduce.matches ? 'auto' : 'smooth', block: 'center' }); };
      }
      blocks[id] = e; world.appendChild(e); applyBlock(id); return e;
    }
    defs.forEach(function (d) { mk(d[0], d[1]); });
    if (apps.length === 0) { /* nothing to add */ }

    function paint() {
      if (!data) { ['att', 'runs', 'ses', 'hlt', 'use'].forEach(function (id) { if (!blocks[id]._in.firstChild) blocks[id]._in.appendChild(el('div', 'hb-note', 'Reading the Hub…')); }); return; }
      var a = blocks.att, nA = data.attention.length; a._in.replaceChildren(); a._n.textContent = nA ? String(nA) : '';
      if (!nA) a._in.appendChild(el('div', 'hb-note', 'Nothing needs you right now.')); data.attention.forEach(function (x) {
        var r = li(x.level === 'red' ? 'r' : 'a', x.title, x.options ? '' : x.detail);
        if (x.options) { var bar = el('div'); bar.style.cssText = 'display:flex;gap:6px;padding:2px 10px 8px'; x.options.forEach(function (o) { var b = el('button', 'hb-btn', String(o.name || o.id).toUpperCase()); b.type = 'button'; b.onclick = function () { fetch('/api/acp/answer', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: x.id, option: o.id }) }).then(function () { if (window.__hubHomePanels) window.__hubHomePanels.refresh(); }); }; bar.appendChild(b); }); a._in.appendChild(r); a._in.appendChild(bar); }
        else a._in.appendChild(r);
      });
      a.classList.toggle('amber', nA > 0); a.classList.toggle('red', data.attention.some(function (x) { return x.level === 'red'; }));
      var r = blocks.runs; r._in.replaceChildren(); var st = el('div', 'hb-stat'); st.appendChild(el('b', '', String(data.runs.length))); st.appendChild(el('span', '', data.runs.length ? data.runs.map(function (m) { return m.brief; }).slice(0, 2).join(' · ') : 'missions running')); r._in.appendChild(st);
      var s = blocks.ses; s._in.replaceChildren(); var ss = data.sessions, any = false;
      [['needs_you', 'a'], ['working', ''], ['idle', 'o']].forEach(function (g) { ss[g[0]].forEach(function (m) { any = true; s._in.appendChild(li(g[1], m.brief, (m.ask || m.project) + ' · ' + g[0].replace('_', ' '))); }); });
      if (!any) s._in.appendChild(el('div', 'hb-note', 'No agent session is waiting, working or recently finished.'));
      var u = blocks.use; u._in.replaceChildren(); var cu = data.usage && data.usage.claude;
      if (!cu) u._in.appendChild(el('div', 'hb-note', 'Counting Claude Code’s logs…'));
      else {
        var bars = el('div'); bars.style.cssText = 'display:flex;align-items:flex-end;gap:3px;height:62px;padding:6px 10px 2px'; var mx = Math.max.apply(null, cu.by_hour.concat([1]));
        cu.by_hour.forEach(function (v) { var i = el('i'); i.style.cssText = 'flex:1;background:linear-gradient(#3ba7ff,rgba(59,167,255,.25));border:1px solid rgba(59,167,255,.6);border-bottom:0;height:' + Math.max(2, Math.round(v / mx * 100)) + '%'; bars.appendChild(i); });
        u._in.appendChild(bars); u._in.appendChild(el('div', 'hb-note', cu.tokens_5h.toLocaleString() + ' tokens in 5 h · ' + cu.tokens_7d.toLocaleString() + ' in 7 days · counted from the logs, no plan limit'));
      }
      var h = data.health, hb = blocks.hlt; hb._in.replaceChildren();
      hb._in.appendChild(li('', 'Hub v' + h.version, 'up ' + ago(h.uptime_s)));
      hb._in.appendChild(li(h.local_model && h.local_model.listening ? '' : 'o', 'Local model', h.local_model && h.local_model.listening ? 'listening' : 'off'));
      hb._in.appendChild(li(h.recent_problems ? 'a' : '', 'Warnings', String(h.recent_problems)));
      hb._in.appendChild(li('o', 'Graphics card', 'not measured'));
      if (h.apps.failed.length) hb._in.appendChild(li('r', 'Failed to start', h.apps.failed.join(', ')));
      Object.keys(blocks).forEach(function (id) { var b = blocks[id]; if (b._app) { var run = (h.apps.running || []).indexOf(b._app.id) >= 0 || b._app.running; b._st.textContent = run ? 'RUNNING' : 'IDLE'; b._st.className = run ? 'on' : ''; } });
    }

    function place() { world.style.transform = 'translate(' + V.x + 'px,' + V.y + 'px) scale(' + V.k + ')'; zh.textContent = Math.round(V.k * 100) + '%'; }
    function cam(to, ms) {
      if (reduce.matches || !ms) { V = to; place(); return; }
      var f = { x: V.x, y: V.y, k: V.k }, t0 = performance.now();
      (function s(n) { var u = Math.min(1, (n - t0) / ms), e = 1 - Math.pow(1 - u, 3.4); V = { x: f.x + (to.x - f.x) * e, y: f.y + (to.y - f.y) * e, k: f.k + (to.k - f.k) * e }; place(); if (u < 1) requestAnimationFrame(s); })(t0);
    }
    function fit(anim) {
      var r = host.getBoundingClientRect(), x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9, n = 0;
      Object.keys(blocks).forEach(function (id) { if (hid[id]) return; var l = L[id]; n++; x0 = Math.min(x0, l.x); y0 = Math.min(y0, l.y); x1 = Math.max(x1, l.x + l.w); y1 = Math.max(y1, l.y + (l.min ? 30 : l.h)); });
      if (!n || !r.width) return;
      var k = Math.min(1.2, Math.min((r.width - 90) / (x1 - x0), (r.height - 110) / (y1 - y0)));
      cam({ k: k, x: r.width / 2 - (x0 + x1) / 2 * k, y: r.height / 2 - (y0 + y1) / 2 * k + 8 }, anim ? 520 : 0);
    }
    function undim() { Object.keys(blocks).forEach(function (i) { blocks[i].classList.remove('dim'); }); }
    function focusBlock(id) {
      if (focusId === id) { focusId = null; undim(); fit(true); return; }
      focusId = id; Object.keys(blocks).forEach(function (i) { blocks[i].classList.toggle('dim', i !== id); });
      var l = L[id], r = host.getBoundingClientRect(), k = Math.min(2.4, Math.min(r.width * .7 / l.w, r.height * .7 / (l.min ? 60 : l.h)));
      cam({ k: k, x: r.width / 2 - (l.x + l.w / 2) * k, y: r.height / 2 - (l.y + (l.min ? 15 : l.h / 2)) * k }, 520);
    }
    function trayDraw() {
      tray.replaceChildren();
      Object.keys(hid).filter(function (i) { return hid[i] && blocks[i]; }).forEach(function (id) {
        var b = el('button', 'hb-btn', '+ ' + (blocks[id]._name || id)); b.type = 'button';
        b.onclick = function () { hid[id] = 0; applyBlock(id); save(); if (!reduce.matches) blocks[id].animate([{ opacity: 0, transform: 'scale(.8)' }, { opacity: 1, transform: 'none' }], { duration: 380, easing: SPRING }); trayDraw(); };
        tray.appendChild(b);
      });
    }

    function onWheel(e) {
      e.preventDefault(); if (focusId) { focusId = null; undim(); }
      var r = host.getBoundingClientRect(), px = e.clientX - r.left, py = e.clientY - r.top, k = Math.min(2.6, Math.max(.3, V.k * Math.exp(-e.deltaY * .0014)));
      V.x = px - (px - V.x) * (k / V.k); V.y = py - (py - V.y) * (k / V.k); V.k = k; place();
    }
    host.addEventListener('wheel', onWheel, { passive: false });
    host.addEventListener('pointerdown', function (e) {
      if (e.button || e.target.closest('.hk,.hb-bar .hb-btn,.hb-tray')) return;
      var sx = e.clientX - V.x, sy = e.clientY - V.y;
      function mv(ev) { V.x = ev.clientX - sx; V.y = ev.clientY - sy; place(); }
      function up() { removeEventListener('pointermove', mv); removeEventListener('pointerup', up); }
      addEventListener('pointermove', mv); addEventListener('pointerup', up);
    });
    host.addEventListener('dblclick', function (e) { if (!e.target.closest('.hk,.hb-btn,.hb-tray')) { focusId = null; undim(); fit(true); } });
    world.addEventListener('pointerdown', function (e) {
      var b = e.target.closest('.hk'); if (!b || e.button) return; var id = b.dataset.id, l = L[id];
      if (e.target.closest('.hk-rz')) {
        e.preventDefault(); var sw = l.w, sh = l.h, sx = e.clientX, sy = e.clientY;
        var mv = function (ev) { l.w = Math.max(130, sw + (ev.clientX - sx) / V.k); l.h = Math.max(70, sh + (ev.clientY - sy) / V.k); applyBlock(id); };
        var up = function () { removeEventListener('pointermove', mv); removeEventListener('pointerup', up); save(); };
        addEventListener('pointermove', mv); addEventListener('pointerup', up); return;
      }
      if (e.target.closest('button')) return;
      var grab = e.target.closest('.hk-h') || (b._open ? b : null); if (!grab) return;
      e.preventDefault(); l.z = ++zTop; applyBlock(id); b.classList.add('pick');
      var sx2 = e.clientX, sy2 = e.clientY, ox = l.x, oy = l.y, moved = false;
      function mv2(ev) { var dx = ev.clientX - sx2, dy = ev.clientY - sy2; if (Math.abs(dx) + Math.abs(dy) > 5) moved = true; l.x = ox + dx / V.k; l.y = oy + dy / V.k; applyBlock(id); }
      function up2() { removeEventListener('pointermove', mv2); removeEventListener('pointerup', up2); b.classList.remove('pick'); save(); if (!moved && b._open) b._open(); }
      addEventListener('pointermove', mv2); addEventListener('pointerup', up2);
    });
    world.addEventListener('click', function (e) {
      var bt = e.target.closest('button[data-a]'); if (!bt) return; var id = bt.closest('.hk').dataset.id, a = bt.dataset.a;
      if (a === 'min') { L[id].min = L[id].min ? 0 : 1; applyBlock(id); save(); }
      if (a === 'foc') focusBlock(id);
      if (a === 'x') { var b = blocks[id]; var done = function () { hid[id] = 1; applyBlock(id); b.getAnimations().forEach(function (x) { x.cancel(); }); save(); trayDraw(); }; if (reduce.matches) done(); else b.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'scale(.85)' }], { duration: 200, fill: 'forwards' }).onfinish = done; }
    });
    world.addEventListener('dblclick', function (e) { var h = e.target.closest('.hk-h'); if (h && !e.target.closest('button')) focusBlock(h.closest('.hk').dataset.id); });
    fitBtn.onclick = function () { focusId = null; undim(); fit(true); };
    tidyBtn.onclick = function () {
      var from = {}; defs.forEach(function (d) { var l = L[d[0]]; from[d[0]] = { x: l.x, y: l.y, w: l.w, h: l.h }; hid[d[0]] = 0; });
      var t0 = performance.now(); focusId = null; undim();
      (function s(n) { var u = Math.min(1, (n - t0) / 620), e = 1 - Math.pow(1 - u, 3.4);
        defs.forEach(function (d) { var f = from[d[0]], t = d[1], l = L[d[0]]; l.x = f.x + (t.x - f.x) * e; l.y = f.y + (t.y - f.y) * e; l.w = f.w + (t.w - f.w) * e; l.h = f.h + (t.h - f.h) * e; l.min = 0; applyBlock(d[0]); });
        if (u < 1) requestAnimationFrame(s); else { save(); trayDraw(); fit(true); } })(t0);
    };
    function onKey(e) { if (e.key === 'Escape' && focusId) { focusId = null; undim(); fit(true); } }
    document.addEventListener('keydown', onKey);
    trayDraw(); paint(); requestAnimationFrame(function () { fit(false); });
    return {
      update: function (d) { data = d; paint(); },
      destroy: function () { document.removeEventListener('keydown', onKey); root.replaceChildren(); root.style.width = root.style.maxWidth = root.style.marginLeft = ''; },
      state: function () { return { V: V, L: L, hid: hid }; }
    };
  }
  window.__hubBoard = { mount: mount };
})();
