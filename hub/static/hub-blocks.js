// Shared block treatment. Decoration never changes a block's layout or runs while idle.
(function () {
  if (window.HubBlocks) return;
  var reduce = matchMedia('(prefers-reduced-motion: reduce)'), KEY = 'agenthub:block-arrival';
  function allowed() { try { return !reduce.matches && !(window.DepthLift && DepthLift.software) && !(window.frameElement && parent.DepthLift && parent.DepthLift.software); } catch (e) { return !reduce.matches; } }
  function edge(root) {
    var raf = 0, hit = null, event = null;
    function clear() { if (raf) cancelAnimationFrame(raf); raf = 0; if (hit) hit.classList.remove('is-hover'); hit = null; }
    function paint() { raf = 0; if (!event || !allowed()) return clear(); var b = event.target.closest('.hub-block'); if (!b) return clear(); if (hit && hit !== b) hit.classList.remove('is-hover'); hit = b;
      var r = b.getBoundingClientRect(), x = (event.clientX - r.left) / r.width, y = (event.clientY - r.top) / r.height;
      b.style.setProperty('--edge-x', x * 100 + '%'); b.style.setProperty('--edge-y', y * 100 + '%'); b.style.setProperty('--depth-x', (x - .5) * 2 + 'px'); b.style.setProperty('--depth-y', (y - .5) * 2 + 'px'); b.classList.add('is-hover');
    }
    function move(e) { if (e.pointerType === 'touch') { clear(); return; } event = e; if (!raf) raf = requestAnimationFrame(paint); }
    root.addEventListener('pointermove', move); root.addEventListener('pointerleave', clear);
    return function () { clear(); root.removeEventListener('pointermove', move); root.removeEventListener('pointerleave', clear); };
  }
  function grid(host, v) { host.style.setProperty('--grid-x', (allowed() ? v.x * .06 : 0) + 'px'); host.style.setProperty('--grid-y', (allowed() ? v.y * .06 : 0) + 'px'); }
  function remember(nodes) {
    var ids = { attention:'att', runs:'runs', sessions:'ses', health:'hlt', usage:'use' }, out = [];
    nodes.forEach(function (e) { var id = ids[e.dataset.id], r = e.getBoundingClientRect(); if (id && r.width && !e._fading) out.push({ id:id, left:r.left, top:r.top, width:r.width, height:r.height }); });
    if (!out.length) return;
    try { sessionStorage.setItem(KEY, JSON.stringify({ at:Date.now(), blocks:out })); } catch (e) {}
  }
  function prepare(blocks) {
    var ticket; try { ticket = JSON.parse(sessionStorage.getItem(KEY) || 'null'); } catch (e) {} if (!ticket || Date.now() - ticket.at > 10000 || !allowed()) return function () {};
    var staged = [];
    ticket.blocks.forEach(function (r) { var b = blocks[r.id]; if (b) { staged.push([b,b.style.visibility]); b.style.visibility='hidden'; b.dataset.arrivalPending='1'; } });
    var timer=setTimeout(release,4500);
    function release(){clearTimeout(timer);staged.forEach(function(x){x[0].style.visibility=x[1];delete x[0].dataset.arrivalPending;});staged=[];}
    return release;
  }
  async function arrive(blocks, scale, release) {
    var ticket; try { ticket = JSON.parse(sessionStorage.getItem(KEY) || 'null'); } catch (e) {} if (!ticket || Date.now() - ticket.at > 10000) { if (release) release(); return; }
    if (window.__hubWaitForTransition) await __hubWaitForTransition();
    try { sessionStorage.removeItem(KEY); } catch (e) {} if (release) release(); if (!allowed() || !window.__hubBoardMotion) return;
    ticket.blocks.forEach(function (r) { var b = blocks[r.id]; if (b && b.isConnected) { b.dataset.arrived = '1'; __hubBoardMotion.flip(b, r, scale(), 'arrival'); } });
  }
  // Rehouse the existing notice without changing Depth Lift or its dismiss/fade timers.
  function dockNotice(n) {
    if (n.id === 'hub-graphics-chip' || n.getAttribute('role') !== 'status' || !/^This browser is drawing graphics in software/.test(n.textContent)) return;
    var detail = n.textContent, dock = document.querySelector('.hb-bar');
    if (!dock) { dock = document.querySelector('.hub-notice-dock'); if (!dock) { dock = document.createElement('div'); dock.className = 'hub-notice-dock'; document.body.appendChild(dock); } }
    document.__hubGraphicsShown = true; n.id = 'hub-graphics-chip'; n.classList.add('hub-notice-chip'); n.title = detail; n.setAttribute('aria-label', detail);
    if (n.firstChild && n.firstChild.nodeType === 3) n.firstChild.textContent = 'SOFTWARE GRAPHICS';
    var opacity = n.style.opacity;
    n.style.cssText = 'display:inline-flex;align-items:center;gap:8px;position:relative;pointer-events:none;opacity:' + (opacity || '0') + ';transition:opacity .6s ease';
    var close = n.querySelector('button');
    if (close) { close.innerHTML = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>'; close.style.cssText = 'position:static;display:grid;place-items:center;width:22px;height:22px;border:0;background:none;color:inherit;pointer-events:auto;cursor:pointer'; }
    dock.appendChild(n);
  }
  if (document.body) {
    Array.from(document.body.children).forEach(dockNotice);
    var noticeObserver = new MutationObserver(function (changes) { changes.forEach(function (change) { change.addedNodes.forEach(function (n) { if (n.nodeType === 1) dockNotice(n); }); }); });
    noticeObserver.observe(document.body, {childList:true});
    addEventListener('pagehide', function () { noticeObserver.disconnect(); }, {once:true});
  }
  function graphics() {
    if (document.__hubGraphicsShown || document.getElementById('hub-graphics-chip')) return;
    var ctl; try { ctl = window.frameElement ? parent.DepthLift : window.DepthLift; } catch (e) {} if (!ctl || !ctl.software) return;
    document.__hubGraphicsShown = true;
    var n = document.createElement('div'); n.setAttribute('role','status'); n.textContent = 'This browser is drawing graphics in software (' + (ctl.renderer || 'software renderer') + '). Fully quit and reopen the browser to restore hardware rendering.';
    var b = document.createElement('button'); b.type='button'; b.setAttribute('aria-label','Hide this notice');
    function gone() { if (reduce.matches) { n.remove(); return; } n.style.opacity='0'; setTimeout(function(){n.remove();},650); }
    b.onclick=gone; n.appendChild(b); n.style.opacity='0'; document.body.appendChild(n); dockNotice(n); setTimeout(function(){n.style.opacity='1';},50);setTimeout(gone,15000);
  }
  window.HubBlocks = { allowed:allowed, edge:edge, grid:grid, remember:remember, prepare:prepare, arrive:arrive, graphics:graphics };
})();
