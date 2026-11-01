// Home panels: what needs you, what is running, who is waiting, how the machine is.
// They sit above the app tiles and never replace them. Each panel can be dragged to a new place, minimised
// or hidden, and the layout is remembered per device class: a phone and a PC keep separate layouts.
// Data comes from one read-only call (/api/home/state); the first fetch waits for the cube turn to finish.
(function () {
  var root = document.getElementById('home-panels');
  if (!root) return;
  var reduce = matchMedia('(prefers-reduced-motion: reduce)');
  var phone = matchMedia('(max-width: 720px)');
  var KEY = function () { return 'agenthub:home-layout:' + (phone.matches ? 'phone' : 'desktop'); };
  var EASE = 'cubic-bezier(.2,.8,.2,1)';
  var DEFAULTS = {
    desktop: { order: ['attention', 'runs', 'sessions', 'health'], min: {}, hidden: {} },
    phone: { order: ['attention', 'sessions', 'runs', 'health'], min: { runs: 1, health: 1 }, hidden: {} }
  };
  var PANELS = {
    attention: { title: 'NEEDS ATTENTION', wide: true, icon: 'M12 3 2.5 20h19L12 3Zm0 6v5m0 3v.01' },
    runs: { title: 'RUNS', icon: 'M5 4l14 8-14 8V4Z' },
    sessions: { title: 'SESSIONS', icon: 'M4 5h16v10H4zM8 19h8M12 15v4' },
    health: { title: 'HEALTH', icon: 'M3 12h4l2-6 4 12 2-6h6' }
  };
  var data = null, layout = load(), editing = false, els = {}, board = null;

  function load() {
    var cls = phone.matches ? 'phone' : 'desktop', d = JSON.parse(JSON.stringify(DEFAULTS[cls]));
    try {
      var s = JSON.parse(localStorage.getItem(KEY()) || 'null');
      if (s && Array.isArray(s.order)) {
        var order = s.order.filter(function (id) { return PANELS[id]; });
        Object.keys(PANELS).forEach(function (id) { if (order.indexOf(id) < 0) order.push(id); });
        d = { order: order, min: s.min || {}, hidden: s.hidden || {} };
      }
    } catch (e) {}
    return d;
  }
  function save() { try { localStorage.setItem(KEY(), JSON.stringify(layout)); } catch (e) {} }

  var css = document.createElement('style');
  css.textContent = [
    '#home-panels{max-width:1100px;margin:0 auto;padding:6px 12px 2px}',
    '.hp-bar{display:flex;align-items:center;gap:8px;margin:2px 0 8px}',
    '.hp-bar .hp-t{font:700 10px Orbitron,monospace;letter-spacing:2px;color:var(--text-faint,#7f9)}',
    '.hp-bar .hp-sp{flex:1}',
    '.hp-btn{font:600 9.5px Orbitron,monospace;letter-spacing:1px;color:var(--accent,#00e676);background:none;border:1px solid var(--border-dim,rgba(0,230,118,.25));border-radius:6px;padding:7px 10px;min-height:32px;cursor:pointer}',
    '.hp-btn.on{background:rgba(0,230,118,.14);border-color:var(--accent,#00e676)}',
    '.hp-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;align-items:start}',
    '@media (max-width:720px){.hp-grid{grid-template-columns:minmax(0,1fr)}#home-panels{padding:4px 10px 0}}',
    '.hp{background:rgba(8,12,40,.72);border:1px solid var(--border-dim,rgba(0,230,118,.22));border-radius:12px;position:relative;min-width:0}',
    '.hp.wide{grid-column:1/-1}',
    '.hp[data-level="red"]{border-color:rgba(255,92,92,.55)}.hp[data-level="amber"]{border-color:rgba(224,165,60,.55)}',
    '.hp-h{display:flex;align-items:center;gap:8px;padding:9px 10px 9px 12px;min-height:40px}',
    '.hp-h svg{width:15px;height:15px;stroke:var(--accent,#00e676);fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;flex:none}',
    '.hp-h .t{font:700 10px Orbitron,monospace;letter-spacing:1.6px;color:var(--text,#d9ffe9)}',
    '.hp-h .n{font:600 10px Orbitron,monospace;color:var(--text-faint,#7f9);margin-left:2px}',
    '.hp-h .sp{flex:1}',
    '.hp-i{width:34px;height:34px;border:0;background:none;border-radius:8px;display:grid;place-items:center;cursor:pointer;color:var(--text-muted,#9db)}',
    '.hp-i:hover{background:rgba(0,230,118,.1)}.hp-i svg{stroke:currentColor}',
    '.hp-i.chev svg{transition:transform .28s ' + EASE + '}.hp.min .hp-i.chev svg{transform:rotate(-90deg)}',
    '.hp-i.grab{cursor:grab;touch-action:none}.hp-i.grab:active{cursor:grabbing}',
    '.hp-edit{display:none}.editing .hp-edit{display:grid}',
    '.hp-body{display:grid;grid-template-rows:1fr;transition:grid-template-rows .3s ' + EASE + '}',
    '.hp.min .hp-body{grid-template-rows:0fr}',
    '.hp-in{overflow:hidden;min-height:0}',
    '.hp-list{list-style:none;margin:0;padding:0 12px 10px;display:flex;flex-direction:column;gap:2px}',
    '.hp-row{display:flex;gap:9px;align-items:baseline;padding:6px 0;border-top:1px solid rgba(255,255,255,.05);color:var(--text,#d9ffe9);text-decoration:none;font-size:13px;line-height:1.35}',
    '.hp-row:first-child{border-top:0}a.hp-row:hover .a{text-decoration:underline}',
    '.hp-row .d{flex:none;width:7px;height:7px;border-radius:50%;background:var(--accent,#00e676);transform:translateY(-1px)}',
    '.hp-row .d.red{background:#ff5c5c}.hp-row .d.amber{background:#e0a53c}',
    '.hp-row .a{font-weight:600}.hp-row .b{color:var(--text-muted,#9db);font-size:12px;overflow-wrap:anywhere}',
    '.hp-row .r{margin-left:auto;font:600 9.5px Orbitron,monospace;color:var(--text-faint,#7f9);white-space:nowrap}',
    '.hp-empty{padding:2px 12px 12px;color:var(--text-muted,#9db);font-size:12.5px}',
    '.hp-sub{padding:6px 12px 0;font:700 9px Orbitron,monospace;letter-spacing:1.4px;color:var(--text-faint,#7f9)}',
    '.hp-kv{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;padding:0 12px 12px;font-size:12.5px}',
    '.hp-kv span:nth-child(odd){color:var(--text-muted,#9db)}',
    '.hp-hidden{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 8px}',
    '.hp.lift{z-index:5;box-shadow:0 14px 34px rgba(0,0,0,.55);transform-origin:center}',
    '.hp-ph{border:1px dashed var(--border-dim,rgba(0,230,118,.3));border-radius:12px}',
    '@media (prefers-reduced-motion:reduce){.hp-body,.hp-i.chev svg{transition:none}}'
  ].join('\n');
  document.head.appendChild(css);

  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function icon(d) {
    var s = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('aria-hidden', 'true');
    var p = document.createElementNS('http://www.w3.org/2000/svg', 'path'); p.setAttribute('d', d); s.appendChild(p); return s;
  }
  function ago(s) { return s < 90 ? s + 's' : s < 5400 ? Math.round(s / 60) + 'm' : s < 172800 ? Math.round(s / 3600) + 'h' : Math.round(s / 86400) + 'd'; }
  function row(level, a, b, r, href) {
    var li = el(href ? 'a' : 'div', 'hp-row'); if (href) li.href = href;
    li.appendChild(el('span', 'd ' + (level || '')));
    var w = el('span'); w.appendChild(el('span', 'a', a)); if (b) { w.appendChild(document.createTextNode(' ')); w.appendChild(el('span', 'b', b)); } li.appendChild(w);
    if (r) li.appendChild(el('span', 'r', r));
    return li;
  }
  function list(rows, empty) {
    if (!rows.length) return el('div', 'hp-empty', empty);
    var ul = el('div', 'hp-list'); rows.forEach(function (r) { ul.appendChild(r); }); return ul;
  }

  var RENDER = {
    attention: function (s) {
      var rows = s.attention.map(function (a) { return row(a.level, a.title, a.detail, '', a.go); });
      return { node: list(rows, 'Nothing needs you right now.'), n: rows.length, level: s.attention.some(function (a) { return a.level === 'red'; }) ? 'red' : rows.length ? 'amber' : '' };
    },
    runs: function (s) {
      var rows = s.runs.map(function (m) { return row('', m.brief, m.project + ' · ' + m.status + (m.model ? ' · ' + m.model : ''), ago(m.age_s), '/missions'); });
      return { node: list(rows, 'No mission is running.'), n: rows.length };
    },
    sessions: function (s) {
      var f = el('div'), g = [['needs_you', 'NEEDS YOU', 'amber'], ['working', 'WORKING', ''], ['idle', 'IDLE · LAST 24 H', '']], n = 0;
      g.forEach(function (x) {
        var arr = s.sessions[x[0]]; n += x[0] === 'idle' ? 0 : arr.length; if (!arr.length) return;
        f.appendChild(el('div', 'hp-sub', x[1]));
        f.appendChild(list(arr.map(function (m) { return row(x[2], m.brief, m.ask || m.project, m.agent, '/missions'); })));
      });
      return { node: f.children.length ? f : el('div', 'hp-empty', 'No agent session is waiting, working or recently finished.'), n: n, level: s.sessions.needs_you.length ? 'amber' : '' };
    },
    health: function (s) {
      var h = s.health, f = el('div'), kv = el('div', 'hp-kv');
      function add(k, v) { kv.appendChild(el('span', '', k)); kv.appendChild(el('span', '', v)); }
      add('Hub', 'v' + h.version + ' · up ' + ago(h.uptime_s));
      add('Apps running', h.apps.running.length ? h.apps.running.join(', ') : 'none');
      if (h.apps.failed.length) add('Apps failed', h.apps.failed.join(', '));
      add('Local model', h.local_model && h.local_model.listening ? 'listening' : 'not running' + (h.stay_local ? ' (missions stay local)' : ''));
      add('Disk free', 'state ' + (h.disk_free_gb.state != null ? h.disk_free_gb.state + ' GB' : '?') + (h.disk_free_gb.work != null ? ' · work ' + h.disk_free_gb.work + ' GB' : ''));
      add('Recent warnings', String(h.recent_problems));
      add('Graphics card', 'not measured');
      f.appendChild(kv);
      var a = el('a', 'hp-btn', 'DIAGNOSE'); a.href = '/api/diagnose'; a.target = '_blank'; a.rel = 'noopener'; a.style.cssText = 'display:inline-block;margin:0 12px 12px;text-decoration:none';
      f.appendChild(a);
      return { node: f, n: 0, level: h.apps.failed.length ? 'red' : '' };
    }
  };

  function build() {
    root.replaceChildren();
    var bar = el('div', 'hp-bar'); bar.appendChild(el('span', 'hp-t', 'OVERVIEW')); bar.appendChild(el('span', 'hp-sp'));
    var hidden = Object.keys(layout.hidden).filter(function (k) { return layout.hidden[k]; });
    var edit = el('button', 'hp-btn' + (editing ? ' on' : ''), editing ? 'DONE' : 'CUSTOMISE'); edit.type = 'button';
    edit.onclick = function () { editing = !editing; build(); paint(); };
    bar.appendChild(edit);
    if (editing) { var rs = el('button', 'hp-btn', 'RESET'); rs.type = 'button'; rs.onclick = function () { layout = JSON.parse(JSON.stringify(DEFAULTS[phone.matches ? 'phone' : 'desktop'])); save(); build(); paint(); }; bar.appendChild(rs); }
    root.appendChild(bar);
    if (editing && hidden.length) {
      var hb = el('div', 'hp-hidden');
      hidden.forEach(function (id) { var b = el('button', 'hp-btn', '+ ' + PANELS[id].title); b.type = 'button'; b.onclick = function () { layout.hidden[id] = 0; save(); build(); paint(); }; hb.appendChild(b); });
      root.appendChild(hb);
    }
    var grid = el('div', 'hp-grid' + (editing ? ' editing' : '')); root.appendChild(grid); els = {};
    layout.order.forEach(function (id) {
      if (layout.hidden[id]) return;
      var P = PANELS[id], card = el('section', 'hp' + (P.wide ? ' wide' : '') + (layout.min[id] ? ' min' : '')); card.dataset.id = id; els[id] = card;
      var h = el('div', 'hp-h'); h.appendChild(icon(P.icon)); h.appendChild(el('span', 't', P.title)); h.appendChild(el('span', 'n')); h.appendChild(el('span', 'sp'));
      var grab = el('button', 'hp-i hp-edit grab'); grab.type = 'button'; grab.title = 'Drag to move (arrow keys also move it)'; grab.setAttribute('aria-label', 'Move ' + P.title); grab.appendChild(icon('M9 5h.01M9 12h.01M9 19h.01M15 5h.01M15 12h.01M15 19h.01'));
      grab.firstChild.style.strokeWidth = '3.2'; h.appendChild(grab);
      var hide = el('button', 'hp-i hp-edit'); hide.type = 'button'; hide.title = 'Hide this panel'; hide.setAttribute('aria-label', 'Hide ' + P.title); hide.appendChild(icon('M6 6l12 12M18 6 6 18'));
      hide.onclick = function () { layout.hidden[id] = 1; save(); build(); paint(); }; h.appendChild(hide);
      var ch = el('button', 'hp-i chev'); ch.type = 'button'; ch.title = 'Minimise / expand'; ch.setAttribute('aria-label', 'Minimise or expand ' + P.title); ch.setAttribute('aria-expanded', String(!layout.min[id])); ch.appendChild(icon('M6 9l6 6 6-6'));
      ch.onclick = function () { layout.min[id] = layout.min[id] ? 0 : 1; card.classList.toggle('min', !!layout.min[id]); ch.setAttribute('aria-expanded', String(!layout.min[id])); save(); }; h.appendChild(ch);
      card.appendChild(h);
      var body = el('div', 'hp-body'), inn = el('div', 'hp-in'); body.appendChild(inn); card.appendChild(body); card._in = inn; card._n = h.querySelector('.n');
      grid.appendChild(card);
      wireDrag(grab, card, grid); wireKeys(grab, id);
    });
  }

  function paint() {
    if (!data) { Object.keys(els).forEach(function (id) { els[id]._in.replaceChildren(el('div', 'hp-empty', 'Reading the Hub…')); }); return; }
    Object.keys(els).forEach(function (id) {
      var r = RENDER[id](data), c = els[id];
      c._in.replaceChildren(r.node); c._n.textContent = r.n ? String(r.n) : ''; c.dataset.level = r.level || '';
    });
  }

  // FLIP: the other panels glide to their new places instead of jumping.
  function flip(grid, mutate, skip) {
    var kids = Array.prototype.slice.call(grid.children), before = new Map();
    kids.forEach(function (k) { before.set(k, k.getBoundingClientRect()); });
    mutate();
    if (reduce.matches) return;
    kids.forEach(function (k) {
      if (k === skip) return;
      var a = before.get(k), b = k.getBoundingClientRect(), dx = a.left - b.left, dy = a.top - b.top;
      if (dx || dy) k.animate([{ transform: 'translate(' + dx + 'px,' + dy + 'px)' }, { transform: 'none' }], { duration: 280, easing: EASE });
    });
  }
  function move(grid, card, toIndex) {
    var kids = Array.prototype.slice.call(grid.children), cur = kids.indexOf(card);
    if (toIndex === cur || toIndex < 0 || toIndex >= kids.length) return false;
    flip(grid, function () { var ref = kids[toIndex]; if (toIndex > cur) grid.insertBefore(card, ref.nextSibling); else grid.insertBefore(card, ref); }, card);
    layout.order = Array.prototype.map.call(grid.children, function (k) { return k.dataset.id; }).concat(layout.order.filter(function (id) { return layout.hidden[id]; }));
    save(); return true;
  }
  function wireKeys(btn, id) {
    btn.onkeydown = function (e) {
      if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown' && e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
      e.preventDefault(); var card = els[id], grid = card.parentNode, i = Array.prototype.indexOf.call(grid.children, card);
      move(grid, card, i + (e.key === 'ArrowUp' || e.key === 'ArrowLeft' ? -1 : 1)); btn.focus();
    };
  }
  function wireDrag(handle, card, grid) {
    handle.addEventListener('pointerdown', function (e) {
      if (e.button) return; e.preventDefault(); handle.setPointerCapture(e.pointerId);
      var r0 = card.getBoundingClientRect(), gx = e.clientX - r0.left, gy = e.clientY - r0.top, tx = 0, ty = 0;
      card.classList.add('lift'); card.style.transition = 'box-shadow .2s'; card.style.willChange = 'transform';
      if (!reduce.matches) card.animate([{ transform: 'scale(1)' }, { transform: 'scale(1.015)' }], { duration: 160, easing: EASE, fill: 'forwards' });
      function follow(ev) {
        var r = card.getBoundingClientRect(), lx = r.left - tx, ly = r.top - ty;
        tx = ev.clientX - gx - lx; ty = ev.clientY - gy - ly; card.style.translate = tx + 'px ' + ty + 'px';
      }
      var settled = 0;
      function over(ev) {
        // The panels glide for 280 ms after a move and their rectangles move with them, so a new target is
        // chosen only once they have settled; otherwise a panel sliding under the pointer swaps straight back.
        if (performance.now() < settled) return;
        var kids = Array.prototype.slice.call(grid.children);
        for (var i = 0; i < kids.length; i++) {
          if (kids[i] === card) continue; var kr = kids[i].getBoundingClientRect();
          if (ev.clientX > kr.left && ev.clientX < kr.right && ev.clientY > kr.top && ev.clientY < kr.bottom) {
            if (move(grid, card, i)) { settled = performance.now() + 300; follow(ev); }
            return;
          }
        }
      }
      function mv(ev) { follow(ev); over(ev); }
      function up() {
        removeEventListener('pointermove', mv); removeEventListener('pointerup', up); removeEventListener('pointercancel', up);
        var from = tx, fromY = ty;
        card.style.translate = ''; card.classList.remove('lift'); card.style.willChange = '';
        card.getAnimations().forEach(function (a) { a.cancel(); });
        if (!reduce.matches) card.animate([{ translate: from + 'px ' + fromY + 'px', transform: 'scale(1.015)' }, { translate: '0 0', transform: 'scale(1)' }], { duration: 300, easing: EASE });
      }
      // window, not the handle: moving the panel in the DOM drops the handle's pointer capture
      addEventListener('pointermove', mv); addEventListener('pointerup', up); addEventListener('pointercancel', up);
    });
  }

  var timer = null;
  function poll() {
    if (document.hidden || window.__hubViewSuspended) return;
    fetch('/api/home/state', { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
      if (!j) return; data = j; if (board) board.update(j); else paint();
    }).catch(function () {});
  }
  function useBoard() { return !phone.matches && window.__hubBoard; }
  function start() {
    if (useBoard()) { board = window.__hubBoard.mount(root); } else { build(); paint(); }
    poll(); timer = setInterval(poll, 10000); document.addEventListener('visibilitychange', poll);
  }
  phone.addEventListener('change', function () {
    if (board) { board.destroy(); board = null; }
    if (useBoard()) { board = window.__hubBoard.mount(root); if (data) board.update(data); } else { layout = load(); build(); paint(); }
  });
  window.__hubHomePanels = { refresh: poll, layout: function () { return JSON.parse(JSON.stringify(layout)); } };
  // First paint of Home is not made to wait for the panels: they start once the cube turn is over.
  (window.__hubWaitForTransition ? window.__hubWaitForTransition() : Promise.resolve()).then(function () { setTimeout(start, 250); });
})();
