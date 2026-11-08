/* Hand section of the website. A skeleton hand is drawn OVER an illustrative board, the way the dashboard draws it (same stage, letters and colours).
   The hand is built from a real hand's proportions and moved along hand-authored key poses with smooth easing, so it never jitters and always sits
   where the board expects it: the fingertip on what it points at, the pinch point on what it drags, the palm over what it pans.
   Four short scenes: start, point, drag (three-finger pinch), take control (fist, then pan, zoom and rotate in one run). Nothing here is a recording. */
(function () {
  'use strict';
  var NS = 'http://www.w3.org/2000/svg';
  var BONES = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[9,10],[10,11],[11,12],[13,14],[14,15],[15,16],[0,17],[17,18],[18,19],[19,20],[5,9],[9,13],[13,17]];
  var TIPS = [[4, 'T'], [8, 'I'], [12, 'M'], [16, 'R'], [20, 'P']];
  var AC = { left: '#00e676', drag: '#f5c842', pan: '#5aa0ff', zoom: '#c77dff', rotate: '#ff9d3b', control: '#ff9d3b' };
  var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var W = 1000, H = 380, HS = .78;

  function el(tag, attrs, parent) { var e = document.createElementNS(NS, tag); for (var k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function ease(t) { return t < 0 ? 0 : t > 1 ? 1 : t * t * (3 - 2 * t); }
  function rad(d) { return d * Math.PI / 180; }

  /* ---------- the hand: an open hand in local pixels (wrist at 0,0, fingers up), bent by curl numbers ---------- */
  var THUMB_OPEN = [[-34, -18], [-62, -56], [-82, -92], [-96, -124]];
  var THUMB_ACROSS = [[-34, -18], [-48, -40], [-30, -62], [-10, -74]];
  var FING = [ // base joint, spread angle (deg from straight up), segment lengths
    { b: [-26, -100], a: -6, l: [48, 30, 26] }, { b: [0, -108], a: 0, l: [54, 34, 28] },
    { b: [24, -102], a: 5, l: [48, 32, 26] }, { b: [46, -90], a: 11, l: [38, 24, 22] }];

  function finger(i, c, spread) {
    var f = FING[i], ang = rad(f.a * (spread == null ? 1 : spread)), dx = Math.sin(ang), dy = -Math.cos(ang);
    var p1 = c * 80, p2 = p1 + c * 85, p3 = p2 + c * 45;
    var P = [f.b.slice()], d = 0, cs = [Math.cos(rad(p1)), Math.cos(rad(p2)), Math.cos(rad(p3))];
    for (var s = 0; s < 3; s++) { d += f.l[s] * cs[s]; P.push([f.b[0] + dx * d - f.b[0] * .12 * c, f.b[1] + dy * d]); }
    return P; // MCP, PIP, DIP, TIP
  }
  function fabrik(chain, target) {
    var L = [], k; for (k = 0; k < 3; k++) L.push(Math.hypot(chain[k + 1][0] - chain[k][0], chain[k + 1][1] - chain[k][1]));
    var root = chain[0].slice(), P = chain.map(function (p) { return p.slice(); }), it, dist = Math.hypot(target[0] - root[0], target[1] - root[1]);
    if (dist > L[0] + L[1] + L[2]) { var u = [(target[0] - root[0]) / dist, (target[1] - root[1]) / dist]; for (k = 1; k < 4; k++) { var s = L[0] + (k > 1 ? L[1] : 0) + (k > 2 ? L[2] : 0); P[k] = [root[0] + u[0] * s, root[1] + u[1] * s]; } return P; }
    for (it = 0; it < 12; it++) {
      P[3] = target.slice();
      for (k = 2; k >= 0; k--) { var d = Math.hypot(P[k][0] - P[k + 1][0], P[k][1] - P[k + 1][1]) || 1, r = L[k] / d; P[k] = [P[k + 1][0] + (P[k][0] - P[k + 1][0]) * r, P[k + 1][1] + (P[k][1] - P[k + 1][1]) * r]; }
      P[0] = root.slice();
      for (k = 1; k < 4; k++) { var e = Math.hypot(P[k][0] - P[k - 1][0], P[k][1] - P[k - 1][1]) || 1, q = L[k - 1] / e; P[k] = [P[k - 1][0] + (P[k][0] - P[k - 1][0]) * q, P[k - 1][1] + (P[k][1] - P[k - 1][1]) * q]; }
    }
    return P;
  }
  // pose: c = [index, middle, ring, pinky] curls, th = thumb folded across (0..1), w = thumb touches the index+middle tips (0..1), sp = finger spread
  function local(p) {
    var F = [0, 1, 2, 3].map(function (i) { return finger(i, p.c[i], p.sp); });
    var meet = [(F[0][3][0] + F[1][3][0]) / 2, (F[0][3][1] + F[1][3][1]) / 2];
    var t0 = THUMB_OPEN.map(function (a, i) { return [lerp(a[0], THUMB_ACROSS[i][0], p.th), lerp(a[1], THUMB_ACROSS[i][1], p.th)]; });
    var t1 = fabrik(t0, meet), T = t0.map(function (a, i) { return [lerp(a[0], t1[i][0], p.w), lerp(a[1], t1[i][1], p.w)]; });
    var J = [[0, 0], T[0], T[1], T[2], T[3]];
    F.forEach(function (f) { f.forEach(function (q) { J.push(q); }); });
    var pinch = [(T[3][0] + F[0][3][0] + F[1][3][0]) / 3, (T[3][1] + F[0][3][1] + F[1][3][1]) / 3];
    return { J: J, pinch: pinch, index: F[0][3], palm: [0, -52] };
  }
  function place(p) { // wrist position, scale and turn from the anchor the scene wants on a given stage spot
    var L = local(p), a = rad(p.a), s = p.s, ca = Math.cos(a), sa = Math.sin(a);
    function R(v) { return [(v[0] * ca - v[1] * sa) * s, (v[0] * sa + v[1] * ca) * s]; }
    var an = p.on === 'idx' ? L.index : p.on === 'pinch' ? L.pinch : L.palm, r = R(an), wx = p.at[0] - r[0], wy = p.at[1] - r[1];
    var J = [];
    L.J.forEach(function (q) { var v = R(q); J.push(wx + v[0], wy + v[1]); });
    var pr = R(L.pinch), ir = R(L.index), pm = R(L.palm);
    return { J: J, pinch: [wx + pr[0], wy + pr[1]], index: [wx + ir[0], wy + ir[1]], palm: [wx + pm[0], wy + pm[1]] };
  }

  /* ---------- the scenes: key poses over time. Numbers between keys are eased, so motion is smooth by construction ---------- */
  var OPEN = [0.04, 0.04, 0.04, 0.04], POINT = [0, 1, 1, 1], FIST = [1, 1, 1, 1], TRI = [0.58, 0.62, 0.3, 0.3];
  function K(t, at, o) { var k = { t: t, at: at, c: OPEN, th: 0, w: 0, sp: 1, a: 0, s: HS, mode: '', tag: '' }; for (var q in o) k[q] = o[q]; if (o.s) k.s = o.s * HS; return k; }
  var BL = [[22, 78], [730, 78], [22, 245], [245, 245]], BW = 205, BH = 106;
  var CL = [BL[1][0] + 61, BL[1][1] + 83];
  var SCENES = {
    start: { dur: 3600, on: 'palm', keys: [
      K(0, [900, 470], { s: .95, a: 10 }), K(1200, [520, 215], {}), K(2600, [500, 200], { a: -3 }), K(3600, [500, 200], {})],
      note: 'In the Hub, start Hands explicitly. T, I, M, R and P label the fingertips.' },
    point: { dur: 5200, on: 'idx', keys: [
      K(0, [900, 470], { c: POINT, th: .8, s: .95 }), K(900, [560, 250], { c: POINT, th: .8 }), K(1900, CL, { c: POINT, th: .8, tag: 'aim' }),
      K(3100, CL, { c: POINT, th: .8, tag: 'dwell' }), K(3400, CL, { c: POINT, th: .8, tag: 'click' }), K(4400, [900, 470], { c: POINT, th: .8 }), K(5200, [900, 470], { c: POINT, th: .8 })],
      note: 'Point and hold: the ring fills, then it clicks.' },
    drag: { dur: 7800, on: 'pinch', keys: [
      K(0, [520, 470], { s: .95 }), K(900, [BL[0][0] + 105, BL[0][1] + 36], { sp: 1.1 }), K(1700, [BL[0][0] + 105, BL[0][1] + 36], { c: TRI, th: .1, w: 1, sp: .8, tag: 'grab' }),
      K(3800, [520, 170], { c: TRI, th: .1, w: 1, sp: .8, tag: 'move' }), K(4500, [520, 170], { c: TRI, th: .1, w: 1, sp: .8, tag: 'move' }),
      K(5200, [520, 170], { sp: 1.1, tag: 'drop' }), K(6200, [520, 470], { s: .95 }), K(7800, [520, 470], { s: .95 })],
      note: 'Thumb, index and middle together: the pinch point drags whatever it is on.' },
    control: { dur: 15200, on: 'palm', keys: [
      K(0, [500, 330], { s: .95 }), K(800, [500, 200], {}), K(1100, [500, 200], {}),
      K(2000, [500, 200], { c: FIST, th: 1, mode: 'control', tag: 'fist' }), K(3000, [500, 200], { c: FIST, th: 1, mode: 'control', tag: 'fist' }),
      K(3800, [500, 200], { mode: 'pan', tag: 'palm' }), K(4400, [500, 200], { mode: 'pan', tag: 'pan' }),
      K(5800, [650, 170], { mode: 'pan', tag: 'pan' }), K(7200, [380, 225], { mode: 'pan', tag: 'pan' }), K(7800, [500, 200], { mode: 'pan', tag: 'pan' }),
      K(8200, [500, 200], { mode: 'zoom', tag: 'zoom0' }), K(9400, [500, 200], { s: 1.3, mode: 'zoom', tag: 'zoom' }), K(10600, [500, 200], { s: .8, mode: 'zoom', tag: 'zoom' }), K(11200, [500, 200], { s: 1, mode: 'zoom', tag: 'zoom' }),
      K(11900, [500, 200], { c: FIST, th: 1, mode: 'control', tag: 'fist' }), K(12400, [500, 200], { c: FIST, th: 1, a: -26, mode: 'rotate', tag: 'rot' }),
      K(13300, [500, 200], { c: FIST, th: 1, a: 26, mode: 'rotate', tag: 'rot' }), K(14000, [500, 200], { c: FIST, th: 1, a: 0, mode: 'rotate', tag: 'rot' }),
      K(14500, [500, 200], {}), K(15200, [500, 200], {})],
      note: 'With fist control enabled, open your palm to pan or zoom. Turn a closed fist in View: 3D to tilt.' }
  };

  function sample(sc, ms) {
    var ks = sc.keys, i = 0;
    while (i < ks.length - 2 && ms > ks[i + 1].t) i++;
    var A = ks[i], B = ks[i + 1], u = ease((ms - A.t) / Math.max(1, B.t - A.t));
    var p = { on: sc.on, at: [lerp(A.at[0], B.at[0], u), lerp(A.at[1], B.at[1], u)], c: A.c.map(function (v, q) { return lerp(v, B.c[q], u); }),
      th: lerp(A.th, B.th, u), w: lerp(A.w, B.w, u), sp: lerp(A.sp, B.sp, u), a: lerp(A.a, B.a, u), s: lerp(A.s, B.s, u) };
    return { p: p, mode: u < .5 ? A.mode : B.mode, tag: u < .5 ? A.tag : B.tag };
  }

  function build(stage, name) {
    var sc = SCENES[name]; if (!sc) return;
    var boardSvg = stage.querySelector('.hand-board'), handSvg = stage.querySelector('.hand-skel'), wrap = stage.querySelector('.hand-boardwrap'), cap = stage.querySelector('.capture-label');
    boardSvg.textContent = ''; handSvg.textContent = '';
    var closeUp = {start:'330 0 630 355',point:'570 25 430 325',drag:'0 20 645 360',control:'195 0 610 380'};
    function frameBoard() {
      var view = stage.clientWidth < 450 ? closeUp[name] : '0 0 1000 380';
      boardSvg.setAttribute('viewBox', view);
      handSvg.setAttribute('viewBox', view);
    }
    frameBoard();
    var resize = new ResizeObserver(frameBoard);
    resize.observe(stage);
    if (cap) cap.textContent = sc.note;
    var defs = el('defs', {}, boardSvg);
    var dots = el('pattern', { id: 'hand-grid', width: 23, height: 23, patternUnits: 'userSpaceOnUse' }, defs);
    el('circle', { cx: 1, cy: 1, r: 1.2, fill: '#00e676', opacity: .22 }, dots);
    el('rect', { width: W, height: H, fill: '#07091d' }, boardSvg);
    el('rect', { width: W, height: H, fill: 'url(#hand-grid)' }, boardSvg);
    var g = el('g', {}, boardSvg);
    function text(parent, x, y, value, size, fill) {
      var t = el('text', { x: x, y: y, fill: fill || '#00e676', 'font-family': 'Outfit, sans-serif', 'font-size': size }, parent);
      t.textContent = value;
    }
    function control(parent, x, y, w, label, lit) {
      el('rect', { x: x, y: y, width: w, height: 24, rx: 6, fill: lit ? '#0a352d' : '#090e29', stroke: '#00e676', 'stroke-opacity': .48 }, parent);
      text(parent, x + 8, y + 16, label, 12);
    }
    function block(x, y, width, height, name, copy, detail) {
      var bg = el('g', { transform: 'translate(' + x + ' ' + y + ')' }, g);
      var box = el('rect', { width: width, height: height, rx: 5, fill: '#0a1028', 'fill-opacity': .9, stroke: '#00e676', 'stroke-opacity': .65, 'stroke-width': 2 }, bg);
      text(bg, 12, 22, name, 15);
      text(bg, width - 42, 22, '−  ×', 15, '#65ae94');
      el('path', { d: 'M0 30H' + width, stroke: '#00e676', 'stroke-opacity': .18 }, bg);
      text(bg, 12, 56, copy, 14, '#aed8cb');
      if (detail) control(bg, 12, 70, 98, detail);
      return { g: bg, box: box, x: x, y: y, x0: x, y0: y };
    }
    var blocks = [
      block(BL[0][0], BL[0][1], BW, BH, 'NEEDS ATTENTION', 'Nothing needs you right now.'),
      block(BL[1][0], BL[1][1], BW, BH, 'HEALTH', '● Hub running', 'SETTINGS'),
      block(BL[2][0], BL[2][1], BW, 73, 'Auto-LLM', 'Open missions'),
      block(BL[3][0], BL[3][1], BW, 73, 'File Browser', 'Open files')
    ];
    block(245, 78, 168, 86, 'RUNS', '0 missions running');
    block(430, 78, 282, 86, 'SESSIONS', 'No sessions need attention.');
    var chrome = el('g', {}, boardSvg);
    control(chrome, 383, 12, 173, 'AGENT HUB   ·   LIVE', true);
    control(chrome, 843, 12, 95, 'HANDS');
    control(chrome, 875, 202, 98, name === 'control' ? 'VIEW: 3D' : 'VIEW: 2D');
    control(chrome, 875, 233, 98, 'FIT');
    control(chrome, 875, 264, 98, 'TIDY');
    control(chrome, 875, 295, 98, 'BLOCKS');
    control(chrome, 875, 326, 98, 'LOG');
    var status = el('text', { x: 22, y: 353, fill: '#8edbc0', 'font-family': 'Outfit, sans-serif', 'font-size': 14 }, chrome);
    status.textContent = 'HANDS · LOCAL TRACKING PREVIEW';
    var palmPoly = el('polygon', { fill: '#41ebff', 'fill-opacity': .07, stroke: 'none' }, handSvg);
    var flash = el('circle', { r: 10, fill: 'none', stroke: AC.left, 'stroke-width': 4, opacity: 0 }, handSvg);
    var bones = BONES.map(function () { return el('line', { stroke: '#41ebff', 'stroke-width': 3.2, 'stroke-linecap': 'round', opacity: .6 }, handSvg); });
    var palmRing = el('circle', { r: 30, fill: 'none', 'stroke-width': 3 }, handSvg);
    var pinchDot = el('circle', { r: 9, fill: AC.drag, opacity: 0 }, handSvg), pinchRing = el('circle', { r: 17, fill: 'none', stroke: AC.drag, 'stroke-width': 3, opacity: 0 }, handSvg);
    var cursor = el('circle', { r: 16, fill: 'none', 'stroke-width': 3, opacity: 0 }, handSvg), dwell = el('path', { fill: 'none', 'stroke-width': 4, 'stroke-linecap': 'round', opacity: 0 }, handSvg);
    var tipEls = TIPS.map(function (t) {
      var c = el('circle', { r: 9, fill: '#080c28', stroke: '#41ebff', 'stroke-width': 1.7 }, handSvg), x = el('text', { 'text-anchor': 'middle', 'font-family': 'Orbitron,monospace', 'font-size': 10, 'font-weight': 700, fill: '#41ebff' }, handSvg);
      x.textContent = t[1]; return { c: c, t: x, k: t[0] };
    });
    var pill = el('rect', { rx: 3, height: 20, fill: '#080c28', 'fill-opacity': .92, 'stroke-width': 1.4 }, handSvg), label = el('text', { 'text-anchor': 'middle', 'font-family': 'Orbitron,monospace', 'font-size': 12, 'font-weight': 700 }, handSvg);
    // The dwell click opens the same illustrative Settings screen on every viewport.
    var settings = null;
    if (name === 'point') {
      settings = document.createElement('section');
      settings.className = 'hand-click-result';
      settings.hidden = true;
      settings.setAttribute('aria-label', 'Demo Settings screen');
      settings.innerHTML = '<img src="assets/previews/hand-click-settings.png" alt="Agent Hub Settings showing the Appearance section">';
      stage.appendChild(settings);
    }
    var t0 = performance.now(), pause = 700, held = null, frame = 0;

    function draw(ms) {
      var S = sample(sc, ms), P = place(S.p), J = P.J, tag = S.tag, mode = S.mode;
      BONES.forEach(function (b, i) { var l = bones[i]; l.setAttribute('x1', J[b[0] * 2]); l.setAttribute('y1', J[b[0] * 2 + 1]); l.setAttribute('x2', J[b[1] * 2]); l.setAttribute('y2', J[b[1] * 2 + 1]); });
      palmPoly.setAttribute('points', [0, 1, 5, 9, 13, 17].map(function (k) { return J[k * 2] + ',' + J[k * 2 + 1]; }).join(' '));
      var pinching = S.p.w > .7, big = { 4: pinching, 8: pinching, 12: pinching };
      tipEls.forEach(function (t) { var x = J[t.k * 2], y = J[t.k * 2 + 1], h = big[t.k]; t.c.setAttribute('cx', x); t.c.setAttribute('cy', y); t.c.setAttribute('r', h ? 11 : 9); t.c.setAttribute('fill', h ? '#41ebff' : '#080c28'); t.t.setAttribute('x', x); t.t.setAttribute('y', y + 3.6); t.t.setAttribute('fill', h ? '#080c28' : '#41ebff'); });
      // what the hand is doing, as the dashboard labels it
      var txt = '', col = AC.left, ring = false;
      if (name === 'point') txt = tag === 'click' ? 'CLICK' : '';
      if (name === 'drag' && (tag === 'grab' || tag === 'move')) { txt = 'DRAG'; col = AC.drag; }
      if (name === 'control') {
        if (mode === 'control') { txt = 'CONTROL'; col = AC.control; ring = true; }
        else if (mode === 'pan') { txt = tag === 'pan' ? 'PAN' : 'OPEN PALM'; col = AC.pan; ring = true; }
        else if (mode === 'zoom') { txt = tag === 'zoom0' ? 'OPEN PALM' : 'ZOOM'; col = AC.zoom; ring = true; }
        else if (mode === 'rotate') { txt = 'ROTATE'; col = AC.rotate; ring = true; }
      }
      var pc = P.palm;
      palmRing.setAttribute('cx', pc[0]); palmRing.setAttribute('cy', pc[1]); palmRing.setAttribute('stroke', col); palmRing.setAttribute('opacity', ring ? 1 : 0);
      var lx = name === 'drag' ? P.pinch[0] : name === 'point' ? P.index[0] : pc[0], ly = (name === 'drag' ? P.pinch[1] : name === 'point' ? P.index[1] : pc[1]) + (name === 'control' ? 62 : 36), tw = txt.length * 9 + 16;
      label.textContent = txt; label.setAttribute('x', lx); label.setAttribute('y', ly + 4); label.setAttribute('fill', col);
      pill.setAttribute('x', lx - tw / 2); pill.setAttribute('y', ly - 11); pill.setAttribute('width', tw); pill.setAttribute('stroke', col);
      pill.setAttribute('opacity', txt ? 1 : 0); label.setAttribute('opacity', txt ? 1 : 0);
      // the pinch point, which is what carries the dragged block
      var showP = name === 'drag' && S.p.w > .05;
      pinchDot.setAttribute('cx', P.pinch[0]); pinchDot.setAttribute('cy', P.pinch[1]); pinchDot.setAttribute('opacity', showP ? S.p.w : 0);
      pinchRing.setAttribute('cx', P.pinch[0]); pinchRing.setAttribute('cy', P.pinch[1]); pinchRing.setAttribute('opacity', showP && (tag === 'grab' || tag === 'move') ? 1 : 0);
      // pointing: cursor on the fingertip, a ring that fills while it holds, a flash when it clicks
      var tip = P.index, isPoint = name === 'point', prog = 0;
      cursor.setAttribute('opacity', isPoint ? 1 : 0); cursor.setAttribute('cx', tip[0]); cursor.setAttribute('cy', tip[1]); cursor.setAttribute('stroke', AC.left);
      if (isPoint) { prog = Math.max(0, Math.min(1, (ms - 1900) / 1200)); if (ms > 3400) prog = 0; }
      dwell.setAttribute('opacity', prog > 0 && prog < 1 ? 1 : 0); dwell.setAttribute('stroke', AC.left);
      var a = -Math.PI / 2, b = a + Math.max(prog, .001) * Math.PI * 1.999, r = 28;
      dwell.setAttribute('d', 'M' + (tip[0] + r * Math.cos(a)) + ' ' + (tip[1] + r * Math.sin(a)) + ' A' + r + ' ' + r + ' 0 ' + (prog > .5 ? 1 : 0) + ' 1 ' + (tip[0] + r * Math.cos(b)) + ' ' + (tip[1] + r * Math.sin(b)));
      if (settings) settings.hidden = ms < 3400;
      var fl = isPoint && ms > 3400 && ms < 4200 ? (ms - 3400) / 800 : -1;
      flash.setAttribute('opacity', fl >= 0 ? 1 - fl : 0); flash.setAttribute('cx', tip[0]); flash.setAttribute('cy', tip[1]); flash.setAttribute('r', 14 + Math.max(0, fl) * 60);
      // the board answers the hand: the palm pans it, the hand's size zooms it, the fist's turn rotates it
      var tx = 0, ty = 0, zoom = 1, ry = 0;
      if (name === 'control') {
        if (mode === 'pan' && tag === 'pan') { tx = pc[0] - 500; ty = pc[1] - 200; }
        if (mode === 'zoom') zoom = Math.pow(S.p.s, 1.7);
        if (mode === 'rotate') ry = S.p.a * 1.35;
      }
      g.setAttribute('transform', 'translate(' + (500 + tx) + ' ' + (190 + ty) + ') scale(' + zoom + ') translate(-500 -190)');
      wrap.style.transform = 'perspective(1100px) rotateY(' + ry.toFixed(1) + 'deg)';
      blocks.forEach(function (bk, i) {
        if (name === 'drag' && i === 0) {
          if (tag === 'grab' || tag === 'move') { if (!held) held = { dx: bk.x - P.pinch[0], dy: bk.y - P.pinch[1] }; bk.x = P.pinch[0] + held.dx; bk.y = P.pinch[1] + held.dy; }
        }
        bk.g.setAttribute('transform', 'translate(' + bk.x + ' ' + bk.y + ')');
        var hot = (name === 'drag' && i === 0 && (tag === 'grab' || tag === 'move')) ? AC.drag : (name === 'point' && i === 1 && (prog > 0 || fl >= 0)) ? AC.left : (name === 'control' && mode === 'control') ? AC.control : '#00e676';
        bk.box.setAttribute('stroke', hot); bk.box.setAttribute('stroke-opacity', hot === '#00e676' ? .65 : 1); bk.box.setAttribute('stroke-width', hot === '#00e676' ? 2.5 : 4.5);
      });
    }
    function tick(now) {
      if (!document.body.contains(stage)) return;
      var ms = (now - t0) % (sc.dur + pause);
      if (ms > sc.dur) ms = sc.dur;
      if (ms < 40) { held = null; blocks.forEach(function (b) { b.x = b.x0; b.y = b.y0; }); }
      draw(ms);
      frame = requestAnimationFrame(tick);
    }
    if (reduce) draw(name === 'control' ? 2500 : name === 'drag' ? 3000 : name === 'point' ? 3900 : 2400);
    else frame = requestAnimationFrame(tick);
    return function () { cancelAnimationFrame(frame); resize.disconnect(); };
  }

  window.HubHandPlayer = function (host) {
    var stage = host && host.querySelector('.hand-stage');
    if (stage) return build(stage, stage.dataset.clip);
  };
})();
