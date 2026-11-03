// How you move around the board. CLASSIC is what the board always did (wheel moves, Ctrl + wheel zooms, drag the background to pan).
//   CAD  the wheel zooms toward the pointer, the middle button drags the board, a double middle-click fits everything (SolidWorks style)
//   3D   CAD plus a tilt (Blender style): the middle button (the wheel pressed in) or right-drag orbits up to 40 degrees, Shift + middle-drag pans,
//        Alt + wheel tilts and Alt + Shift + wheel turns; blocks sit at a depth by kind
//        (needs-attention near, health and usage far); pointer rays meet each pane's own depth plane
// The axis gizmo (CAD and 3D) does the same with one finger or one mouse button: drag it to orbit (3D) or pan, tap an axis to look along it,
// RESET to come back flat and fit. The choice is kept in localStorage 'agenthub:board:nav'. This is a prototype: CLASSIC stays the default.
(function () {
  var KEY = 'agenthub:board:nav', ORDER = ['classic', 'cad', '3d'], NAME = { classic: 'VIEW', cad: 'VIEW: CAD', '3d': 'VIEW: 3D' };
  var TITLE = {
    classic: 'CLASSIC: wheel moves, Ctrl + wheel zooms, drag the background to pan. Click for CAD: wheel zooms, middle-drag pans.',
    cad: 'Wheel zooms toward the pointer, middle-drag (or the gizmo) pans, double middle-click fits. Click for 3D.',
    '3d': 'CAD plus tilt: middle-drag or right-drag orbits, Shift + middle-drag pans, Alt + wheel tilts, blocks sit at a depth. Click for CLASSIC.'
  };
  var LIM = 40, PERSP = 1500, PREVIEW = [16, -20];
  var CSS = '.hb-3d{perspective:' + PERSP + 'px}.hb-3d .hb-world{transform-style:preserve-3d}.hb-3d .hk{content-visibility:visible;translate:0 0 var(--hb-dz,0px)}'
    + ".hb-3d .hk[data-id=att]{--hb-dz:150px}.hb-3d .hk[data-id=runs],.hb-3d .hk[data-id=ses]{--hb-dz:65px}.hb-3d .hk[data-id=hlt],.hb-3d .hk[data-id=use]{--hb-dz:-100px}"
    + '.hb-gizmo{position:absolute;right:12px;bottom:112px;z-index:8;width:144px;display:none;flex-direction:column;align-items:center;gap:3px;touch-action:none;user-select:none;-webkit-user-select:none}'
    + '.hb-gizmo.on{display:flex}.hb-gizmo svg{width:104px;height:104px;border-radius:50%;background:rgba(6,10,36,.62);border:1px solid var(--border-dim,rgba(0,230,118,.28));cursor:grab;-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px)}'
    + '.hb-gizmo.drag svg{cursor:grabbing}.hb-gizmo .gz-tools{display:flex;gap:3px;width:100%}'
    + ".hb-gizmo .gz-tools button{flex:1 1 0;font:700 8px Orbitron,monospace;letter-spacing:.4px;padding:4px 2px;min-height:36px;color:var(--text-muted,#8fcfb2);background:rgba(6,10,36,.74);border:1px solid var(--border-dim,rgba(0,230,118,.28));border-radius:6px;cursor:pointer}"
    + '.hb-gizmo .gz-tools button.on{color:var(--accent,#00e676);border-color:var(--accent,#00e676)}.hb-gizmo [data-snap]{cursor:pointer}.gz-readout{font:700 8px/1.7 Orbitron,monospace;text-align:center;color:var(--cyan,#41ebff)}'
    + '.hb-3d .hk{transform-style:preserve-3d;box-shadow:0 18px 32px rgba(0,0,0,.45)}.hb-3d .hk.tile{--hb-dz:20px}.hb-3d .hk.exp{--hb-dz:170px}'
    + '.hk-solid{display:none;position:absolute;inset:0;pointer-events:none;transform-style:preserve-3d}.hb-3d .hk-solid{display:block}.hk-solid i{position:absolute;display:block;box-sizing:border-box;border:1px solid #148d91;backface-visibility:visible}.hk-solid .back{inset:0;transform:translateZ(-36px);background:#082d46}.hk-solid .left,.hk-solid .right{top:0;width:36px;height:100%;transform-origin:left center;transform:rotateY(90deg);background:linear-gradient(90deg,#126d88,#071e39)}.hk-solid .left{left:0}.hk-solid .right{left:100%}.hk-solid .top,.hk-solid .bottom{left:0;width:100%;height:36px;transform-origin:center top;transform:rotateX(-90deg);background:linear-gradient(#137f88,#06344b)}.hk-solid .top{top:0}.hk-solid .bottom{top:100%}'
    + '@media (pointer:coarse){.hb-gizmo{width:132px}.hb-gizmo svg{width:124px;height:124px}.hb-gizmo .gz-tools button{min-height:44px;padding:6px 3px}}';
  function load() { try { var v = localStorage.getItem(KEY); return ORDER.indexOf(v) >= 0 ? v : 'classic'; } catch (e) { return 'classic'; } }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function sv(tag, attrs, parent) { var e = document.createElementNS('http://www.w3.org/2000/svg', tag); for (var k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; }
  var rad = Math.PI / 180;
  // the board's own rotation, as the CSS applies it: rotateX(rx) rotateY(ry); a point is turned about Y first, then X
  function turn(p, rx, ry) {
    var x = p[0] * Math.cos(ry * rad) + p[2] * Math.sin(ry * rad), z = -p[0] * Math.sin(ry * rad) + p[2] * Math.cos(ry * rad), y = p[1];
    return [x, y * Math.cos(rx * rad) - z * Math.sin(rx * rad), y * Math.sin(rx * rad) + z * Math.cos(rx * rad)];
  }

  function mount(c) {
    if (!document.getElementById('hb-view-css')) { var st = el('style'); st.id = 'hb-view-css'; st.textContent = CSS; document.head.appendChild(st); }
    var host = c.host, mode = load(), rx = 0, ry = 0, tool = 'orbit', flat = 0, ac = new AbortController(), sig = { signal: ac.signal };
    var btn = el('button', 'hb-btn', NAME[mode]); btn.type = 'button';
    var gz = el('div', 'hb-gizmo'), svg = sv('svg', { viewBox: '-52 -52 104 104', role: 'img', 'aria-label': 'Axes: drag to move around the board' }, gz);
    var readout = el('output', 'gz-readout'); readout.setAttribute('aria-label', 'Board rotation'); gz.appendChild(readout);
    var tools = el('div', 'gz-tools'), tOrbit = el('button', '', 'ORBIT'), tPan = el('button', '', 'PAN'), tReset = el('button', '', 'RESET');
    [tOrbit, tPan, tReset].forEach(function (b) { b.type = 'button'; tools.appendChild(b); }); gz.append(svg, tools); host.appendChild(gz);
    tOrbit.title = 'Dragging the axes turns the board'; tPan.title = 'Dragging the axes moves the board'; tReset.title = 'Flat again, and everything in view';

    function paintGizmo() {
      readout.textContent = (mode === '3d' ? 'DRAG TO ORBIT' : 'DRAG TO PAN') + ' · ' + Math.round(rx) + ' / ' + Math.round(ry) + ' DEG';
      svg.textContent = '';
      sv('circle', { cx: 0, cy: 0, r: 2.4, fill: 'rgba(217,255,233,.5)' }, svg);
      var axes = [['x', [1, 0, 0], '#ff5c5c', 'X'], ['y', [0, -1, 0], '#5fe08a', 'Y'], ['z', [0, 0, 1], '#3ba7ff', 'Z']], pts = [];
      axes.forEach(function (a) { [1, -1].forEach(function (s) { var p = turn([a[1][0] * s, a[1][1] * s, a[1][2] * s], rx, ry); pts.push({ a: a, s: s, x: p[0] * 33, y: p[1] * 33, z: p[2] }); }); });
      pts.sort(function (p, q) { return p.z - q.z; });
      pts.forEach(function (p) {
        var g = sv('g', { 'data-snap': p.a[0] + (p.s > 0 ? '+' : '-') }, svg);
        sv('line', { x1: 0, y1: 0, x2: p.x, y2: p.y, stroke: p.a[2], 'stroke-width': p.s > 0 ? 2.2 : 1, 'stroke-opacity': p.s > 0 ? .95 : .4, 'stroke-linecap': 'round' }, g);
        sv('circle', { cx: p.x, cy: p.y, r: p.s > 0 ? 8.5 : 4.5, fill: p.s > 0 ? p.a[2] : 'none', 'fill-opacity': p.s > 0 ? .85 : 0, stroke: p.a[2], 'stroke-opacity': p.s > 0 ? 1 : .55, 'stroke-width': 1.2 }, g);
        if (p.s > 0) { var t = sv('text', { x: p.x, y: p.y + 3.4, 'text-anchor': 'middle', 'font-size': 9.5, 'font-weight': 700, fill: '#06102a', 'font-family': 'Orbitron,monospace', 'pointer-events': 'none' }, g); t.textContent = p.a[3]; }
      });
    }
    function toolPaint() { tOrbit.classList.toggle('on', tool === 'orbit' && mode === '3d'); tPan.classList.toggle('on', tool === 'pan' || mode === 'cad'); tOrbit.hidden = mode !== '3d'; }
    function apply(initial) {
      host.classList.toggle('hb-3d', mode === '3d');
      host.classList.toggle('hb-cad', mode !== 'classic');
      gz.classList.toggle('on', mode !== 'classic');
      btn.textContent = NAME[mode]; btn.title = TITLE[mode]; btn.classList.toggle('on', mode !== 'classic');
      if (mode !== '3d') { rx = ry = 0; }
      toolPaint(); paintGizmo(); if (!initial) c.place();
    }
    // entering 3D leans the board to a preview angle at once, so the depth is seen without having to find the right button first
    function setMode(m) { mode = m; try { localStorage.setItem(KEY, m); } catch (e) {} tool = m === '3d' ? 'orbit' : 'pan'; apply(); if (m === '3d') tiltTo(PREVIEW[0], PREVIEW[1], 450); }
    btn.onclick = function () { setMode(ORDER[(ORDER.indexOf(mode) + 1) % ORDER.length]); };

    function clampTilt() { rx = Math.max(-LIM, Math.min(LIM, rx)); ry = Math.max(-LIM, Math.min(LIM, ry)); }
    function orbit(dx, dy) { if (mode !== '3d') return; ++flat; c.stop(); ry += dx * .25; rx -= dy * .25; clampTilt(); paintGizmo(); c.place(); }
    function pan(dx, dy) { c.stop(); var V = c.V(); V.x += dx; V.y += dy; c.place(); }
    // eased move of the tilt to (tx, ty); the board is left where it is
    function tiltTo(tx, ty, ms) {
      var t0 = performance.now(), fx = rx, fy = ry, token = ++flat;
      if (!ms || !c.motion.allowed()) { rx = tx; ry = ty; paintGizmo(); c.place(); return; }
      (function s(n) { if (token !== flat) return; var u = Math.min(1, (n - t0) / ms), e = 1 - Math.pow(1 - u, 3); rx = fx + (tx - fx) * e; ry = fy + (ty - fy) * e; paintGizmo(); c.place(); if (u < 1) requestAnimationFrame(s); })(t0);
    }
    function flatten() { if (rx || ry) { ++flat; rx = ry = 0; paintGizmo(); c.place(); } }       // at once: a block pressed while the board is tilted must be where it is drawn
    function snap(code) {
      var s = code[1] === '+' ? 1 : -1;
      if (code[0] === 'z') return tiltTo(0, 0, 240);
      if (mode !== '3d') return;
      if (code[0] === 'x') return tiltTo(0, -LIM * s, 280);      // looking along the board's width
      return tiltTo(LIM * s, 0, 280);                            // 'y': looking along its height
    }

    // ---- gizmo: drag moves or turns the board, a tap on an axis looks along it
    var gdrag = null;
    svg.addEventListener('pointerdown', function (e) {
      if (e.button) return; e.preventDefault(); e.stopPropagation(); ++flat;
      var hit = e.target.closest && e.target.closest('[data-snap]');
      gdrag = { id: e.pointerId, x: e.clientX, y: e.clientY, sx: e.clientX, sy: e.clientY, moved: false, snap: hit ? hit.getAttribute('data-snap') : null };
      try { svg.setPointerCapture(e.pointerId); } catch (x) {} gz.classList.add('drag');
    }, sig);
    svg.addEventListener('pointermove', function (e) {
      if (!gdrag || e.pointerId !== gdrag.id) return;
      var dx = e.clientX - gdrag.x, dy = e.clientY - gdrag.y; gdrag.x = e.clientX; gdrag.y = e.clientY;
      if (!gdrag.moved && Math.hypot(e.clientX - gdrag.sx, e.clientY - gdrag.sy) < 4) return;
      gdrag.moved = true; (mode === '3d' && tool === 'orbit' ? orbit : pan)(dx, dy);
    }, sig);
    function gup(e) { if (!gdrag || e.pointerId !== gdrag.id) return; var d = gdrag; gdrag = null; gz.classList.remove('drag'); if (!d.moved && d.snap && e.type === 'pointerup') snap(d.snap); }
    svg.addEventListener('pointerup', gup, sig); svg.addEventListener('pointercancel', gup, sig); svg.addEventListener('lostpointercapture', gup, sig);
    tOrbit.onclick = function () { tool = 'orbit'; toolPaint(); };
    tPan.onclick = function () { tool = 'pan'; toolPaint(); };
    tReset.onclick = function () { tiltTo(0, 0, 240); c.fit(true); };

    // ---- the mouse: middle drags the board, right turns it (3D), a block pressed while tilted flattens it first
    var lastMid = 0;
    host.addEventListener('pointerdown', function (e) {
      if (mode === 'classic') return;
      if (e.target.closest('.hb-bar,.hb-tray,.hb-gizmo,.hb-map,.hb-jump')) return;
      // Pane controls and grabs retain the chosen orientation.
      var middle = e.button === 1, right = e.button === 2 && mode === '3d' && !e.target.closest('.hk');
      if (!middle && !right) return;
      e.preventDefault(); c.touch(); c.stop();
      var turnIt = right || (middle && !e.shiftKey && mode === '3d'), lx = e.clientX, ly = e.clientY, sx = lx, sy = ly, moved = false, id = e.pointerId;
      host.classList.add('panning');
      function mv(ev) { if (ev.pointerId !== id) return; var dx = ev.clientX - lx, dy = ev.clientY - ly; lx = ev.clientX; ly = ev.clientY; if (Math.abs(ev.clientX - sx) + Math.abs(ev.clientY - sy) > 3) moved = true; (turnIt ? orbit : pan)(dx, dy); }
      function up(ev) {
        if (ev.pointerId !== id) return; removeEventListener('pointermove', mv); removeEventListener('pointerup', up); removeEventListener('pointercancel', up); host.classList.remove('panning');
        if (middle && !moved) { var now = performance.now(); if (now - lastMid < 380) { lastMid = 0; tiltTo(0, 0, 200); c.fit(true); } else lastMid = now; }
      }
      addEventListener('pointermove', mv); addEventListener('pointerup', up); addEventListener('pointercancel', up);
    }, { signal: ac.signal, capture: true });
    host.addEventListener('mousedown', function (e) { if (mode !== 'classic' && e.button === 1 && !e.target.closest('.hb-bar,.hb-tray,.hb-gizmo')) e.preventDefault(); }, sig);       // no browser auto-scroll circle
    host.addEventListener('auxclick', function (e) { if (mode !== 'classic' && e.button === 1) e.preventDefault(); }, sig);
    host.addEventListener('contextmenu', function (e) { if (mode === '3d' && !e.target.closest('.hk,.hb-bar,.hb-tray')) e.preventDefault(); }, sig);

    tool = mode === '3d' ? 'orbit' : 'pan'; if (mode === '3d') { rx = PREVIEW[0]; ry = PREVIEW[1]; } apply(true);
    return {
      btn: btn,
      mode: function () { return mode; },
      tilt: function () { return { rx: rx, ry: ry }; },
      setMode: setMode,
      // the world's transform: unchanged when flat, so CLASSIC is exactly what it was
      transform: function (V) {
        var base = 'translate3d(' + V.x + 'px,' + V.y + 'px,0) ' + (mode === '3d' ? 'scale3d(' + V.k + ',' + V.k + ',' + V.k + ')' : 'scale(' + V.k + ')');
        if (!rx && !ry) return base;
        var cx = host.clientWidth / 2, cy = host.clientHeight / 2;
        return 'translate3d(' + cx + 'px,' + cy + 'px,0) rotateX(' + rx + 'deg) rotateY(' + ry + 'deg) translate3d(' + (-cx) + 'px,' + (-cy) + 'px,0) ' + base;
      },
      // the wheel in CAD and 3D zooms toward the pointer; Shift + wheel still pans sideways; Ctrl + wheel / a pinch is left to the board
      wheel: function (e, target, r, aim) {
        if (mode === '3d' && e.altKey) { var d = (e.shiftKey ? e.deltaX || e.deltaY : e.deltaY) * (e.deltaMode === 1 ? 32 : 1); if (e.shiftKey) orbit(-d * .12, 0); else orbit(0, -d * .12); return true; }
        if (mode === 'classic' || e.ctrlKey || e.shiftKey) return false;
        var dy = e.deltaMode === 1 ? e.deltaY * 32 : e.deltaY, k = Math.min(2.6, Math.max(.3, target.k * Math.exp(-dy * .0018))), px = e.clientX - r.left, py = e.clientY - r.top;
        aim({ x: px - (px - target.x) * k / target.k, y: py - (py - target.y) * k / target.k, k: k }); return true;
      },
      // Inverse perspective ray / pane-plane intersection. No layout reads while following the pointer.
      toWorld: function (x, y, z, rect) {
        var V=c.V(), dx=x-rect.left-host.clientWidth/2, dy=y-rect.top-host.clientHeight/2;
        if(mode!=='3d')return {x:(x-rect.left-V.x)/V.k,y:(y-rect.top-V.y)/V.k};
        var cx=Math.cos(rx*rad),sx=Math.sin(rx*rad),cy=Math.cos(ry*rad),sy=Math.sin(ry*rad);
        var a=sy*dx-cy*sx*dy,b=cy*cx*PERSP,t=(z*V.k-b)/(a-b);
        var ux=cy*dx*t+sy*sx*dy*t-sy*cx*PERSP*(1-t),uy=cx*dy*t+sx*PERSP*(1-t);
        return {x:(ux+host.clientWidth/2-V.x)/V.k,y:(uy+host.clientHeight/2-V.y)/V.k};
      },
      flatten: flatten,
      destroy: function () { ac.abort(); gz.remove(); host.classList.remove('hb-3d', 'hb-cad'); }
    };
  }
  window.__hubBoardView = { mount: mount };
})();
