/* Hand section of the website: plays a real hand recording (joint numbers only) as an animated skeleton drawn OVER an illustrative board,
   the way the dashboard draws it. Both use the same coordinates (a 1000 x 700 stage), so the hand and the board agree.
   Clips are in hand-clips.js, cut from the owner's own recordings by tools/build_hand_clips.py. The board is an illustration, not a capture. */
(function () {
  'use strict';
  var NS = 'http://www.w3.org/2000/svg';
  var BONES = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[9,10],[10,11],[11,12],[13,14],[14,15],[15,16],[0,17],[17,18],[18,19],[19,20],[5,9],[9,13],[13,17]];
  var TIPS = [[4, 'T'], [8, 'I'], [12, 'M'], [16, 'R'], [20, 'P']];
  var AC = { left: '#00e676', pan: '#5aa0ff', zoom: '#c77dff', rotate: '#ff9d3b', control: '#ff9d3b' };
  var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var W = 1000, H = 700;

  function el(tag, attrs, parent) { var e = document.createElementNS(NS, tag); for (var k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function frameAt(clip, t) {
    var n = clip.frames.length, f = t * (n - 1), i = Math.max(0, Math.min(n - 2, Math.floor(f))), u = f - i, A = clip.frames[i], B = clip.frames[i + 1];
    return { j: A.j.map(function (v, q) { return lerp(v, B.j[q], u); }), px: lerp(A.px, B.px, u), py: lerp(A.py, B.py, u), k: lerp(A.k, B.k, u), tw: lerp(A.tw, B.tw, u), pi: lerp(A.pi, B.pi, u), on: u < .5 ? A.on : B.on, fist: u < .5 ? A.fist : B.fist };
  }
  function mid(J, a, b) { return { x: (J[a * 2] + J[b * 2]) / 2, y: (J[a * 2 + 1] + J[b * 2 + 1]) / 2 }; }
  function palmOf(J) { return { x: (J[0] + J[10] + J[18] + J[26] + J[34]) / 5, y: (J[1] + J[11] + J[19] + J[27] + J[35]) / 5 }; }

  function player(stage, name) {
    var clips = window.HAND_CLIPS;
    if (!clips || !clips[name]) return;
    var clip = clips[name], boardSvg = stage.querySelector('.hand-board'), handSvg = stage.querySelector('.hand-skel'), wrap = stage.querySelector('.hand-boardwrap');
    boardSvg.textContent = ''; handSvg.textContent = '';
    var first = frameAt(clip, 0);
    // ---- the board (illustration)
    var g = el('g', {}, boardSvg);
    for (var gx = 0; gx <= W; gx += 100) el('line', { x1: gx, y1: 0, x2: gx, y2: H, stroke: '#41ebff', 'stroke-opacity': .09 }, g);
    for (var gy = 0; gy <= H; gy += 100) el('line', { x1: 0, y1: gy, x2: W, y2: gy, stroke: '#41ebff', 'stroke-opacity': .09 }, g);
    var NAMES = ['MISSIONS', 'GIT GRAPH', 'AGENTS', 'HANDS'];
    // where the hand is when it acts, so the block it works on sits under it
    var onI = -1;
    clip.frames.forEach(function (f, i) { if (onI < 0 && f.on) onI = i; });
    var tipOn = onI >= 0 ? { x: clip.frames[onI].j[16], y: clip.frames[onI].j[17] } : { x: first.j[16], y: first.j[17] };
    var spots = [[90, 70], [660, 90], [110, 440], [650, 430]];
    if (name === 'point') { var m = frameAt(clip, .5); spots[0] = [m.j[16] - 100, m.j[17] - 55]; }
    if (name === 'pinch') spots[0] = [tipOn.x - 100, tipOn.y - 30];
    var blocks = NAMES.map(function (n, i) {
      var bg = el('g', {}, g), x = spots[i][0], y = spots[i][1];
      el('rect', { x: 0, y: 0, width: 210, height: 130, rx: 9, fill: '#0b1220', stroke: '#00e676', 'stroke-opacity': .6, 'stroke-width': 2.5 }, bg);
      el('rect', { x: 0, y: 0, width: 210, height: 28, rx: 9, fill: '#00e676', 'fill-opacity': .15 }, bg);
      var t = el('text', { x: 12, y: 19, fill: '#00e676', 'font-family': 'Orbitron,sans-serif', 'font-size': 13, 'font-weight': 700 }, bg); t.textContent = n;
      for (var r = 0; r < 3; r++) el('rect', { x: 14, y: 48 + r * 24, width: 120 + r * 18 - r * 12, height: 7, rx: 3.5, fill: '#41ebff', 'fill-opacity': .25 }, bg);
      return { g: bg, x: x, y: y, x0: x, y0: y };
    });
    // ---- the hand, over the board
    var bones = BONES.map(function () { return el('line', { stroke: '#41ebff', 'stroke-width': 3, 'stroke-linecap': 'round', opacity: .55 }, handSvg); });
    var pinchLine = el('line', { 'stroke-width': 4, 'stroke-linecap': 'round' }, handSvg);
    var palmRing = el('circle', { r: 26, fill: 'none', 'stroke-width': 3 }, handSvg);
    var tipEls = TIPS.map(function (t) {
      var c = el('circle', { r: 8, fill: '#080c28', stroke: '#41ebff', 'stroke-width': 1.6 }, handSvg);
      var x = el('text', { 'text-anchor': 'middle', 'font-family': 'Orbitron,monospace', 'font-size': 9.5, 'font-weight': 700, fill: '#41ebff' }, handSvg); x.textContent = t[1];
      return { c: c, t: x, k: t[0] };
    });
    var pill = el('rect', { rx: 3, height: 18, fill: '#080c28', 'fill-opacity': .9, 'stroke-width': 1.3 }, handSvg);
    var label = el('text', { 'text-anchor': 'middle', 'font-family': 'Orbitron,monospace', 'font-size': 11, 'font-weight': 700 }, handSvg);
    var cursor = el('circle', { r: 16, fill: 'none', 'stroke-width': 3, opacity: 0 }, handSvg);
    var dwell = el('path', { fill: 'none', 'stroke-width': 4, 'stroke-linecap': 'round', opacity: 0 }, handSvg);

    var dur = clip.ms * clip.frames.length, t0 = performance.now(), shown = null, pause = 900, onMid = onI >= 0 ? mid(clip.frames[onI].j, 4, 8) : null;
    function modeOf(f) {
      if (name === 'point') return { t: '', c: AC.left };
      if (name === 'pinch') return f.on ? { t: 'DRAG', c: AC.left } : { t: 'CLICK / DRAG', c: AC.left, soft: true };
      if (name === 'fist') return { t: 'CONTROL', c: AC.control };
      if (name === 'pan') return { t: 'PAN', c: AC.pan };
      if (name === 'zoom') return { t: 'ZOOM', c: AC.zoom };
      return { t: 'ROTATE', c: AC.rotate };
    }
    function draw(f, u) {
      // ease toward the target so the last bit of jitter in the numbers does not show
      if (!shown) shown = f.j.slice(); else for (var q = 0; q < f.j.length; q++) shown[q] += (f.j[q] - shown[q]) * .55;
      var J = shown, mo = modeOf(f), pc = palmOf(J);
      BONES.forEach(function (b, i) { var l = bones[i]; l.setAttribute('x1', J[b[0] * 2]); l.setAttribute('y1', J[b[0] * 2 + 1]); l.setAttribute('x2', J[b[1] * 2]); l.setAttribute('y2', J[b[1] * 2 + 1]); });
      var hot = { 4: f.on, 8: f.on && name === 'pinch' };
      tipEls.forEach(function (t) { var x = J[t.k * 2], y = J[t.k * 2 + 1], h = hot[t.k]; t.c.setAttribute('cx', x); t.c.setAttribute('cy', y); t.c.setAttribute('r', h ? 10 : 8); t.c.setAttribute('fill', h ? '#41ebff' : '#080c28'); t.t.setAttribute('x', x); t.t.setAttribute('y', y + 3.4); t.t.setAttribute('fill', h ? '#080c28' : '#41ebff'); });
      pinchLine.setAttribute('x1', J[8]); pinchLine.setAttribute('y1', J[9]); pinchLine.setAttribute('x2', J[16]); pinchLine.setAttribute('y2', J[17]);
      pinchLine.setAttribute('stroke', AC.left); pinchLine.setAttribute('stroke-opacity', f.on ? 1 : .25);
      var ring = name !== 'point';
      palmRing.setAttribute('cx', pc.x); palmRing.setAttribute('cy', pc.y); palmRing.setAttribute('stroke', mo.c);
      palmRing.setAttribute('stroke-dasharray', mo.soft ? '5 5' : ''); palmRing.setAttribute('opacity', ring ? (mo.soft ? .65 : 1) : 0);
      var txt = mo.t, tw = txt.length * 8 + 14, py = pc.y + 46;
      label.textContent = txt; label.setAttribute('x', pc.x); label.setAttribute('y', py + 3); label.setAttribute('fill', mo.c);
      pill.setAttribute('x', pc.x - tw / 2); pill.setAttribute('y', py - 11); pill.setAttribute('width', tw); pill.setAttribute('stroke', mo.c); pill.setAttribute('opacity', txt ? 1 : 0); label.setAttribute('opacity', txt ? 1 : 0);
      // the board answers the hand
      var tx = 0, ty = 0, sc = 1, rx = 0, ry = 0, p0 = palmOf(first.j);
      if (name === 'pan') { tx = pc.x - p0.x; ty = pc.y - p0.y; }
      if (name === 'zoom') sc = Math.max(.6, Math.min(1.9, Math.pow(f.k, 2.2)));
      if (name === 'turn') { ry = f.tw * 55; rx = -f.pi * 80; }
      g.setAttribute('transform', 'translate(' + (W / 2 + tx) + ' ' + (H / 2 + ty) + ') scale(' + sc + ') translate(' + (-W / 2) + ' ' + (-H / 2) + ')');
      wrap.style.transform = 'perspective(1100px) rotateY(' + ry.toFixed(1) + 'deg) rotateX(' + rx.toFixed(1) + 'deg)';
      var tip = { x: J[16], y: J[17] };
      cursor.setAttribute('opacity', name === 'point' || name === 'pinch' ? 1 : 0); cursor.setAttribute('cx', tip.x); cursor.setAttribute('cy', tip.y); cursor.setAttribute('stroke', f.on ? '#f5c842' : AC.left);
      if (name === 'point') {
        var prog = Math.max(0, Math.min(1, (u - .3) / .5));
        dwell.setAttribute('opacity', prog > 0 ? 1 : 0); dwell.setAttribute('stroke', AC.left);
        var a = -Math.PI / 2, b = a + prog * Math.PI * 1.999, r = 26;
        dwell.setAttribute('d', 'M' + (tip.x + r * Math.cos(a)) + ' ' + (tip.y + r * Math.sin(a)) + ' A' + r + ' ' + r + ' 0 ' + (prog > .5 ? 1 : 0) + ' 1 ' + (tip.x + r * Math.cos(b)) + ' ' + (tip.y + r * Math.sin(b)));
      } else dwell.setAttribute('opacity', 0);
      if (name === 'pinch' && onMid) {
        var pm = mid(J, 4, 8);
        if (f.on) { blocks[0].x = blocks[0].x0 + (pm.x - onMid.x); blocks[0].y = blocks[0].y0 + (pm.y - onMid.y); blocks[0].held = { x: blocks[0].x, y: blocks[0].y }; }
        else if (blocks[0].held) { blocks[0].x = blocks[0].held.x; blocks[0].y = blocks[0].held.y; }
      }
      blocks.forEach(function (b, i) {
        b.g.setAttribute('transform', 'translate(' + b.x + ' ' + b.y + ')');
        b.g.firstChild.setAttribute('stroke', (name === 'pinch' && i === 0 && f.on) ? '#f5c842' : name === 'fist' ? '#ff9d3b' : '#00e676');
      });
    }
    function reset() { blocks.forEach(function (b) { b.x = b.x0; b.y = b.y0; b.held = null; }); shown = null; }
    function tick(now) {
      if (!document.body.contains(stage)) return;
      var cycle = dur + pause, u = (((now - t0) % cycle) + cycle) % cycle / dur;
      if (u < .02) reset();
      u = Math.min(1, u);
      draw(frameAt(clip, u), u);
      requestAnimationFrame(tick);
    }
    if (reduce) { draw(frameAt(clip, .55), .55); return; }
    requestAnimationFrame(tick);
  }

  window.HubHandPlayer = function (host) {
    var stage = host && host.querySelector('.hand-stage');
    if (stage) player(stage, stage.dataset.clip);
  };
})();
