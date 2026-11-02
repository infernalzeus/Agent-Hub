// Finite board animations. No idle animation loop and no permanent compositor hints.
(function () {
  var reduce = matchMedia('(prefers-reduced-motion: reduce)');
  function allowed() {
    try { return !reduce.matches && !(window.DepthLift && DepthLift.software) && !(window.frameElement && parent.DepthLift && parent.DepthLift.software); }
    catch (e) { return !reduce.matches; }
  }
  function flip(block, before, scale, kind) {
    if (block._flip) block._flip.cancel();
    if (!allowed()) return;
    var after = block.getBoundingClientRect();
    if (!after.width || !before.width) return;
    block.dataset.motion = kind; block.style.willChange = 'transform';
    var a = block.animate([
      { opacity: kind === 'arrival' ? 0 : 1, transformOrigin: '0 0', transform: 'translate(' + (before.left - after.left) / scale + 'px,' + (before.top - after.top) / scale + 'px) scale(' + before.width / after.width + ',' + before.height / after.height + ')' },
      { opacity: 1, transformOrigin: '0 0', transform: 'none' }
    ], { duration: kind === 'drop' ? 260 : 380, easing: kind === 'drop' ? 'cubic-bezier(.34,1.45,.64,1)' : 'cubic-bezier(.2,.8,.2,1)' });
    block._flip = a;
    function done() { if (block._flip !== a) return; delete block.dataset.motion; block._flip = null; if (!block.classList.contains('pick')) block.style.willChange = ''; }
    a.onfinish = a.oncancel = done;
  }
  function skeleton(label) {
    var e = document.createElement('div'); e.className = 'hb-skeleton' + (allowed() ? '' : ' still'); e.setAttribute('role', 'status'); e.setAttribute('aria-label', label || 'Loading');
    for (var i = 0; i < 3; i++) e.appendChild(document.createElement('i')); return e;
  }
  function number(node, from, to) {
    node.dataset.value = String(to);
    if (!allowed() || from == null || from === to) { node.textContent = String(to); return; }
    var start = performance.now();
    function tick(now) { if (!node.isConnected) return; var p = Math.min(1, (now - start) / 320); node.textContent = String(Math.round(from + (to - from) * (1 - Math.pow(1 - p, 3)))); if (p < 1) requestAnimationFrame(tick); }
    node.textContent = String(from); requestAnimationFrame(tick);
  }
  function frame(f) {
    if (f._wait) f._wait.remove();
    var wait = f._wait = skeleton('Loading tool'); wait.classList.add('hk-loading'); delete f.dataset.ready; f.setAttribute('aria-busy','true');
    requestAnimationFrame(function () { if (f.isConnected && !f.dataset.ready) f.before(wait); });
    f.style.opacity = '0'; f.style.transition = allowed() ? 'opacity .22s ease' : 'none';
    if (f._loadBound) return; f._loadBound = true;
    f.addEventListener('load', function () {
      f.style.opacity = '1'; f.dataset.ready = '1'; f.removeAttribute('aria-busy'); var wait = f._wait;
      if (!wait) return; f._wait = null;
      if (allowed() && wait.isConnected) wait.animate([{opacity:1},{opacity:0}],{duration:180}).onfinish=function(){wait.remove();}; else wait.remove();
    });
  }
  window.__hubBoardMotion = { allowed: allowed, flip: flip, frame: frame, skeleton: skeleton, number: number };
})();
