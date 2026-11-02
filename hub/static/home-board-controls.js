// Board camera inertia and neighbour guides. Work stops as soon as the camera settles.
(function () {
  function camera(read, paint, allowed) {
    var raf = 0, target = null, velocity = null, last = 0;
    function stop() { if (raf) cancelAnimationFrame(raf); raf = 0; target = velocity = null; last = 0; }
    function tick(now) {
      raf = 0; var v = read(), dt = last ? Math.min(40, now - last) : 16; last = now;
      if (target) {
        var a = 1 - Math.exp(-dt / 65); ['x', 'y', 'k'].forEach(function (key) { v[key] += (target[key] - v[key]) * a; });
        if (Math.abs(target.x - v.x) + Math.abs(target.y - v.y) < .2 && Math.abs(target.k - v.k) < .0005) { Object.assign(v, target); target = null; }
      } else if (velocity) {
        v.x += velocity.x * dt; v.y += velocity.y * dt; var resistance = Math.exp(-dt / 145); velocity.x *= resistance; velocity.y *= resistance;
        if (Math.hypot(velocity.x, velocity.y) < .015) velocity = null;
      }
      paint(); if (target || velocity) raf = requestAnimationFrame(tick); else last = 0;
    }
    function run() { if (!raf) raf = requestAnimationFrame(tick); }
    return { stop: stop, target: function () { return target && Object.assign({}, target); },
      aim: function (to) { if (!allowed()) { stop(); Object.assign(read(), to); paint(); return; } target = to; velocity = null; run(); },
      coast: function (x, y) { if (!allowed()) return; stop(); velocity = { x: Math.max(-2, Math.min(2, x)), y: Math.max(-2, Math.min(2, y)) }; run(); }
    };
  }
  function guides(host, layouts, hidden, read) {
    var layer = document.createElement('div'); layer.className = 'hb-guides'; layer.setAttribute('aria-hidden', 'true');
    var xline = document.createElement('i'), yline = document.createElement('i'); xline.className = 'vertical'; yline.className = 'horizontal'; layer.append(xline, yline); host.appendChild(layer);
    function clear() { xline.hidden = yline.hidden = true; }
    function snap(id, commit) {
      clear(); var l = layouts[id], v = read(), threshold = 7 / v.k, dx = null, dy = null, gx = 0, gy = 0;
      Object.keys(layouts).forEach(function (other) {
        if (other === id || hidden[other]) return; var n = layouts[other];
        [l.x, l.x + l.w].forEach(function (a) { [n.x, n.x + n.w].forEach(function (b) { if (Math.abs(b - a) < threshold && (dx === null || Math.abs(b - a) < Math.abs(dx))) { dx = b - a; gx = b; } }); });
        [l.y, l.y + l.h].forEach(function (a) { [n.y, n.y + n.h].forEach(function (b) { if (Math.abs(b - a) < threshold && (dy === null || Math.abs(b - a) < Math.abs(dy))) { dy = b - a; gy = b; } }); });
      });
      if (dx !== null) { l.x += dx * (commit ? 1 : .65); xline.hidden = false; xline.style.left = v.x + gx * v.k + 'px'; }
      if (dy !== null) { l.y += dy * (commit ? 1 : .65); yline.hidden = false; yline.style.top = v.y + gy * v.k + 'px'; }
      if (commit) clear();
    }
    clear(); return { snap: snap, clear: clear, destroy: function () { layer.remove(); } };
  }
  window.__hubBoardControls = { camera: camera, guides: guides };
})();
