/* Hand section of the website: plays a real hand recording (joint numbers only) as an animated skeleton next to an illustrative board.
   The clips are in hand-clips.js, cut from the owner's own recordings by tools/build_hand_clips.py. The board is an illustration, not a capture. */
(function () {
  'use strict';
  var NS = 'http://www.w3.org/2000/svg';
  var BONES = [[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[9,10],[10,11],[11,12],[13,14],[14,15],[15,16],[0,17],[17,18],[18,19],[19,20],[5,9],[9,13],[13,17]];
  var TIPS = { 4: '#ffffff', 8: '#00e676', 12: '#f5c842' };
  var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  var BLOCKS = [[110, 150, 'MISSIONS'], [470, 120, 'GIT GRAPH'], [250, 460, 'HANDS'], [620, 470, 'AGENTS']];

  function el(tag, attrs, parent) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function lerp(a, b, t) { return a + (b - a) * t; }
  function frameAt(clip, t) {
    var n = clip.frames.length, f = t * (n - 1), i = Math.min(n - 2, Math.floor(f)), u = f - i, A = clip.frames[i], B = clip.frames[i + 1];
    var j = A.j.map(function (v, q) { return lerp(v, B.j[q], u); });
    return { j: j, px: lerp(A.px, B.px, u), py: lerp(A.py, B.py, u), k: lerp(A.k, B.k, u), tw: lerp(A.tw, B.tw, u), pi: lerp(A.pi, B.pi, u), on: u < .5 ? A.on : B.on, fist: u < .5 ? A.fist : B.fist };
  }

  function player(host, name) {
    var stage = host.querySelector('.hand-stage'), clips = window.HAND_CLIPS;
    if (!stage || !clips || !clips[name]) return;
    var clip = clips[name], skel = stage.querySelector('.hand-skel'), board = stage.querySelector('.hand-board'), chip = stage.querySelector('.hand-chip'), wrap = stage.querySelector('.hand-boardwrap');
    skel.textContent = ''; board.textContent = '';
    // skeleton
    var bones = BONES.map(function () { return el('line', { stroke: '#41ebff', 'stroke-width': 7, 'stroke-linecap': 'round', opacity: .6 }, skel); });
    var joints = []; for (var q = 0; q < 21; q++) joints.push(el('circle', { r: TIPS[q] ? 15 : 8, fill: TIPS[q] || '#41ebff' }, skel));
    var line = el('line', { stroke: '#00e676', 'stroke-width': 4, 'stroke-linecap': 'round' }, skel);
    var palm = el('circle', { r: 40, fill: 'none', 'stroke-width': 6, stroke: '#ff9d3b', opacity: 0 }, skel);
    // board (illustration): a grid and four blocks, moved by the hand
    var g = el('g', {}, board);
    for (var gx = 0; gx <= 1000; gx += 100) { el('line', { x1: gx, y1: 0, x2: gx, y2: 1000, stroke: '#41ebff', 'stroke-opacity': .1 }, g); el('line', { x1: 0, y1: gx, x2: 1000, y2: gx, stroke: '#41ebff', 'stroke-opacity': .1 }, g); }
    var blocks = BLOCKS.map(function (b) {
      var bg = el('g', {}, g);
      el('rect', { x: 0, y: 0, width: 230, height: 150, rx: 10, fill: '#0b1220', stroke: '#00e676', 'stroke-opacity': .6, 'stroke-width': 3 }, bg);
      el('rect', { x: 0, y: 0, width: 230, height: 30, rx: 10, fill: '#00e676', 'fill-opacity': .15 }, bg);
      var t = el('text', { x: 14, y: 21, fill: '#00e676', 'font-family': 'Orbitron,sans-serif', 'font-size': 15, 'font-weight': 700 }, bg); t.textContent = b[2];
      for (var r = 0; r < 3; r++) el('rect', { x: 16, y: 54 + r * 26, width: 130 + r * 30 - r * 20, height: 8, rx: 4, fill: '#41ebff', 'fill-opacity': .25 }, bg);
      return { g: bg, x: b[0], y: b[1] };
    });
    var cursor = el('circle', { r: 20, fill: 'none', stroke: '#00e676', 'stroke-width': 5, opacity: 0 }, board);
    var dwell = el('circle', { r: 30, fill: 'none', stroke: '#00e676', 'stroke-width': 7, opacity: 0, 'stroke-dasharray': '0 999', transform: 'rotate(-90)' }, board);
    chip.textContent = clip.label;
    var dur = clip.ms * clip.frames.length, t0 = performance.now(), grab = null, held = 0;

    function draw(f, u) {
      var J = f.j;
      BONES.forEach(function (b, i) { var l = bones[i]; l.setAttribute('x1', J[b[0] * 2]); l.setAttribute('y1', J[b[0] * 2 + 1]); l.setAttribute('x2', J[b[1] * 2]); l.setAttribute('y2', J[b[1] * 2 + 1]); });
      for (var q = 0; q < 21; q++) { joints[q].setAttribute('cx', J[q * 2]); joints[q].setAttribute('cy', J[q * 2 + 1]); }
      line.setAttribute('x1', J[8]); line.setAttribute('y1', J[9]); line.setAttribute('x2', J[16]); line.setAttribute('y2', J[17]);
      line.setAttribute('stroke-opacity', f.on ? 1 : .25); joints[4].setAttribute('r', f.on ? 22 : 15);
      var cx = (J[0] + J[18] + J[10]) / 3, cy = (J[1] + J[19] + J[11]) / 3;
      palm.setAttribute('cx', cx); palm.setAttribute('cy', cy);
      palm.setAttribute('opacity', f.fist || name === 'pan' || name === 'zoom' ? .9 : 0);
      palm.setAttribute('stroke', name === 'pan' ? '#41ebff' : name === 'zoom' ? '#00e676' : '#ff9d3b');
      palm.setAttribute('stroke-dasharray', f.fist ? '' : '14 10');
      // board
      var tx = 0, ty = 0, sc = 1, rx = 0, ry = 0;
      if (name === 'pan') { tx = f.px * 1500; ty = f.py * 1500; }
      if (name === 'zoom') sc = Math.max(.6, Math.min(1.9, Math.pow(f.k, 2.2)));
      if (name === 'turn') { ry = f.tw * 55; rx = -f.pi * 80; }
      g.setAttribute('transform', 'translate(' + (500 + tx) + ' ' + (500 + ty) + ') scale(' + sc + ') translate(-500 -500)');
      wrap.style.transform = 'perspective(900px) rotateY(' + ry.toFixed(1) + 'deg) rotateX(' + rx.toFixed(1) + 'deg)';
      var tipx = J[16] , tipy = J[17];
      var inx = Math.max(60, Math.min(940, tipx)), iny = Math.max(60, Math.min(940, tipy));
      if (name === 'point' || name === 'pinch') {
        cursor.setAttribute('opacity', 1); cursor.setAttribute('cx', inx); cursor.setAttribute('cy', iny); cursor.setAttribute('stroke', f.on ? '#f5c842' : '#00e676');
        var over = null; blocks.forEach(function (b, i) { if (inx > b.x - 20 && inx < b.x + 250 && iny > b.y - 20 && iny < b.y + 170) over = i; });
        if (name === 'point') {
          held = over === null ? 0 : held + 1;
          dwell.setAttribute('opacity', over === null ? 0 : 1); dwell.setAttribute('cx', inx); dwell.setAttribute('cy', iny);
          var circ = 2 * Math.PI * 30, prog = Math.min(1, held / 18);
          dwell.setAttribute('stroke-dasharray', (circ * prog).toFixed(1) + ' ' + circ); dwell.setAttribute('transform', 'rotate(-90 ' + inx + ' ' + iny + ')');
        }
        if (name === 'pinch') {
          if (f.on && grab === null && over !== null) grab = { i: over, dx: inx - blocks[over].x, dy: iny - blocks[over].y };
          if (!f.on) grab = null;
          if (grab) { blocks[grab.i].x = inx - grab.dx; blocks[grab.i].y = iny - grab.dy; }
        }
      } else { cursor.setAttribute('opacity', 0); dwell.setAttribute('opacity', 0); }
      blocks.forEach(function (b, i) {
        b.g.setAttribute('transform', 'translate(' + b.x + ' ' + b.y + ')');
        b.g.firstChild.setAttribute('stroke', grab && grab.i === i ? '#f5c842' : name === 'fist' ? '#ff9d3b' : '#00e676');
      });
    }
    function reset() { blocks.forEach(function (b, i) { b.x = BLOCKS[i][0]; b.y = BLOCKS[i][1]; }); grab = null; held = 0; }
    function tick(now) {
      if (!document.body.contains(stage)) return;
      var u = (((now - t0) % (dur + 900)) + dur + 900) % (dur + 900) / dur;
      if (u < .02) reset();
      u=Math.max(0,u);draw(frameAt(clip, Math.min(1, u)), u);
      requestAnimationFrame(tick);
    }
    if (reduce) { draw(frameAt(clip, .55), .55); return; }
    requestAnimationFrame(tick);
  }

  window.HubHandPlayer = function (host, step) {
    var stage = host && host.querySelector('.hand-stage');
    if (stage) player(host, stage.dataset.clip);
  };
})();
