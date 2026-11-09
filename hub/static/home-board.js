// Home board (desktop): the overview panels and your app icons as blocks on a canvas.
// The wheel zooms toward the pointer, dragging the background pans, a block is picked up by its title (an app icon by
// its body), double-click a title to focus one block, the corner resizes, the cross hides it into the tray.
// Every width uses the board; hidden legacy cards still host the borrowed app controls.
(function () {
  var touchScreen=matchMedia('(pointer:coarse)');
  var TW = 224, PEEK = 0, EASE = 'cubic-bezier(.2,.8,.2,1)', SPRING = 'cubic-bezier(.34,1.45,.64,1)', KEY = 'agenthub:board:v2';
  var reduce = matchMedia('(prefers-reduced-motion: reduce)'), motion = window.__hubBoardMotion;
  var P = { // default sizes; positions come from grid(), heights grow to fit what is inside
    att: { t: 'NEEDS ATTENTION', w: 380, h: 110 }, runs: { t: 'RUNS', w: 210, h: 100 }, ses: { t: 'SESSIONS', w: 320, h: 110 },
    hlt: { t: 'HEALTH', w: 280, h: 130 }, use: { t: 'CLAUDE CODE USAGE', w: 380, h: 120 }
  };
  var ICON = { stop: 'M7 7h10v10H7z', col: 'M6 15l6-6 6 6', dup: 'M9 9h10v10H9zM5 15V5h10', out: 'M7 17 17 7M9 7h8v8', move: 'M9 5h.01M9 12h.01M9 19h.01M15 5h.01M15 12h.01M15 19h.01', min: 'M6 12h12', foc: 'M5 9V5h4M19 9V5h-4M5 15v4h4M19 15v4h-4', x: 'M6 6l12 12M18 6 6 18' };
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function svg(d, w) { var s = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('aria-hidden', 'true'); s.style.cssText = 'width:13px;height:13px;fill:none;stroke:currentColor;stroke-width:' + (w || 1.8) + ';stroke-linecap:round;stroke-linejoin:round'; var p = document.createElementNS('http://www.w3.org/2000/svg', 'path'); p.setAttribute('d', d); s.appendChild(p); return s; }
  // Window-title pictures by what the window is (same line style as the website's architecture diagram); the Doctor's cross is the Support window's.
  var TITLE_ICON = { support: 'M10 4h4v6h6v4h-6v6h-4v-6H4v-4h6z', mission: 'M5 21V4M5 4h11l-2 4 2 4H5', graph: 'M4 6a2 2 0 1 0 4 0 2 2 0 0 0-4 0zM16 8a2 2 0 1 0 4 0 2 2 0 0 0-4 0zM10 18a2 2 0 1 0 4 0 2 2 0 0 0-4 0zM7.5 7.5l3.5 9M17 9.5L13.5 16.5', agent: 'M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM3 20c0-3 3-5 6-5s6 2 6 5M17 11a3 3 0 1 0 0-6M21 20c0-2-1.5-4-4-4.6', skill: 'M4 5h6a2 2 0 0 1 2 2v13a2 2 0 0 0-2-2H4zM20 5h-6a2 2 0 0 0-2 2v13a2 2 0 0 1 2-2h6z', media: 'M12 4v11M7 11l5 5 5-5M5 20h14', file: 'M3 6h6l2 2h10v11H3z', hand: 'M8 13V5a1.5 1.5 0 0 1 3 0v6M11 11V4a1.5 1.5 0 0 1 3 0v7M14 11V6a1.5 1.5 0 0 1 3 0v8c0 4-2 7-6 7s-4-2-6-5l-1-2a1.5 1.5 0 0 1 2.5-1.5L8 14', routine: 'M4 9a8 8 0 0 1 14-3l2 2M20 4v4h-4M20 15a8 8 0 0 1-14 3l-2-2M4 20v-4h4', schedule: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2', talk: 'M12 3a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM6 11a6 6 0 0 0 12 0M12 17v4', desktop: 'M3 4h18v12H3zM8 21h8M12 16v5' };
  var PANEL_ICON = { att: 'M12 3 2.5 20h19L12 3Zm0 6v5m0 3v.01', runs: 'M5 4l14 8-14 8V4Z', ses: 'M4 5h16v10H4zM8 19h8M12 15v4', hlt: 'M3 12h4l2-6 4 12 2-6h6', use: 'M5 20V11M12 20V4M19 20v-6' };
  // Inline vector symbols share the header's metal tile; an app name stays outside the icon.
  var APPLET_ICON={
    'movie-clipper':'M4 5h16v15H4zM4 10h16M7 5l3 5M13 5l3 5M10 13l5 2-5 3z',
    'file-browser':'M3 7V5h7l2 3h9v12H3V7z',
    oc:'M9 4a3 3 0 0 0-5 3 4 4 0 0 0 0 7 3 3 0 0 0 5 5M15 4a3 3 0 0 1 5 3 4 4 0 0 1 0 7 3 3 0 0 1-5 5M9 3v18M15 3v18M9 8H6M15 13h4',
    ytdl:'M12 3v12M7 10l5 5 5-5M4 16v5h16v-5',yt:'M12 15V3M7 8l5-5 5 5M4 16v5h16v-5'
  };
  function appTile(a){var s=svg(APPLET_ICON[a.id]||'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z',2.2);s.setAttribute('class','tile');return s;}
  function cardIcon(headerId) {
    var h = document.getElementById(headerId), src = h && h.querySelector('.card-emoji svg'); if (!src) return null;
    var n = (cardIcon.n = (cardIcon.n || 0) + 1), c = src.cloneNode(true); c.innerHTML = c.innerHTML.replace(/id="([^"]+)"/g, 'id="$1-b' + n + '"').replace(/url\(#([^)]+)\)/g, 'url(#$1-b' + n + ')');
    c.removeAttribute('width'); c.removeAttribute('height'); c.setAttribute('class', 'cardicon'); c.style.cssText = 'width:30px;height:30px'; return c;
  }
  function ago(s) { return s < 90 ? s + 's' : s < 5400 ? Math.round(s / 60) + 'm' : s < 172800 ? Math.round(s / 3600) + 'h' : Math.round(s / 86400) + 'd'; }
  function li(level, a, b, tag) { var d = el(tag||'div', 'hb-li'); d.appendChild(el('i', level || '')); d.appendChild(el('b', '', a)); if (b) d.appendChild(el('span', '', b)); return d; }

  function css() {
    if (document.getElementById('hb-css')) return;
    var s = document.createElement('style'); s.id = 'hb-css';
    s.textContent = [
      '.hb{position:fixed;inset:0;z-index:1;border:0;border-radius:0;overflow:hidden;overflow:clip;background:#04061a;cursor:grab;touch-action:none;animation:hbIn .5s ease both}',
      '.hb:active{cursor:grabbing}',
      '@keyframes hbIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}',
      '.hb::before{content:"";position:absolute;inset:0;background-image:radial-gradient(rgba(0,230,118,.09) 1px,transparent 1px);background-size:32px 32px;pointer-events:none}',
      '.hb-world{position:absolute;left:0;top:0;width:0;height:0;transform-origin:0 0}',
      '.hb-bar{position:absolute;left:12px;top:calc(var(--hb-top,88px) + 4px);right:12px;display:flex;flex-wrap:wrap;justify-content:flex-end;gap:6px;align-items:center;z-index:6;pointer-events:none}',
      '.hb-bar>*{pointer-events:auto}.hb-z{font:700 9px Orbitron,monospace;letter-spacing:1.2px;color:var(--text-faint,#6fae92);margin-right:auto;pointer-events:none}',
      '.hb-btn{font:700 9px Orbitron,monospace;letter-spacing:1.2px;color:var(--accent,#00e676);background:rgba(6,10,36,.74);-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);border:1px solid var(--border-dim,rgba(0,230,118,.28));border-radius:7px;padding:7px 11px;min-height:30px;cursor:pointer}',
      '.hb-btn:hover{background:rgba(0,230,118,.14)}',
      '.hb-tray{position:fixed;left:12px;bottom:14px;display:flex;gap:6px;flex-wrap:wrap;z-index:31;max-width:calc(50vw - 60px)}',
      // A desktop window is a dashboard: the board fills the window under the header, the page never scrolls, and the old cards below it are hidden (everything they did is a block or a bar button here).
      'html.hub-board-on,html.hub-board-on body{height:100%}html.hub-board-on{overflow:hidden;overflow:clip}html.hub-board-on body{overflow:visible;padding:0}',
      // The header and the first-time card float over the board as glass; the board itself is the whole window.
      'html.hub-board-on body>header{position:fixed;top:8px;left:50%;transform:translateX(-50%);z-index:30;width:auto;max-width:calc(100vw - 16px);margin:0;padding:6px 14px;background:rgba(6,10,36,.66);border:1px solid var(--border-dim,rgba(0,230,118,.28));border-radius:14px;-webkit-backdrop-filter:blur(10px);backdrop-filter:blur(10px)}',
      'html.hub-board-on #setup-card{position:static;display:flex;align-items:center;gap:10px;padding:2px 8px;margin:0;border-radius:8px;background:rgba(36,28,12,.82);max-width:none}html.hub-board-on #setup-card .sc-title{white-space:nowrap}html.hub-board-on #setup-card .btn{padding:4px 10px;min-height:0;font-size:9px}',
      '.hk[hidden]{display:none!important}html.hub-board-on #setup-banner{display:none}html.hub-board-on #setup-card .sc-text{display:none}html.hub-board-on #setup-card[hidden]{display:none}',
      'html.hub-board-on body>#apps-before,html.hub-board-on body>#opencode-app-area,html.hub-board-on body>#ytdl-app-area,html.hub-board-on body>#yt-app-area,html.hub-board-on body>#filebrowser-area,html.hub-board-on body>#apps-after{display:none!important}',
      'html.hub-board-on #home-panels{height:0;margin:0;padding:0;overflow:visible}',
      '.hb-bar .hb-z.hint{flex:1 1 200px;min-width:0;white-space:normal;line-height:1.35;text-align:left}.hb-btn.off{color:var(--text-faint,#6fae92);border-style:dashed}.hb-btn.on{border-color:var(--accent,#00e676)}',
      '.hk-pi{flex:none;color:var(--accent,#00e676)}.hk-app .gi svg.tile{width:32px;height:32px}.hk-app .hb-btn{margin-left:auto;text-decoration:none;padding:5px 8px;min-height:0}',
      '.hk{position:absolute;display:flex;flex-direction:column;min-width:0;transition:border-color .25s,box-shadow .25s,opacity .3s;content-visibility:auto;contain-intrinsic-size:auto 224px auto 110px}',
      '.hk.amber{border-color:rgba(224,165,60,.6)}.hk.red{border-color:rgba(255,92,92,.6)}',
      '.hk.pick{border-color:var(--accent,#00e676);box-shadow:0 0 0 1px var(--accent,#00e676),0 18px 40px rgba(0,0,0,.6)}.hk.dim{opacity:.12;pointer-events:none}',
      '.hk-h{display:flex;align-items:center;gap:4px;padding:4px 4px 4px 9px;cursor:grab;user-select:none;flex:none}',
      '.hk-h .t{font:700 11px Orbitron,monospace;letter-spacing:1px;color:var(--text,#d9ffe9);flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
      '.hk-h .n{font:700 11px Orbitron,monospace;color:var(--text-muted,#8fcfb2)}',
      '.hk-h button[data-a=dup]{display:none}.hk.exp.can-dup .hk-h button[data-a=dup]{display:grid}',
      '.hk-h button{width:28px;height:28px;border:0;background:none;color:var(--text-muted,#8fcfb2);opacity:.9;border-radius:5px;cursor:pointer;display:grid;place-items:center;padding:0}.hk-h button svg{width:15px!important;height:15px!important}.hk-h button:hover{color:var(--text,#d9ffe9);background:rgba(0,230,118,.12)}',
      '.hk-b{flex:1;min-height:0;display:grid;grid-template-rows:1fr;transition:opacity .3s,filter .3s;overflow:hidden}.hk-i{overflow:hidden;min-height:0}',
      // minimised: the title goes bold and bright, the content stays as a faded, softened glimpse (not removed), and cannot be pressed
      '.hk.min{overflow:hidden}.hk.min .hk-h .t{font-weight:900;color:var(--accent,#00e676);text-shadow:0 0 10px rgba(0,230,118,.45)}.hk.min .hk-b{display:none}',
      '.hk-rz{position:absolute;right:0;bottom:0;width:16px;height:16px;cursor:nwse-resize;touch-action:none}.hk.min .hk-rz{display:none}',
      '.hb-li{display:flex;gap:8px;align-items:baseline;padding:5px 10px;border-top:1px solid rgba(255,255,255,.05);font-size:12.5px;color:var(--text,#d9ffe9)}.hb-li i{width:6px;height:6px;border-radius:50%;background:var(--accent,#00e676);flex:none}.hb-li i.a{background:#e0a53c}.hb-li i.r{background:#ff5c5c}.hb-li i.o{background:var(--text-faint,#6fae92)}.hb-li span{color:var(--text-muted,#8fcfb2);font-size:11.5px;overflow-wrap:anywhere}',
      '.hb-stat{padding:2px 10px 8px}.hb-stat b{display:block;font:900 32px Orbitron,monospace;color:var(--accent,#00e676);line-height:1.1}.hb-stat span{color:var(--text-muted,#8fcfb2);font-size:12px}',
      '.hb-note{padding:2px 10px 9px;font-size:12px;color:var(--text-muted,#8fcfb2);line-height:1.45}',
      '.hk-app{display:flex;align-items:center;gap:10px;padding:4px 10px 8px;cursor:pointer}.hk-app .gi{width:32px;height:32px;flex:none;display:grid;place-items:center;font-size:22px}.hk-app .gi svg{width:30px;height:30px}.hk-app b{font-weight:600;font-size:14px;line-height:1.2;color:var(--text,#d9ffe9)}.hk-app small{display:block;font:600 10px Orbitron,monospace;letter-spacing:.7px;color:var(--text-muted,#8fcfb2)}.hk-app small.on{color:var(--accent,#00e676)}',
      '.hk:not(.exp) [data-a=col],.hk:not(.exp) [data-a=out]{display:none}',
      '.hk.tile:not(.exp) [data-a=foc]{display:none}.hk.tile:not(.exp) .hk-h .t{white-space:normal;overflow-wrap:anywhere;line-height:1.2;font-size:10.5px;letter-spacing:.6px}',
      '.hk.exp{border-color:var(--accent,#00e676);box-shadow:0 0 0 1px var(--accent,#00e676),0 24px 60px rgba(0,0,0,.6)}.hk.exp .hk-i{display:flex;flex-direction:column;height:100%}',
      '.hk.settle{transition:left .42s ' + SPRING + ',top .42s ' + SPRING + ',width .38s ' + EASE + ',height .38s ' + EASE + ',border-color .25s}',
      '.hk-tabs{display:flex;gap:6px;padding:0 8px 6px;flex:none}.hk-tabs button{font:700 9px Orbitron,monospace;letter-spacing:1.2px;color:var(--text-muted,#8fcfb2);background:none;border:1px solid var(--border-dim,rgba(0,230,118,.28));border-radius:6px;padding:6px 10px;cursor:pointer}.hk-tabs button.on{color:var(--accent,#00e676);border-color:var(--accent,#00e676);background:rgba(0,230,118,.1)}',
      '.hk-fr{flex:1;min-height:0;width:100%;border:0;background:transparent;color-scheme:dark;border-radius:0 0 3px 3px}.hk-wait{padding:14px;color:var(--text-muted,#8fcfb2);font-size:13px}.hk-mv{flex:1;min-height:0;overflow:auto;padding:0 6px 8px}',
      '.hb-dragging iframe{pointer-events:none}.hk.pick{will-change:transform;content-visibility:visible}.hk.exp,.hk:focus-within{content-visibility:visible}.hb.panning .hb-world{will-change:transform}',
      '.hb-guides{position:absolute;inset:0;pointer-events:none;z-index:5}.hb-guides i{position:absolute;background:var(--cyan,#41ebff);opacity:.65}.hb-guides .vertical{top:0;bottom:0;width:1px}.hb-guides .horizontal{left:0;right:0;height:1px}',
      '.hk-glyph{display:none}.hb-compact .hk:not(.exp) .hk-rz,.hb-compact .hk:not(.exp) .hk-h button{display:none}.hb-compact .hk:not(.exp) .hk-b{opacity:.5;filter:blur(calc((.7 - var(--hb-scale)) * 5px));pointer-events:none}.hb-compact .hk:not(.exp) .hk-h{min-height:0;gap:6px}.hb-compact .hk:not(.exp) .hk-glyph{display:flex;flex:none}.hb-compact .hk-glyph svg{width:calc(14px / var(--hb-scale));height:calc(14px / var(--hb-scale))}.hb-compact .hk-h .t,.hb-compact .hk-h .n{font-size:calc(12px / var(--hb-scale));letter-spacing:.3px;font-weight:900;color:var(--accent,#00e676)}',
      '@media (prefers-reduced-motion:reduce){.hb{animation:none}.hk-b{transition:none}.hk.settle{transition:none}}'
    ].join('\n');
    document.head.appendChild(s);var shared=document.getElementById('hub-blocks-css');if(shared)document.head.appendChild(shared);
  }

  function mount(root) {
    if (root.__hubBoardInstance) root.__hubBoardInstance.destroy();
    css();
    var panelNodes=new Set(),panelObserver=null;
    var hiddenProperty=Object.getOwnPropertyDescriptor(HTMLElement.prototype,'hidden');
    function fadePanel(node){
      if(!node||node._hubFade)return node;if(node.classList.contains('hb-jump')){var nativeAnimate=node.animate;node.animate=function(frames,options){if(options&&options.duration===140)options=Object.assign({},options,{duration:0});return nativeAnimate.call(node,frames,options);};}node._hubFade=true;panelNodes.add(node);var wanted=hiddenProperty.get.call(node),animation=null,token=0,nativeRemove=node.remove;
      function change(hide,remove){wanted=!!hide;var current=animation&&!hiddenProperty.get.call(node)?parseFloat(getComputedStyle(node).opacity):(wanted?1:0);var t=++token;if(animation)animation.cancel();node.classList.toggle('hub-panel-closing',wanted);node.setAttribute('aria-hidden',String(wanted));
        var finish=function(){if(t!==token)return;hiddenProperty.set.call(node,wanted);if(animation){animation.cancel();animation=null;}if(remove){nativeRemove.call(node);panelNodes.delete(node);}if(alive)syncModal();};
        if(!node.isConnected||reduce.matches||!alive){finish();return;}
        var modalSelector='#voice,.hands-setup,.hb-glass-panel,.hb-session-detail';var waitForExit=!wanted&&Array.from(panelNodes).some(function(n){return n!==node&&n.isConnected&&!n.hasAttribute('hidden')&&((isPopup(node)&&isPopup(n))||(node.matches(modalSelector)&&n.matches(modalSelector)));});hiddenProperty.set.call(node,false);animation=node.animate([{opacity:current},{opacity:wanted?0:1}],{duration:180,delay:waitForExit?180:0,fill:'both',easing:'ease-out'});animation.onfinish=finish;
        if(!wanted){positionPopup(node);closeOtherPopups(node);if(node.matches('#voice,.hands-setup,.hb-glass-panel,.hb-session-detail'))closeModalPeers(node);}syncModal();
      }
      Object.defineProperty(node,'hidden',{configurable:true,get:function(){return wanted;},set:function(v){change(v,false);}});
      node._hubResetFade=function(){if(animation)animation.cancel();hiddenProperty.set.call(node,wanted);delete node.hidden;node.remove=nativeRemove;if(nativeAnimate)node.animate=nativeAnimate;delete node._hubFade;delete node._fadeOpen;};node.remove=function(){change(true,true);};node._fadeOpen=function(){change(false,false);};return node;
    }
    function isPopup(n){return n.matches('.hb-more-menu,.hb-layer-menu,.hb-jump,.hb-ctx,.hb-tray-list');}
    function closeOtherPopups(keep){panelNodes.forEach(function(n){if(n!==keep&&n.isConnected&&isPopup(n)&&!n.hidden)n.hidden=true;});}
    function positionPopup(n){if(!isPopup(n)||!host||!host.isConnected)return;var r=stageRect(),w=Math.max(100,Math.min(380,r.width-12));n.style.left=(r.left+6)+'px';n.style.top=(r.top+6)+'px';n.style.right='auto';n.style.bottom='auto';n.style.width=w+'px';n.style.maxHeight=Math.max(40,r.height-12)+'px';n.style.transform='none';}
    function closeModalPeers(keep){panelNodes.forEach(function(n){if(n!==keep&&n.isConnected&&n.matches('#voice,.hands-setup,.hb-glass-panel,.hb-session-detail')&&!n.hidden){if(n.id==='voice')document.getElementById('v-close').click();else if(n.matches('.hands-setup'))n.hidden=true;else n.remove();}});}
    function syncModal(){if(!host)return;var history=document.getElementById('v-history');if(history&&!history.hidden&&history.textContent==='HISTORY')history.click();var v=document.getElementById('voice'),g=Array.from(document.querySelectorAll('.hb-glass-panel,.hands-setup,.hb-session-detail')).find(function(n){return !n.hasAttribute('hidden');});var on=!!((v&&!v.hasAttribute('hidden'))||(g&&!g.hasAttribute('hidden')));host.classList.toggle('hb-modal-open',on);document.documentElement.classList.toggle('hub-modal-open',on);}
    function glassPage(url,title){
      closeOtherPopups(null);var old=host.querySelector('.hb-glass-panel');if(old)old.remove();var voice=document.getElementById('voice');if(voice&&!voice.hidden)document.getElementById('v-close').click();
      var pane=fadePanel(el('section','hb-glass-panel')),head=el('div','hb-glass-head'),close=el('button','hb-btn','');pane.setAttribute('role','dialog');pane.setAttribute('aria-label',title);close.type='button';close.title='Close '+title;close.setAttribute('aria-label','Close '+title);close.appendChild(svg(ICON.x));close.onclick=function(){pane.remove();};head.append(el('h2','',title),close);var fr=el('iframe','hb-glass-frame');fr.title=title;fr.src=embedUrl(url);fr.onload=function(){try{fr.contentDocument.addEventListener('keydown',function(e){if(e.key==='Escape')pane.remove();});}catch(e){}hookFrame(fr,null);};pane.append(head,fr);host.appendChild(pane);pane._fadeOpen();close.focus({preventScroll:true});
    }
    var graphicsNotice=null,graphicsDismissed=false;
    var view = null, L = {}, hid = {}, touched = false, data = null, V = { x: 0, y: 0, k: 1 }, focusId = null, zTop = 2, blocks = {}, nav = null, alive = true, dragCleanups = [];
    try { var saved = JSON.parse(localStorage.getItem(KEY) || 'null'); if (saved) { L = saved.L || {}; hid = saved.hid || {}; } } catch (e) {}
    function save(quiet) {
      if (quiet !== true && typeof markBoard === 'function') markBoard();
      try {
        var out = {}; Object.keys(L).forEach(function (k) { if (k.indexOf('#') > 0) return; var l = L[k]; out[k] = { x: l.x, y: l.y, w: l.exp ? l.ow : l.w, h: l.exp ? l.oh : l.h, min: l.min, z: l.z, u: l.u, rz: l.rz }; });
        localStorage.setItem(KEY, JSON.stringify({ L: out, hid: hid }));
      } catch (e) {}
    }

    // The layout (positions, sizes, minimised, hidden blocks, layers) is also kept on the Hub, so the app, the browser and the iPad leave the board where it was left.
    // The newest copy wins; the local copy stays the fast one. Nothing is sent until the Hub's own copy has been read (so a failed read never wipes it).
    var prefsCache = null, prefsTimer = 0, boardAt = 0;
    try { boardAt = +localStorage.getItem('agenthub:board:at') || 0; } catch (e) {}
    function boardPayload() {
      var out = {}; Object.keys(L).forEach(function (k) { if (k.indexOf('#') > 0) return; var l = L[k]; out[k] = { x: l.x, y: l.y, w: l.exp ? l.ow : l.w, h: l.exp ? l.oh : l.h, min: l.min, z: l.z, u: l.u, rz: l.rz }; });
      return { at: boardAt, L: out, hid: hid, layers: layerState };
    }
    function markBoard() {
      boardAt = Date.now(); try { localStorage.setItem('agenthub:board:at', String(boardAt)); } catch (e) {}
      clearTimeout(prefsTimer); prefsTimer = setTimeout(function () {
        if (!alive || !prefsCache) return;
        fetch('/api/board/prefs', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.assign({}, prefsCache, { board: boardPayload() })) }).catch(function () {});
      }, 900);
    }
    function adoptBoard(sb) {
      Object.keys(sb.L || {}).forEach(function (k) { var s = sb.L[k], l = L[k]; if (!s || typeof s.x !== 'number') return;
        if (!l) { L[k] = { x: s.x, y: s.y, w: s.w, h: s.h, min: s.min, z: s.z, u: s.u, rz: s.rz }; return; }
        if (l.exp) { l.ow = s.w; l.oh = s.h; } else { l.w = s.w; l.h = s.h; } l.x = s.x; l.y = s.y; l.min = s.min; l.z = s.z; l.u = s.u; l.rz = s.rz; });
      hid = sb.hid || {};
      var ls = sb.layers; if(validLayers(ls))layerState=normalLayers(ls);
      boardAt = sb.at; try { localStorage.setItem('agenthub:board:at', String(boardAt)); localStorage.setItem('agenthub:board:layers', JSON.stringify(layerState)); } catch (e) {}
      save(true); Object.keys(blocks).forEach(function (id) { if (L[id]) applyBlock(id); }); try { relayout(); refreshLayers(); trayDraw(); } catch (e) {}
    }
    function readBoardPrefs() {
      fetch('/api/board/prefs', { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).then(function (p) {
        if (!p || !alive) return; prefsCache = p; var sb = p.board;
        if (sb && sb.L && sb.at > boardAt) adoptBoard(sb); else if (boardAt && (!sb || sb.at < boardAt)) markBoard();
      }).catch(function () {});
    }
    root.replaceChildren(); // Home is a 520 px column; the board breaks out of it to the width of the window.
    root.style.width = 'min(96vw,1500px)'; root.style.maxWidth = 'none'; root.style.marginLeft = 'calc((100% - min(96vw,1500px)) / 2)'; root.style.boxSizing = 'border-box';
    var recoveryTimer=0;var setupCard = document.getElementById('setup-card'), setupText = setupCard && setupCard.querySelector('.sc-text'); if (setupText) setupCard.title = setupText.textContent;   // the first-time notice is a small chip over the board; the sentence is its tooltip
    var host = el('div', 'hb'), stageClip=el('div','hb-stage'), world = el('div', 'hb-world'), bar = el('div', 'hb-bar'), zh = el('div', 'hb-z', '100%'), tray = el('div', 'hb-tray');
    var restartChip=el('button','hb-btn hb-restart-needed','HUB IS OLDER THAN ITS FILES: RESTART');restartChip.type='button';restartChip.hidden=true;restartChip.onclick=function(){document.getElementById('restart-btn').click();};host.appendChild(restartChip);
    var fitBtn = el('button', 'hb-btn', 'FIT'), tidyBtn = el('button', 'hb-btn', 'TIDY'), zin = el('button', 'hb-btn', '+'), zout = el('button', 'hb-btn', '−');
    fitBtn.type = tidyBtn.type = zin.type = zout.type = 'button'; tidyBtn.title = 'Neaten the blocks where they are: line them up and clear overlaps. Nothing else moves'; tidyBtn.setAttribute('aria-label', 'Organise the board'); fitBtn.title = 'Fit every block in view'; zin.title = 'Zoom in (Ctrl + wheel)'; zout.title = 'Zoom out (Ctrl + wheel)';
    var hint = el('span', 'hb-z hint', ''); hint.style.cssText = 'margin-right:8px;opacity:.7'; hint.style.transition = 'opacity .7s'; hint.textContent = matchMedia('(pointer:coarse)').matches ? 'DRAG TO MOVE · PINCH TO ZOOM · DRAG A TITLE TO MOVE A BLOCK · TAP AN APP TO OPEN IT HERE' : 'WHEEL MOVES · CTRL + WHEEL ZOOMS · DRAG A BLOCK TO MOVE IT · CLICK AN APP TO OPEN IT HERE';
    var blocksBtn = el('button', 'hb-btn', 'BLOCKS'), ingestBtn = el('button', 'hb-btn', '+ INGEST APP'), talkBtn = el('button', 'hb-btn', 'TALK'), pcBtn = el('button', 'hb-btn hb-pc off', 'PC CONTROL');
    blocksBtn.type = ingestBtn.type = talkBtn.type = pcBtn.type = 'button'; blocksBtn.title = 'Every block, shown or hidden (Ctrl + K)'; ingestBtn.title = 'Teach the Hub another app'; talkBtn.title = 'Talk to the Hub'; pcBtn.title = 'PC control';
    // Home is board-only; legacy cards remain hidden control hosts, never a navigation option.
    var setupHome = setupCard && { parent: setupCard.parentNode, next: setupCard.nextSibling };   // the first-time notice lives in the bar, where it can never sit over a block
    var setupBtn = el('button', 'hb-btn', 'SETUP'); setupBtn.type = 'button'; setupBtn.hidden = true; setupBtn.title = 'Things the Hub found that need setting up'; setupBtn.onclick = function () { location.href = '/setup'; };
    bar.append(zh, hint, setupBtn, ingestBtn, talkBtn, pcBtn, zout, zin, blocksBtn, tidyBtn, fitBtn);  stageClip.appendChild(world);host.append(bar,stageClip); document.body.appendChild(tray); root.appendChild(host); document.documentElement.classList.add('hub-board-on');
    // how you move around the board: 2D (flat; wheel zooms, middle-drag pans) or 3D (tilt and orbit)
    view = window.__hubBoardView ? window.__hubBoardView.mount({ host: host, V: function () { return V; }, place: function () { place(); }, stop: function () { stopCam(); }, touch: function () { touched = true; }, fit: function (a) { fit(a); }, motion: motion }) : null;
    if (view) { bar.insertBefore(view.btn, zout); bar.insertBefore(view.gizmoBtn, zout); }

    var stopEdge = HubBlocks.edge(host), arrived = false;
    var defs = [['att', P.att], ['runs', P.runs], ['ses', P.ses], ['hlt', P.hlt], ['use', P.use]];
    var apps = (typeof APP_LIST !== 'undefined' ? APP_LIST : []).filter(function (a) { return !a.hidden; });
    // the three built-in cards (Auto-LLM, YouTube Download, YouTube Upload) are page sections, not apps: an icon block scrolls to the card and opens it
    var CARDS = [['oc', 'Auto-LLM', 'oc-header', null], ['ytdl', 'YouTube Download', 'ytdl-header', 'ytdl-toggle-btn'], ['yt', 'YouTube Upload', 'yt-header', 'yt-toggle-btn']].filter(function (c) { return document.getElementById(c[2]); });
    CARDS.forEach(function (c) { defs.push(['card:' + c[0], { t: 'APP', w: TW, h: 64, card: c }]); });
    // the Doctor's picture (Agent Smith's cyan line-art style); the drawn glyph is only the fallback if the file is missing
    function doctorPicture(){var img=document.createElement('img');img.className='hub-doctor';img.alt='The Doctor';img.src='/static/agent-icons/doctor.png';img.onerror=function(){var g=svg(SUPPORT.extra[3],2);g.classList.add('hub-doctor');if(img.parentNode)img.parentNode.replaceChild(g,img);};return img;}
    var SUPPORT = { t: 'APP', w: TW, h: 64, extra: ['support', 'Support', '/support', 'M12 4.8a3.2 3.2 0 1 0 0 6.4 3.2 3.2 0 0 0 0-6.4zM5 21c0-3.9 3.1-7 7-7s7 3.1 7 7M9.2 14.3v2.4a2.3 2.3 0 0 0 4.6 0v-.6M16.3 17.2h2.4M17.5 16v2.4M10.2 3.6a2 2 0 0 1 3.6 0'] };
    defs.push(['extra:support', SUPPORT]);
    apps.forEach(function (a) { defs.push(['app:' + a.id, { t: 'APP', w: TW, h: 64, app: a }]); });
    // a block you have not arranged yourself takes its place and height from the layout; one you moved or resized keeps what you gave it
    defs.forEach(function (d) { var sv = L[d[0]]; L[d[0]] = (sv && sv.u) ? { x: sv.x, y: sv.y, w: sv.w, h: sv.h, min: sv.min ? 1 : 0, z: sv.z, u: 1, rz: sv.rz ? 1 : 0 } : { x: 0, y: 0, w: d[1].w, h: d[1].h, min: sv && sv.min ? 1 : 0, u: 0, rz: 0 }; });

    // No two blocks may sit on top of each other. The block you just opened, moved or resized keeps its place (then the open ones,
    // then the most recently used); every other block that is in the way goes to the nearest free spot, so a shove never ping-pongs.
    var GAP = 14;
    function validLayers(ls){return !!(ls&&Array.isArray(ls.order)&&ls.order.length&&ls.order.length<=32&&ls.order.every(function(k,i,a){return typeof k==='string'&&/^[a-z0-9-]{1,64}$/.test(k)&&a.indexOf(k)===i;}));}
    function normalLayers(ls){return {order:ls.order.slice(),hidden:ls.hidden||{},members:ls.members||{},labels:ls.labels||{},collapsed:ls.collapsed||{},invert:!!ls.invert,axis:(ls.axis==='height'||ls.axis==='both')?ls.axis:'depth'};}
    var layerState={order:['system','tools','apps'],hidden:{},members:{},labels:{},collapsed:{},invert:false,axis:'depth'};
    try{var ls=JSON.parse(localStorage.getItem('agenthub:board:layers'));if(validLayers(ls))layerState=normalLayers(ls);}catch(e){}
    function layerName(k){return layerState.labels[k]||k.toUpperCase();}
    function layerOf(id){var base=id.split('#')[0],k=layerState.members[base]||(P[base]?'system':base.indexOf('act:')===0?'apps':base.indexOf('app:')===0&&!['app:movie-clipper','app:file-browser'].includes(base)?'apps':'tools');return layerState.order.indexOf(k)>=0?k:layerState.order[0];}
    function isHidden(id){return !!hid[id]||!!layerState.hidden[layerOf(id)];}
    function revealLayer(id){var key=layerOf(id);if(layerState.hidden[key]){delete layerState.hidden[key];saveLayers();refreshLayers();}}
    function saveLayers(){try{localStorage.setItem('agenthub:board:layers',JSON.stringify(layerState));}catch(e){}if(typeof markBoard==='function')markBoard();}
    function changeLayer(id,key){layerState.members[id.split('#')[0]]=key;hubNote(((blocks[id]&&blocks[id]._name)||id)+' moved to layer '+layerName(key));saveLayers();refreshLayers();}
    function refreshLayers(){Object.keys(blocks).forEach(applyBlock);if(stackDepth)stackDepth();if(layerMenu&&!layerMenu.hidden)drawLayers();trayDraw();}

    function bh(l) { return l.min ? (touchScreen.matches?44:32) + PEEK : l.h; }
    function hits(x, y, w, h, S, g) { for (var i = 0; i < S.length; i++) { var P = S[i]; if (g && P.g === g) continue; if (x < P.x + P.w + GAP && P.x < x + w + GAP && y < P.y + P.h + GAP && P.y < y + h + GAP) return true; } return false; }
    function resolve(pin) {
      var ids = Object.keys(L).filter(function (i) { return blocks[i] && !isHidden(i); }), pushed = {}, order = ids.slice();
      function rank(id) { return id === pin ? 1e9 : L[id].exp ? 1e8 : (L[id].z || 1); }
      order.sort(function (a, c) { return rank(c) - rank(a); });
      var placed = [];
      order.forEach(function (id) {
        var l = L[id], w = l.w, h = bh(l);
        if (hits(l.x, l.y, w, h, placed, l.stack)) {
          var xs = [l.x], ys = [l.y], best = null, bd = 1e18;
          placed.forEach(function (P) { xs.push(P.x + P.w + GAP, P.x - w - GAP, P.x); ys.push(P.y + P.h + GAP, P.y - h - GAP, P.y); });
          xs.forEach(function (x) { ys.forEach(function (y) { var d = (x - l.x) * (x - l.x) + (y - l.y) * (y - l.y); if (d < bd && !hits(x, y, w, h, placed, l.stack)) { bd = d; best = [x, y]; } }); });
          if (!best) { var far = placed.reduce(function (m, P) { return Math.max(m, P.x + P.w); }, l.x); best = [far + GAP, l.y]; }
          pushed[id] = { x: l.x, y: l.y }; l.x = best[0]; l.y = best[1];
        }
        placed.push({ x: l.x, y: l.y, w: w, h: h, g: l.stack });
      });
      Object.keys(pushed).forEach(function (id) { var b = blocks[id]; if (!reduce.matches) settle(b); applyBlock(id); L[id].from = L[id].from || pushed[id]; });
      if (stackDepth) stackDepth();
      return pushed;
    }


    // Heights follow the content (no clipped lists), and the default arrangement is packed from the real sizes, so nothing is hidden or stacked.
    function sizeOf(id) { var l = L[id]; return { w: l.exp ? l.ow : l.w, h: l.exp ? l.oh : l.h }; }
    function autosize() {
      defs.forEach(function (d) {
        var l = L[d[0]], e = blocks[d[0]]; if (!e || l.exp || l.min || isHidden(d[0])) return;if(l.rz){e._in.style.overflowY='auto';return;}
        var keep = e.style.height, visibility = e.style.contentVisibility; e.style.contentVisibility = 'visible'; e.style.height = 'auto'; var nat = Math.max(Math.ceil(e.offsetHeight),e.querySelector('.hk-h').offsetHeight+e._in.scrollHeight)+8; e.style.height = keep; e.style.contentVisibility = visibility;
        // The block follows its content, up and down (it used to only grow, so a block whose content shrank stayed too big), and the 3D slab behind it
        // follows the block: the slab's own height is set here too, not only when the block is placed.
        l.h = Math.max(110, Math.min(nat, 460));
        e._in.style.overflowY = nat > 460 ? 'auto' : 'hidden'; e.style.height = l.h + 'px';
        if (e._solid) e._solid.style.height = e.style.height;
      });
    }
    var fitTimer = 0;
    function fitSoon() { if (fitTimer) return; fitTimer = setTimeout(function () { fitTimer = 0; if (!alive) return; var before = defs.map(function (d) { return L[d[0]] && L[d[0]].h; }).join(); autosize(); var after = defs.map(function (d) { return L[d[0]] && L[d[0]].h; }).join(); if (before !== after && nav) nav.refresh(); }, 180); }
    function watchContent(e) { if (e._in && window.MutationObserver) new MutationObserver(fitSoon).observe(e._in, { childList: true, subtree: true, characterData: true }); }
    function grid() {
      // Wide window: the overview panels in a row, usage under the first, the tiles below. Narrow window (a tablet): everything flows
      // in rows that fit, centred, so nothing is cut off at the sides and the zoom can stay readable.
      var T = {}, G = 22, host_w = stageRect().width || 1100, maxW = Math.floor(host_w / .85) - 60, ids = ['att', 'runs', 'ses', 'hlt', 'use'];
      var tiles = defs.filter(function (d) { return !P[d[0]]; }), x, y, rowH = 0, widest = 0;
      if (maxW >= 1250) {
        var X0 = -640; x = X0; y = -330;
        ['att', 'runs', 'ses', 'hlt'].forEach(function (id) { var z = sizeOf(id); T[id] = { x: x, y: y }; x += z.w + G; rowH = Math.max(rowH, z.h); });
        y += rowH + G; T.use = { x: X0, y: y }; y += sizeOf('use').h + G + 12;
        var COLS = Math.max(4, Math.min(8, Math.floor(((host_w || 1100) - 70) / (TW + G + 6))));   // as many tiles per row as the window is wide
        for (var i = 0; i < tiles.length; i += COLS) {
          var row = tiles.slice(i, i + COLS), rh = 0;
          row.forEach(function (d, c) { T[d[0]] = { x: X0 + c * (TW + G), y: y }; rh = Math.max(rh, sizeOf(d[0]).h); });
          y += rh + 14;
        }
        return T;
      }
      x = 0; y = 0; var rows = [[]];
      function put(id, z) { if (x && x + z.w > maxW) { x = 0; y += rowH + G; rowH = 0; rows.push([]); } T[id] = { x: x, y: y, w: z.w }; rows[rows.length - 1].push(id); x += z.w + G; rowH = Math.max(rowH, z.h); widest = Math.max(widest, x - G); }
      ids.forEach(function (id) { put(id, sizeOf(id)); });
      x = 0; y += rowH + G + 12; rowH = 0; rows.push([]);
      tiles.forEach(function (d) { put(d[0], sizeOf(d[0])); });
      Object.keys(T).forEach(function (id) { T[id] = { x: T[id].x - widest / 2, y: T[id].y - 330 }; });
      return T;
    }
    function relayout() {
      autosize(); var T = grid(), pin = null;
      defs.forEach(function (d) { var l = L[d[0]]; if (l.exp) pin = d[0]; if (l.u || l.exp) return; var t = T[d[0]]; if (!t) return; var moved = Math.abs(l.x - t.x) + Math.abs(l.y - t.y) > 1; l.x = t.x; l.y = t.y; if (moved && blocks[d[0]]._shown && !reduce.matches) settle(blocks[d[0]]); applyBlock(d[0]); });
      resolve(pin);
      defs.forEach(function (d) { blocks[d[0]]._shown = true; });
    }

    function applyBlock(id) { var e = blocks[id], l = L[id]; if (!e.classList.contains('pick')) { e.style.left = l.x + 'px'; e.style.top = l.y + 'px'; } e.style.width = l.w + 'px'; e.style.height = l.min ? (32 + PEEK) + 'px' : l.h + 'px'; e.classList.toggle('min', !!l.min); e.style.zIndex = (layerState.order.indexOf(layerOf(id))+1)*100000+Math.min(99999,l.z||1); e.hidden = isHidden(id);if(e._solid){var v=e._solid;v.hidden=e.hidden;v.style.left=l.x+'px';v.style.top=l.y+'px';v.style.width=l.w+'px';v.style.height=e.style.height;v.style.zIndex=e.style.zIndex;v.classList.toggle('exp',!!l.exp);} if (nav) nav.refresh(); }
    function mk(id, d) {
      var e = el('div', 'hk hub-block' + ((d.app || d.card || d.extra || d.act) ? ' tile' : '')); e.dataset.id = id; e.tabIndex = 0; e.setAttribute('role', 'group');
      var h = el('div', 'hk-h'), glyph = el('span', 'hk-glyph'); glyph.appendChild(svg(id === 'runs' ? 'M5 4l14 8-14 8V4Z' : 'M5 5h14v14H5zM8 12h8')); glyph.firstChild.style.width = glyph.firstChild.style.height = ''; h.appendChild(glyph); var ttl = String(d.app ? (d.app.name || d.app.id) : d.card ? d.card[1] : d.extra ? d.extra[1] : d.act ? (d.act.name || 'Action') : d.t || '').toLowerCase(), pic = PANEL_ICON[id]; if (!pic) { for (var tk in TITLE_ICON) { if (ttl.indexOf(tk) >= 0) { pic = TITLE_ICON[tk]; break; } } } if (pic) { var pi = svg(pic, 1.8); pi.classList.add('hk-pi'); pi.style.width = pi.style.height = '15px'; h.appendChild(pi); }
      h.appendChild(el('span', 't', d.app ? (d.app.name || d.app.id) : d.card ? d.card[1] : d.extra ? d.extra[1] : d.act ? (d.act.name || 'Action') : d.t)); h.appendChild(el('span', 'n'));
      [['stop', 'Stop this app'], ['col', 'Close this view'], ['dup', 'Open another window of this tool'], ['out', 'Open in its own tab'], ['min', 'Minimise'], ['foc', 'Focus'], ['x', 'Hide in tray; click its chip to restore']].forEach(function (b) { var bt = el('button'); bt.type = 'button'; bt.dataset.a = b[0]; bt.setAttribute('aria-label', b[1]); bt.title = b[1]; bt.appendChild(svg(ICON[b[0]]));if(b[0]==='stop'){bt.hidden=true;bt.appendChild(el('span','','STOP'));}h.appendChild(bt); });
      var body = el('div', 'hk-b'), inn = el('div', 'hk-i'); body.appendChild(inn); var solid=el('div','hk-solid');solid.setAttribute('aria-hidden','true');['back','left','right','top','bottom'].forEach(function(side){solid.appendChild(el('i',side));});solid.classList.add('hk-volume');solid.dataset.id=id;if(d.app||d.card||d.extra||d.act)solid.classList.add('tile');e._solid=solid;e.append(h,body,el('div','hk-rz')); e._in = inn; e._n = h.querySelector('.n'); e._app = d.app || null; e._open = null; e._name = d.app ? (d.app.name || d.app.id) : d.card ? d.card[1] : d.t;
      if (d.app) {
        var a = d.app, box = el('div', 'hk-app'), gi = el('div', 'gi');
        if(typeof CARD_ICONS!=='undefined'&&CARD_ICONS[a.id]){gi.innerHTML=CARD_ICONS[a.id];var clone=gi.firstElementChild,suffix='-board'+(appTile.n=(appTile.n||0)+1);if(clone){clone.innerHTML=clone.innerHTML.replace(/id="([^"]+)"/g,'id="$1'+suffix+'"').replace(/url\(#([^)]+)\)/g,'url(#$1'+suffix+')');}}else gi.appendChild(appTile(a));gi.dataset.applet=a.id;
        var nm = el('div'); nm.appendChild(el('b', '', a.name || a.id)); var st = el('small', a.running ? 'on' : '', a.running ? 'RUNNING' : 'IDLE'); nm.appendChild(st); if (gi.firstElementChild && gi.firstElementChild.tagName.toLowerCase() === 'svg') gi.firstElementChild.style.width = gi.firstElementChild.style.height = '30px'; box.append(gi, nm); inn.appendChild(box); e._st = st;
        if (a.id === 'file-browser' && typeof SMB_SHORTCUT !== 'undefined' && SMB_SHORTCUT) {   // the old card's SMB link
          var sm = el('a', 'hb-btn', 'SMB'), onMac = /Macintosh/.test(navigator.userAgent) && !(navigator.maxTouchPoints > 1);
          sm.href = (onMac && SMB_SHORTCUT.href_mac) || SMB_SHORTCUT.href; sm.title = SMB_SHORTCUT.title || 'Open the network share'; sm.addEventListener('click', function (ev) { ev.stopPropagation(); }); sm.addEventListener('pointerdown', function (ev) { ev.stopPropagation(); }); box.appendChild(sm);
        }
      }
      if (d.extra) {
        var ex = d.extra, xb = el('div', 'hk-app'), xg = el('div', 'gi'); xg.dataset.applet=ex[0];if(ex[0]==='support'){xg.appendChild(doctorPicture());}else{xg.appendChild(svg(ex[3], 1.8)); xg.firstChild.style.cssText = 'width:26px;height:26px;fill:none;stroke:var(--accent,#00e676);stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round';}
        var xn = el('div'); xn.appendChild(el('b', '', ex[1])); xn.appendChild(el('small', '', 'FIX THE HUB')); xb.append(xg, xn); inn.appendChild(xb);
        e._name = ex[1]; e._spec = { tabs: [[ex[4] || 'SUPPORT', ex[2]]], w: ex[5] || 780, h: ex[6] || 640 }; e._open = function () { expand(id); };
      }
      if (d.app) { e._spec = { app: d.app.id, w: 780, h: 560 }; e._open = function () { expand(id); }; }
      if (d.act) {   // a tile backed by Hub actions (the old cards' action apps): its own dialog
        var t2 = d.act, ab = el('div', 'hk-app'), ag = el('div', 'gi'); ag.dataset.applet=t2.id||'action';ag.appendChild(appTile(t2)); var an = el('div'); an.appendChild(el('b', '', t2.name || 'Action')); an.appendChild(el('small', '', 'ACTIONS')); ab.append(ag, an); inn.appendChild(ab);
        e._name = t2.name || 'Action'; e._open = function () { if (typeof openActions === 'function') openActions(t2); };
      }
      if (d.card) {
        var c = d.card, bx2 = el('div', 'hk-app'), g2 = el('div', 'gi'); g2.appendChild(cardIcon(c[2])||appTile({id:c[0]}));g2.dataset.applet=c[0];
        var nm2 = el('div'); nm2.appendChild(el('b', '', c[1])); nm2.appendChild(el('small', '', 'OPEN')); bx2.append(g2, nm2); inn.appendChild(bx2);
        e._spec = c[0] === 'oc' ? { tabs: [['MISSIONS', '/missions'], ['GRAPH', '/graph'], ['REINFORCEMENT LEARNING', '/yard'], ['AGENCY', '/agents'], ['CHATS', '/chats']], w: 860, h: 600 } : { move: c[0] === 'ytdl' ? 'ytdl-app-area' : 'yt-app-area', toggle: c[3], w: 560, h: 620 };
        e._open = function () { expand(id); };
      }
      e.setAttribute('aria-label', e._name); blocks[id] = e; watchContent(e); world.append(solid,e); applyBlock(id); return e;
    }
    defs.forEach(function (d) { mk(d[0], d[1]); });
    var releaseArrival = HubBlocks.prepare(blocks);
    // The app list and the action tiles arrive after the page starts; a tile that shows up later gets its block too (nothing the old cards had is ever missing).
    function syncTiles() {
      var added = false;
      (typeof APP_LIST !== 'undefined' ? APP_LIST : []).filter(function (a) { return !a.hidden; }).forEach(function (a) { var id = 'app:' + a.id; if (!blocks[id]) { addDef([id, { t: 'APP', w: TW, h: 64, app: a }]); added = true; } });
      (typeof ACTION_APPS !== 'undefined' ? ACTION_APPS : []).forEach(function (t) { var id = 'act:' + (t.id || t.name); if (!blocks[id]) { addDef([id, { t: 'APP', w: TW, h: 64, act: t }]); added = true; } });
      if (added) { relayout(); if (!touched) fit(true); }
    }
    function addDef(d) { defs.push(d); L[d[0]] = { x: 0, y: 0, w: d[1].w, h: d[1].h, min: 0, u: 0, rz: 0 }; mk(d[0], d[1]); }
    defs.filter(function (d) { return false; });

    // Click an app and it opens here, inside the board, at a readable size; the cross-arrow button opens it in its own tab instead.
    function settle(b) { if (!motion.allowed()) return; b.classList.add('settle'); setTimeout(function () { b.classList.remove('settle'); }, 450); }
    function embedUrl(url) { var u = new URL(url, location.href); if (['/missions', '/agents', '/graph', '/yard', '/chats', '/support'].indexOf(u.pathname) >= 0) u.searchParams.set('embed', '1'); return u.href; }
    // A block's own page is a separate document: events inside it never reach the board. These hooks hand the few that matter across: the pressed wheel (orbit or pan,
    // even when the pointer is over a window), Alt or Ctrl with the wheel (tilt, zoom), and a press anywhere in a window brings that window to the front.
    // In 3D the board is tilted by CSS 3D transforms and the browser's own wheel scrolling stops working inside it (a window's page, or a list in a block), so the wheel scrolls the nearest scrollable thing by hand.
    function scrollByHand(e, doc) {
      var cs, n = e.target && e.target.nodeType === 1 ? e.target : null, dy = e.deltaMode === 1 ? e.deltaY * 32 : e.deltaMode === 2 ? e.deltaY * 400 : e.deltaY, win = doc.defaultView;
      for (; n; n = n.parentElement) {
        cs = win.getComputedStyle(n);
        if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll') && n.scrollHeight > n.clientHeight + 1 && (dy < 0 ? n.scrollTop > 0 : n.scrollTop + n.clientHeight < n.scrollHeight - 1)) { n.scrollTop += dy; return true; }
      }
      var se = doc.scrollingElement; if (se && se.scrollHeight > se.clientHeight + 1 && (dy < 0 ? se.scrollTop > 0 : se.scrollTop + se.clientHeight < se.scrollHeight - 1)) { se.scrollTop += dy; return true; }
      return false;
    }
    function hookFrame(f, id) {
      try {
        var w = f.contentWindow; if (!w || !w.document) return;
        w.document.addEventListener('mousedown', function (e) { if (e.button === 1) e.preventDefault(); }, true);
        w.addEventListener('pointerdown', function (e) { if (id && L[id]) { L[id].z = ++zTop; applyBlock(id); if (stackDepth) stackDepth(); } if (view && e.button === 1) view.drag(e, w); }, true);
        w.addEventListener('wheel', function (e) {
          if (view && view.mode() === '3d' && !e.altKey && !e.ctrlKey && !e.shiftKey && e.deltaY && scrollByHand(e, w.document)) { e.preventDefault(); return; }
          if (!view || !(e.altKey || e.ctrlKey)) return; e.preventDefault();
          var r = f.getBoundingClientRect(), k = (r.width / (f.clientWidth || r.width)) || 1;
          host.dispatchEvent(new WheelEvent('wheel', { bubbles: true, cancelable: true, deltaX: e.deltaX, deltaY: e.deltaY, deltaMode: e.deltaMode, ctrlKey: e.ctrlKey, altKey: e.altKey, shiftKey: e.shiftKey, clientX: r.left + e.clientX * k, clientY: r.top + e.clientY * k }));
        }, { capture: true, passive: false });
      } catch (err) { /* a page from another origin keeps its own events */ }
    }
    function hubNote(t){try{window.dispatchEvent(new CustomEvent('hub-log',{detail:{kind:'hub',text:String(t)}}));}catch(e){}}
    var stackDepth = null;
    // Several windows of one tool: another block of the same tool, offset a little, allowed to overlap its siblings, in front of them in 3D.
    stackDepth = function () {
      var groups={};Object.keys(blocks).forEach(function(id){var key=layerOf(id);(groups[key]=groups[key]||[]).push(id);});
      var axis=layerState.axis||'depth',n=layerState.order.length,lift={};
      // Apart in HEIGHT: the layer at the top of the list is at the top, then the next one below it, each placed under the one above using the
      // real size of its blocks (never a fixed step), so two layers cannot overlap. INVERT puts the deepest layer at the top instead.
      if(axis!=='depth'){
        var topFirst=layerState.invert?layerState.order.slice():layerState.order.slice().reverse(),cursor=null;
        topFirst.forEach(function(key){
          var ids=(groups[key]||[]).filter(function(id){return !isHidden(id);});if(!ids.length){lift[key]=0;return;}
          var lo=Infinity,hi=-Infinity;ids.forEach(function(id){var l=L[id];lo=Math.min(lo,l.y);hi=Math.max(hi,l.y+bh(l));});
          if(cursor===null){lift[key]=0;cursor=hi+56;}else{lift[key]=cursor-lo;cursor+=(hi-lo)+56;}
        });
      }
      Object.keys(groups).forEach(function(key){var bases={};groups[key].forEach(function(id){var base=id.split('#')[0];if(L[id].exp&&!isHidden(id))(bases[base]=bases[base]||[]).push(id);});
        groups[key].forEach(function(id){var siblings=bases[id.split('#')[0]]||[];siblings.sort(function(a,b){return (L[a].z||0)-(L[b].z||0);});var step=siblings.length>1?(siblings.indexOf(id)-siblings.length+1)*90:0;
          var idx=layerState.order.indexOf(key),rank=layerState.invert?(n-1-idx):idx,z=(axis==='height'?0:rank*Math.min(140,280/Math.max(1,n-1)))+step,dy=axis==='depth'?0:(lift[key]||0);
          [blocks[id],blocks[id]._solid].forEach(function(e){if(e){e.style.setProperty('--hb-dz',z+'px');e.style.setProperty('--hb-dy',dy+'px');}});});
      });
    };
    function openWindow(title, url, fromSync) {
      if (!alive) return false;
      var slug = String(title).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 24) || 'window', id = 'extra:win-' + slug + '-' + (String(url).replace(/[^0-9a-z]+/gi, '') || 'x').slice(-14), label = String(title).toUpperCase().slice(0, 14);
      if (!blocks[id]) {
        addDef([id, { t: 'APP', w: 200, h: 64, extra: ['win-' + slug, String(title).slice(0, 28), url, 'M4 5h16v14H4zM4 9h16', label, 640, 480] }]);
        var l0 = L[id], n = Object.keys(blocks).filter(function (k) { return k.indexOf('extra:win-') === 0; }).length; l0.x = 80 + n * 44; l0.y = 90 + n * 44; l0.u = 1; hid[id] = 0;
      }
      var b = blocks[id]; b._spec.tabs = [[label, url]]; b._winUrl = url;
      if (!fromSync) { try { fetch('/api/windows/panels', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title: title, url: url }) }); } catch (e) {} }
      touched = true; stopCam(); revealLayer(id);
      if (hid[id]) { hid[id] = 0; applyBlock(id); resolve(id); trayDraw(); save(); }
      if (L[id].exp) { var fr = b.querySelector('iframe'); if (fr) { fr.src = embedUrl(url); b._url = url; } } else expand(id);
      L[id].z = ++zTop; applyBlock(id); if (stackDepth) stackDepth(); lookAt(id);
      // The panel is sized to the window it shows (its own width : height), not to a fixed box, and nothing else on the board is left under it.
      var wm = /[?&]id=(\d+)/.exec(String(url));
      fetch('/api/windows', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (j) {
        var w = (j.windows || []).filter(function (x) { return wm && String(x.id) === wm[1]; })[0];
        if (alive && blocks[id]) fitWindowPanel(id, w && w.w > 0 && w.h > 0 ? w.w / w.h : 16 / 10, w && w.w > 0 ? w.w : 700);
      }).catch(function () { if (alive && blocks[id]) fitWindowPanel(id, 16 / 10, 700); });
      return true;
    }
    // CHROME: the bar, the note line and the panel's own header above the picture, in the panel's own pixels.
    function fitWindowPanel(id, aspect, winW) {
      var q = L[id], b = blocks[id]; if (!q || !b || !q.exp) return;
      var CHROME = 150, phone = host.clientWidth < 900, sr = stageRect(), hr = host.getBoundingClientRect(), k = V.k || 1, w, h;
      if (phone) {                                                       // a phone: the width of the visible screen, as tall as the picture needs, never taller than the screen
        w = Math.max(260, (sr.width - 12) / k); h = Math.min(Math.max(220, w / aspect + CHROME), Math.max(300, (sr.height - 12) / k));
      } else {                                                           // a computer: a picture of about the size the window is, a little smaller for a big one
        w = Math.max(420, Math.min(760, winW)); h = Math.min(760, Math.round(w / aspect + CHROME));
      }
      q.w = Math.round(w); q.h = Math.round(h); b._spec.w = q.w; b._spec.h = q.h;
      if (phone) { q.x = (sr.left - hr.left + 6 - V.x) / k; q.y = (sr.top - hr.top + 6 - V.y) / k; }
      applyBlock(id); resolve(id); L[id].z = ++zTop; applyBlock(id); if (stackDepth) stackDepth(); lookAt(id);
    }
    // The panels open on the Hub are open here too, and a panel closed anywhere is closed everywhere.
    function syncPanels() {
      if (!alive) return;
      fetch('/api/windows/panels', { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).then(function (j) {
        if (!j || !alive) return;
        var want = {}; j.panels.forEach(function (p) { want[p.url] = p; });
        Object.keys(blocks).filter(function (k) { return k.indexOf('extra:win-') === 0; }).forEach(function (k) { if (blocks[k]._winUrl && !want[blocks[k]._winUrl]) closeWindow(k); });
        j.panels.forEach(function (p) { var have = Object.keys(blocks).some(function (k) { return blocks[k]._winUrl === p.url; }); if (!have) openWindow(p.title, p.url, true); });
      }).catch(function () {});
    }
    window.addEventListener('message', function (e) { var u = e.data && e.data.hubWindowClose; if (!u) return; Object.keys(blocks).forEach(function (k) { if (blocks[k]._winUrl === u) closeWindow(k); }); });
    // The bottom-left tray gets a WINDOWS button: the windows open on this PC, one press opens one as a panel.
    var winBtn = null, winList = null;
    function buildWindowsTray() {
      if (winBtn || !tray) return;
      var bt = el('button', 'hb-btn hb-tray-count'), list = fadePanel(el('div', 'hb-tray-list'));
      bt.type = 'button'; bt.dataset.tray = 'windows'; bt.title = 'Windows of this PC: open one as a panel'; bt.setAttribute('aria-label', 'Windows of this PC'); bt.append(svg('M4 5h16v11H4zM9 20h6M12 16v4', 2));
      list.hidden = true; list.setAttribute('role', 'dialog'); list.setAttribute('aria-label', 'Windows of this PC'); list.appendChild(el('div', 'hb-list-title', 'WINDOWS OF THIS PC'));
      function fill() {
        fetch('/api/windows', { cache: 'no-store' }).then(function (r) { return r.json(); }).then(function (j) {
          Array.prototype.slice.call(list.querySelectorAll('button,p')).forEach(function (n) { n.remove(); });
          if (!j.windows || !j.windows.length) { list.appendChild(el('p', 'hb-tray-empty', j.supported === false ? 'Windows can be shown on Windows only.' : 'No windows are open.')); return; }
          j.windows.forEach(function (w) {
            var row = el('button', 'hb-btn', String(w.title).slice(0, 44) + '  (' + String(w.exe).replace(/\.exe$/i, '') + ')'); row.type = 'button';
            row.onclick = function () { list.hidden = true; bt.setAttribute('aria-expanded', 'false'); openWindow(w.title, '/mirror?id=' + w.id); }; list.appendChild(row);
          });
          if (!list.hidden) positionPopup(list);
        }).catch(function () {});
      }
      bt.onclick = function () { list.hidden = !list.hidden; bt.setAttribute('aria-expanded', String(!list.hidden)); if (!list.hidden) { fill(); positionPopup(list); } };
      document.addEventListener('pointerdown', function (e) { if (!list.hidden && !list.contains(e.target) && !bt.contains(e.target)) { list.hidden = true; bt.setAttribute('aria-expanded', 'false'); } }, true);
      tray.appendChild(bt); host.appendChild(list); winBtn = bt; winList = list;
    }
    setTimeout(buildWindowsTray, 1500); var panelTimer = 0; setTimeout(function () { syncPanels(); panelTimer = setInterval(syncPanels, 4000); }, 6000);          // panels other devices opened load after the move into the dashboard has finished, never during it
    function duplicate(srcId) {
      var base = srcId.split('#')[0], src = blocks[srcId], bd = null;
      defs.forEach(function (d) { if (d[0] === base) bd = d; });
      if (!bd || !src || !src._spec || !(src._spec.tabs || src._spec.app)) return;
      var n = 2; while (blocks[base + '#' + n]) n++;
      if (n > 5) return;                                               // five windows of a tool is plenty
      var id = base + '#' + n; addDef([id, Object.assign({}, bd[1])]);
      var b = blocks[id], l = L[id], s0 = L[srcId]; b._name = blocks[base]._name + ' ' + n; hid[id] = 0;
      L[base].stack = base; l.stack = base; l.x = s0.x + 46; l.y = s0.y + 46; l.u = 1; touched = true; stopCam();
      expand(id);
      var want = src._url, tb = b._in.querySelectorAll('.hk-tabs button');
      (b._spec.tabs || []).forEach(function (t, i) { if (t[1] === want && tb[i]) tb[i].click(); });
      l.z = ++zTop; applyBlock(id); resolve(id); stackDepth(); if (nav) nav.refresh();
    }
    function closeWindow(id) {
      var b = blocks[id]; if (!b) return;
      if(b._solid)b._solid.remove();b.remove(); delete blocks[id]; delete L[id]; delete hid[id];
      for (var i = defs.length - 1; i >= 0; i--) if (defs[i][0] === id) defs.splice(i, 1);
      resolve(null); trayDraw(); stackDepth(); if (nav) nav.refresh();
    }
    function frame(url, id) { var f = el('iframe', 'hk-fr'); f.src = embedUrl(url); f.setAttribute('loading', /^\/(mirror|session)\b/.test(String(url)) ? 'eager' : 'lazy'); f.title = 'Embedded Hub tool'; f.addEventListener('load', function () { hookFrame(f, id); }); if (motion) motion.frame(f); return f; }
    function expand(id) {
      var b = blocks[id], l = L[id], sp = b._spec; if (!sp) return;
      if (l.exp) { collapse(id); return; }
      var before = b.getBoundingClientRect();
      l.exp = 1; l.ow = l.w; l.oh = l.h; l.min = 0; l.z = ++zTop; b._icon = Array.prototype.slice.call(b._in.childNodes); b._in.replaceChildren();
      b.classList.add('exp'); if (sp.tabs || sp.app) b.classList.add('can-dup'); b.querySelector('.hk-h .t').textContent = String(b._name).toUpperCase(); l.w = host.clientWidth < 900 ? Math.max(260, Math.min(sp.w, host.clientWidth - 28)) : sp.w; l.h = host.clientWidth < 900 ? Math.max(240, Math.min(sp.h, host.clientHeight - TOP() - 28)) : sp.h; applyBlock(id); resolve(id);
      if (sp.app) {
        b._in.appendChild(motion.skeleton('Starting ' + b._name));
        fetch('/api/start/' + sp.app, { method: 'POST' }).then(function (r) { if (!r.ok) throw new Error('could not start'); return r.json(); }).then(function (j) {
          if (!alive||!l.exp) return;b._app.running=true;b.querySelector('[data-a=stop]').hidden=false;b._st.textContent='RUNNING';b._st.className='on';b._url = j.base_path + '/'; b._in.replaceChildren(frame(b._url, id));
        }).catch(function (err) { if (l.exp) b._in.replaceChildren(el('div', 'hk-wait', 'Could not start ' + b._name + ': ' + err.message)); });
      } else if (sp.tabs) {
        var tabs = el('div', 'hk-tabs'), fr = frame(sp.tabs[0][1], id); b._url = sp.tabs[0][1];
        sp.tabs.forEach(function (t, i) { var tb = el('button', i ? '' : 'on', t[0]); tb.type = 'button'; tb.onclick = function () { Array.prototype.forEach.call(tabs.children, function (x) { x.classList.remove('on'); }); tb.classList.add('on'); fr.src = embedUrl(t[1]); if (motion) motion.frame(fr); b._url = t[1]; }; tabs.appendChild(tb); });
        b._in.append(tabs, fr);
      } else if (sp.move) {
        var src = document.getElementById(sp.move), wrap = el('div', 'hk-mv'); b._from = src; b._home = src && src.parentNode; b._next = src && src.nextSibling;
        if (src) { wrap.appendChild(src); var t = sp.toggle && document.getElementById(sp.toggle); if (t && /EXPAND/.test(t.textContent)) t.click(); }
        b._in.appendChild(wrap);
      }
      if (motion) motion.flip(b, before, V.k, 'open');
      setTimeout(function () { if (alive && l.exp && L[id] === l && blocks[id]) { l.looked = 1; lookAt(id); } }, 420);        // a window closed within 420 ms is gone
    }
    function collapse(id, faded) {
      var b = blocks[id], l = L[id]; if (!l.exp || l.closing) return;
      if (!faded && motion.allowed()) { l.closing = true; b.dataset.motion = 'close'; b._in.animate([{opacity:1},{opacity:0}],{duration:120}).onfinish = function () { l.closing = false; if (alive) collapse(id, true); }; return; }
      var before = b.getBoundingClientRect();
      if (b._from && b._home) { b._home.insertBefore(b._from, b._next || null); b._from = null; }
      b._in.replaceChildren.apply(b._in, b._icon || []); l.exp = 0; b._url = null; b.classList.remove('exp', 'can-dup'); l.w = l.ow; l.h = l.oh; b.querySelector('.hk-h .t').textContent = b._name; applyBlock(id);
      Object.keys(L).forEach(function (k) { var o = L[k]; if (o.from && o.u) { o.x = o.from.x; o.y = o.from.y; settle(blocks[k]); applyBlock(k); } o.from = null; }); resolve(null);
      if (motion) { motion.flip(b, before, V.k, 'close'); if (!b._flip) delete b.dataset.motion; }
      if (focusId === id) { focusId = null; undim(); fit(true); } else if (l.looked) fit(true);
      l.looked = 0;
    }
    if (apps.length === 0) { /* nothing to add */ }


    function blockActions(target,actions){var row=el('div','hb-block-actions');actions.forEach(function(a){var b=el(typeof a[1]==='string'?'a':'button','hb-btn',a[0]);if(typeof a[1]==='string')b.href=a[1];else {b.type='button';b.onclick=a[1];}row.appendChild(b);});target.appendChild(row);}
    function hideBlock(id){var b=blocks[id];if(!b)return;hid[id]=1;hubNote(((b._name)||id)+' hidden in the tray');b.getAnimations().forEach(function(a){a.cancel();});applyBlock(id);save();trayDraw();if(focusId===id){focusId=null;undim();}if(stackDepth)stackDepth();}
    var bin=document.getElementById('edit-toggle');
    function overBin(e){if(!bin)return false;var r=bin.getBoundingClientRect();return e.clientX>=r.left-8&&e.clientX<=r.right+8&&e.clientY>=r.top-8&&e.clientY<=r.bottom+8;}
    function stopApp(id){var b=blocks[id],app=b&&b._app;if(!app||!confirm('Stop '+b._name+'?'))return;var button=b.querySelector('[data-a=stop]');button.disabled=true;fetch('/api/stop/'+encodeURIComponent(app.id),{method:'POST'}).then(function(r){if(!r.ok)throw Error('Could not stop app');Object.keys(blocks).forEach(function(k){if(blocks[k]._app&&blocks[k]._app.id===app.id){if(L[k].exp)collapse(k,true);blocks[k]._app.running=false;blocks[k]._st.textContent='IDLE';blocks[k]._st.className='';blocks[k].querySelector('[data-a=stop]').hidden=true;}});if(window.__hubHomePanels)__hubHomePanels.refresh();}).catch(function(e){button.title=e.message;}).finally(function(){button.disabled=false;});}
    function sessionOpen(m){
      var old=host.querySelector('.hb-session-detail');if(old)old.remove();
      var dlg=el('section','hb-session-detail');dlg.setAttribute('role','dialog');dlg.setAttribute('aria-modal','true');dlg.setAttribute('aria-label','Session details');
      var head=el('div','hb-session-head'),title=el('h2','',m.brief||'Session'),close=el('button','hb-btn','CLOSE');close.type='button';close.onclick=function(){dlg.remove();};head.append(title,close);dlg.appendChild(head);
      if(/^Doctor[: ]/.test(m.brief)){var doctor=doctorPicture();head.prepend(doctor);}
      var meta=el('div','hb-session-meta');var chatNote=(m.kind==='agent-log')?el('p','hb-session-note','This is a '+(m.agent==='codex'?'Codex':'Claude Code')+' chat. The Hub can read it but cannot answer it: open it in '+(m.agent==='codex'?'Codex':'Claude Code')+' to reply. Only missions can be answered here.'):null;if(m.status)meta.appendChild(el('span','hb-status-chip',m.status.replace(/_/g,' ')));if(m.kind)meta.appendChild(el('span','hb-session-kind',m.kind==='agent-log'?'chat':m.kind));dlg.appendChild(meta);if(chatNote)dlg.appendChild(chatNote);
      if(m.last){dlg.append(el('h3','','LAST MESSAGE'),el('p','hb-session-last',m.last));}
      if(m.cwd){dlg.append(el('h3','','FOLDER'),el('p','hb-session-folder',m.cwd));var folder=el('button','hb-btn','OPEN FOLDER');folder.type='button';folder.onclick=function(){folder.disabled=true;fetch('/api/sessions/open-folder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:m.id})}).then(function(r){if(!r.ok)throw Error('Could not open folder');folder.textContent='FOLDER OPENED';}).catch(function(e){folder.textContent=e.message;}).finally(function(){folder.disabled=false;});};dlg.appendChild(folder);}
      if(/^Doctor[: ]/.test(m.brief)){var support=el('button','hb-btn','OPEN SUPPORT');support.type='button';support.onclick=function(){dlg.remove();window.__hubBoard.open('/support?session='+encodeURIComponent(m.id));var block=blocks['extra:support'],selected=block.querySelector('.hb-session-context');if(selected)selected.remove();selected=el('aside','hb-session-context');selected.textContent=(m.brief||'Doctor session')+' · '+m.id+' · '+(m.status||'');block._in.prepend(selected);};dlg.appendChild(support);}
      host.appendChild(dlg);close.focus({preventScroll:true});
    }

    var heldPointers=new Set(),paintPending=false,paintReleaseTimer=0;
    function holdPaint(e){if(e.button===0&&e.target.closest('.hk'))heldPointers.add(e.pointerId);}
    function releasePaint(e){if(e&&e.type!=='blur')heldPointers.delete(e.pointerId);else heldPointers.clear();if(!heldPointers.size&&paintPending){clearTimeout(paintReleaseTimer);paintReleaseTimer=setTimeout(function(){if(alive){paintPending=false;paint();}},0);}}
    document.addEventListener('pointerdown',holdPaint,true);window.addEventListener('pointerup',releasePaint,true);window.addEventListener('pointercancel',releasePaint,true);window.addEventListener('blur',releasePaint);
    function paint() {
      if(heldPointers.size){paintPending=true;return;}
      if (!data) { ['att', 'runs', 'ses', 'hlt', 'use'].forEach(function (id) { if (!blocks[id]._in.firstChild) { blocks[id].dataset.loading = '1'; blocks[id]._in.appendChild(motion.skeleton('Loading ' + blocks[id]._name)); } }); return; }
      var a = blocks.att, nA = data.attention.filter(function (x) { return x.kind !== 'session'; }).length; a._in.replaceChildren(); a._n.textContent = nA ? String(nA) : '';
      if (!nA) a._in.appendChild(el('div', 'hb-note', 'Nothing needs you right now.')); data.attention.forEach(function (x) {
        var chat = x.kind === 'session', r = li(chat ? 'o' : (x.level === 'red' ? 'r' : 'a'), x.title, x.options ? '' : x.detail); if (chat) { r.classList.add('hb-chat'); r.insertBefore(el('em', 'hb-tag', 'CHAT · REPLY IN ITS OWN APP'), r.children[1]); }
        if (x.options) { var bar = el('div'); bar.style.cssText = 'display:flex;gap:6px;padding:2px 10px 8px'; x.options.forEach(function (o) { var b = el('button', 'hb-btn', String(o.name || o.id).toUpperCase()); b.type = 'button'; b.onclick = function () { fetch('/api/acp/answer', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: x.id, option: o.id }) }).then(function () { if (window.__hubHomePanels) window.__hubHomePanels.refresh(); }); }; bar.appendChild(b); }); a._in.appendChild(r); a._in.appendChild(bar); }
        else a._in.appendChild(r);
        if (x.doctor) {
          var db = el('div'); db.style.cssText = 'display:flex;gap:6px;padding:2px 10px 8px';
          var ask = el('button', 'hb-btn', x.asked ? 'THE DOCTOR WAS ASKED' : 'ASK THE DOCTOR'); ask.type = 'button'; ask.disabled = !!x.asked;
          ask.onclick = function () { ask.disabled = true; ask.textContent = 'ASKING…'; fetch('/api/support/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: x.doctor }) }).then(function () { if (window.__hubHomePanels) window.__hubHomePanels.refresh(); }); };
          db.appendChild(ask); a._in.appendChild(db);
        }
      });
      if(setupCard)a._in.appendChild(setupCard);blockActions(a._in,[['SETUP','/setup']]);
      a.classList.toggle('amber', nA > 0); a.classList.toggle('red', data.attention.some(function (x) { return x.level === 'red'; }));
      var up=data.health&&data.health.uptime_s;if(typeof up==='number'){var boot=Math.round(Date.now()/1000-up),prevBoot=0;try{prevBoot=Number(localStorage.getItem('agenthub:hub:boot'))||0;localStorage.setItem('agenthub:hub:boot',String(boot));}catch(e){}
        if(prevBoot&&Math.abs(boot-prevBoot)>15)hubNote('Hub restarted: it was turned off and on again');else if(!prevBoot)hubNote('Hub is on');}
      if(!window.__hubOpenNoted){window.__hubOpenNoted=1;var fromLanding='';try{fromLanding=sessionStorage.getItem('agenthub:from')||'';sessionStorage.removeItem('agenthub:from');}catch(e){}hubNote(fromLanding==='landing'?'Hub opened from the landing page':'Hub opened');}
      var runIds={};data.runs.forEach(function(m){runIds[m.id]=m.brief||m.id;});
      if(paint._runs){Object.keys(runIds).forEach(function(k){if(!(k in paint._runs))hubNote('Mission started: '+runIds[k]);});Object.keys(paint._runs).forEach(function(k){if(!(k in runIds))hubNote('Mission finished or stopped: '+paint._runs[k]);});}paint._runs=runIds;
      var attIds={};data.attention.forEach(function(x){if(x.kind!=='session')attIds[x.id||x.title]=x.title;});if(paint._att){Object.keys(attIds).forEach(function(k){if(!(k in paint._att))hubNote('Needs you: '+attIds[k]);});}paint._att=attIds;
      var r = blocks.runs; r._n.textContent = String(data.runs.length); r._in.replaceChildren(); var st = el('div', 'hb-stat'); var runNumber = el('b'); st.appendChild(runNumber); motion.number(runNumber, r._count, data.runs.length); r._count = data.runs.length; st.appendChild(el('span', '', data.runs.length ? data.runs.map(function (m) { return m.brief; }).slice(0, 2).join(' · ') : 'missions running')); r._in.appendChild(st);
      var s = blocks.ses; s._in.replaceChildren(); var ss = data.sessions, any = false; s._n.textContent = String(ss.needs_you.length + ss.working.length + ss.idle.length);
      [['needs_you', 'a'], ['working', ''], ['idle', 'o']].forEach(function (g) { if(ss[g[0]].length)s._in.appendChild(el('div','hb-session-group',g[0].replace('_',' ').toUpperCase()));ss[g[0]].forEach(function (m) { any = true; var chatRow=m.kind==='agent-log',row=li(g[1],m.brief,(chatRow?'CHAT · ':'MISSION · ')+(m.ask||m.project||'')+' · '+g[0].replace('_',' '),'button');if(chatRow)row.classList.add('hb-chat');row.type='button';if(/^Doctor[: ]/.test(m.brief)){var doctor=doctorPicture();row.prepend(doctor);}row.classList.add('hb-session');row.tabIndex=0;row.setAttribute('role','button');row.title=/^Doctor[: ]/.test(m.brief)?'Open this Doctor session in Support':'Show session status and details';row.onclick=function(){sessionOpen(m);};row.onkeydown=function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();row.click();}};s._in.appendChild(row); }); });
      if (!any) s._in.appendChild(el('div', 'hb-note', 'No agent session is waiting, working or recently finished.'));
      var u = blocks.use; u._in.replaceChildren(); var cu = data.usage && data.usage.claude;
      if (!cu) u._in.appendChild(el('div', 'hb-note', 'Counting Claude Code’s logs…'));
      else {
        var bars = el('div'); bars.style.cssText = 'display:flex;align-items:flex-end;gap:3px;height:62px;padding:6px 10px 2px'; var mx = Math.max.apply(null, cu.by_hour.concat([1]));
        cu.by_hour.forEach(function (v) { var i = el('i'); i.style.cssText = 'flex:1;background:linear-gradient(#3ba7ff,rgba(59,167,255,.25));border:1px solid rgba(59,167,255,.6);border-bottom:0;height:' + Math.max(2, Math.round(v / mx * 100)) + '%'; bars.appendChild(i); });
        u._in.appendChild(bars); u._in.appendChild(el('div', 'hb-note', cu.tokens_5h.toLocaleString() + ' tokens in 5 h · ' + cu.tokens_7d.toLocaleString() + ' in 7 days · counted from the logs, no plan limit'));
      }
      var h = data.health, hb = blocks.hlt;restartChip.hidden=!h.stale_code;host.style.setProperty('--hb-notice-height',h.stale_code?'38px':'0px'); hb._n.textContent = String(h.recent_problems); hb._in.replaceChildren();
      if(h.stale_code){var restartNote=el('button','hb-btn hb-health-restart','RESTART NEEDED');restartNote.type='button';restartNote.onclick=restartChip.onclick;hb._in.appendChild(restartNote);}hb._in.appendChild(li('', 'Hub v' + h.version, 'up ' + ago(h.uptime_s)));
      hb._in.appendChild(li(h.local_model && h.local_model.listening ? '' : 'o', 'Local model', h.local_model && h.local_model.listening ? 'listening' : 'off'));
      hb._in.appendChild(li(h.recent_problems ? 'a' : '', 'Warnings', String(h.recent_problems)));
      hb._in.appendChild(li('o', 'Graphics card', 'not measured'));notices();blockActions(hb._in,[['SETTINGS','/setup'],['RESTART',function(){document.getElementById('restart-btn').click();}]]);
      if (h.apps.failed.length) hb._in.appendChild(li('r', 'Failed to start', h.apps.failed.join(', ')));
      Object.keys(blocks).forEach(function (id) { var b = blocks[id]; if (!b.dataset.loading) return; delete b.dataset.loading; if (motion.allowed()) b._in.animate([{opacity:0},{opacity:1}],{duration:220}); });
      syncTiles(); relayout(); if (!touched) fit(false); legacy();
      Object.keys(blocks).forEach(function (id) { var b = blocks[id]; if (b._app) { var run = Array.isArray(h.apps.running)?h.apps.running.indexOf(b._app.id)>=0:!!b._app.running; b._st.textContent = run ? 'RUNNING' : 'IDLE'; b._st.className = run ? 'on' : '';b.querySelector('[data-a=stop]').hidden=!run; } });
    }

    var raster=1,rasterTimer=0;
    function worldTransform(v){var t=view?view.transform(v):'translate3d('+v.x+'px,'+v.y+'px,0) scale('+v.k+')';return raster===1?t:'scale3d('+(1/raster)+','+(1/raster)+','+(1/raster)+') '+t;}
    function place(rasterOnly) {
      clearTimeout(recoveryTimer);recoveryTimer=setTimeout(function(){if(alive)trayDraw();},180);
      world.style.transform=worldTransform(V);if(!rasterOnly){clearTimeout(rasterTimer);rasterTimer=setTimeout(function(){if(!alive)return;var next=/Apple/.test(navigator.vendor)?1:Math.max(1,V.k);if(Math.abs(next-raster)>.015){raster=next;world.style.zoom=raster;place(true);}},180);} zh.textContent = Math.round(V.k * 100) + '%'; host.style.setProperty('--hb-scale', V.k); HubBlocks.grid(host, V); if (nav) nav.refresh();if(trayLists&&trayLists.outside&&!trayLists.outside.hidden)updateTrayLive();
      var compact = V.k < .35;
      if (host.classList.contains('hb-compact') !== compact) host.classList.toggle('hb-compact', compact);
    }
    // A camera move in flight gives way the moment you touch the board (wheel, drag, zoom buttons): it must never fight your hand.
    var camTok = 0, physics = __hubBoardControls.camera(function () { return V; }, place, function () { return motion && motion.allowed(); }), guides = __hubBoardControls.guides(host, L, hid, function () { return V; });
    function stopCam() { camTok++; physics.stop(); }
    var reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
    // `force`: FIT and TIDY always glide unless the person asked the system for reduced motion (the software-graphics rule skips them otherwise, which read as no transition at all)
    function cam(to, ms, force) {
      physics.stop();
      var tok = ++camTok;
      if (!ms || (force ? reducedMotion.matches : !motion.allowed())) { V = to; place(); return; }
      var f = { x: V.x, y: V.y, k: V.k }, t0 = performance.now();
      (function s(n) { if (!alive || tok !== camTok) return; var u = Math.min(1, (n - t0) / ms), e = 1 - Math.pow(1 - u, 3.4); V = { x: f.x + (to.x - f.x) * e, y: f.y + (to.y - f.y) * e, k: f.k + (to.k - f.k) * e }; place(); if (u < 1) requestAnimationFrame(s); })(t0);
    }
    // the glass header and the bar take the top of the window; the board's own content starts below them
    var stage={left:8,top:120,right:800,bottom:600,width:792,height:480};
    function stageRect(ignoreTray){
      var hr=host.getBoundingClientRect(),ar=bar.getBoundingClientRect(),top=Math.max(ar.bottom,document.querySelector('body>header')?document.querySelector('body>header').getBoundingClientRect().bottom:0,!restartChip.hidden?restartChip.getBoundingClientRect().bottom:0)-hr.top+8,right=hr.width-8,bottom=hr.height-8;
      stage={left:8,top:top,right:Math.max(48,right),bottom:Math.max(top+40,bottom)};stage.width=stage.right-stage.left;stage.height=stage.bottom-stage.top;
      stageClip.style.clipPath='none';return stage;
    }
    function TOP(){return stageRect().top;}
    function setTop(){var h=document.querySelector('body>header');document.documentElement.style.setProperty('--hub-header-bottom',Math.ceil(h?h.getBoundingClientRect().bottom:0)+'px');host.style.setProperty('--hb-top',Math.ceil(h?h.getBoundingClientRect().bottom+4:80)+'px');document.documentElement.style.setProperty('--hub-chrome-bottom',Math.ceil(Math.max(bar.getBoundingClientRect().bottom,h?h.getBoundingClientRect().bottom:0))+'px');stageRect();}
    function cameraFor(ids,maxK){
      var r=stageRect(),x0=Infinity,y0=Infinity,x1=-Infinity,y1=-Infinity;ids.forEach(function(id){var l=L[id];x0=Math.min(x0,l.x);y0=Math.min(y0,l.y);x1=Math.max(x1,l.x+l.w);y1=Math.max(y1,l.y+bh(l));});if(!ids.length)return null;
      var k=Math.max(.01,Math.min(maxK,(r.width-16)/Math.max(1,x1-x0),(r.height-16)/Math.max(1,y1-y0))),to={k:k,x:(r.left+r.right)/2-(x0+x1)/2*k,y:(r.top+r.bottom)/2-(y0+y1)/2*k};
      // Perspective changes projected bounds. Solve at the requested view, not at a guessed flat rectangle.
      if(!view||view.mode()!=='3d')return to;
      var old=world.style.transform,hr=host.getBoundingClientRect();
      function projected(v){world.style.transform=worldTransform(v);var a=Infinity,b=Infinity,c=-Infinity,d=-Infinity;ids.forEach(function(id){var q=blocks[id].getBoundingClientRect();a=Math.min(a,q.left-hr.left);b=Math.min(b,q.top-hr.top);c=Math.max(c,q.right-hr.left);d=Math.max(d,q.bottom-hr.top);});return {x:(a+c)/2,y:(b+d)/2,w:c-a,h:d-b};}
      for(var i=0;i<8;i++){
        var q=projected(to),factor=Math.min(1,(r.width-16)/Math.max(1,q.w),(r.height-16)/Math.max(1,q.h));to.k*=factor;q=projected(to);
        var px=projected({x:to.x+10,y:to.y,k:to.k}),py=projected({x:to.x,y:to.y+10,k:to.k}),ax=(px.x-q.x)/10,ay=(px.y-q.y)/10,bx=(py.x-q.x)/10,by=(py.y-q.y)/10,det=ax*by-ay*bx,dx=(r.left+r.right)/2-q.x,dy=(r.top+r.bottom)/2-q.y;
        if(Math.abs(det)>.00001){to.x+=(dx*by-dy*bx)/det;to.y+=(dy*ax-dx*ay)/det;}
      }
      world.style.transform=old;return to;
    }
    function fit(anim){var ids=Object.keys(blocks).filter(function(id){return !isHidden(id);});var to=cameraFor(ids,1.2);if(to)cam(to,anim?520:0,true);}
    function undim() { Object.keys(blocks).forEach(function (i) { blocks[i].classList.remove('dim'); }); }
    // the camera goes to a block you opened, but the others stay clickable (focus dims them; opening does not)
    function lookAt(id){var to=cameraFor([id],2.4);if(to)cam(to,520);}
    function focusBlock(id){if(focusId===id){focusId=null;undim();fit(true);return;}focusId=id;Object.keys(blocks).forEach(function(i){blocks[i].classList.toggle('dim',i!==id);});lookAt(id);}
    var trayLiveAt=0;function updateTrayLive(){var now=performance.now();if(now-trayLiveAt>80){trayLiveAt=now;trayDraw();}}
    var trayButtons={},trayLists={},trayRows={hidden:{},outside:{}};
    function trayDraw(){
      var free=stageRect(true),groups={hidden:[],outside:[]};Object.keys(blocks).forEach(function(id){if(layerState.hidden[layerOf(id)])return;if(hid[id])groups.hidden.push(id);else{var r=blocks[id].getBoundingClientRect();if(r.right<free.left+Math.min(80,r.width*.5)||r.left>free.right-Math.min(80,r.width*.5)||r.bottom<free.top+Math.min(32,r.height*.5)||r.top>free.bottom-Math.min(32,r.height*.5))groups.outside.push(id);}});
      ['hidden','outside'].forEach(function(kind){
        if(!trayButtons[kind]){var bt=el('button','hb-btn hb-tray-count'),icon=svg(kind==='hidden'?'M12 5v14M5 12h14':'M8.5 9a3.5 3.5 0 1 1 5.3 3c-1.1.7-1.8 1.3-1.8 2.6M12 19h.01',2.2),count=el('span','',0),list=fadePanel(el('div','hb-tray-list'));bt.type='button';bt.dataset.tray=kind;bt.append(icon,count);list.hidden=true;list.setAttribute('role','dialog');list.setAttribute('aria-label',kind==='hidden'?'Hidden blocks':'Out of view blocks');var title=el('div','hb-list-title',kind==='hidden'?'HIDDEN BLOCKS':'OUT OF VIEW');list.appendChild(title);bt.onclick=function(){list.hidden=!list.hidden;bt.setAttribute('aria-expanded',String(!list.hidden));};tray.appendChild(bt);host.appendChild(list);trayButtons[kind]=bt;trayLists[kind]=list;}
        var bt=trayButtons[kind],list=trayLists[kind],ids=groups[kind],cache=trayRows[kind];bt.querySelector('span').textContent=ids.length;bt.setAttribute('aria-label',(kind==='hidden'?'Hidden':'Out of view')+' blocks, '+ids.length);bt.title=kind==='hidden'?'Hidden blocks':'Blocks out of view';
        Object.keys(cache).forEach(function(id){if(ids.indexOf(id)<0){var row=cache[id];delete cache[id];if(reduce.matches)row.remove();else{row.classList.add('hub-panel-closing');row.style.overflow='hidden';var a=row.animate([{opacity:1,height:row.offsetHeight+'px',minHeight:'0px'},{opacity:0,height:'0px',minHeight:'0px',paddingTop:'0px',paddingBottom:'0px'}],{duration:180,fill:'forwards'});a.onfinish=function(){row.remove();};}}});
        ids.forEach(function(id){if(cache[id])return;var row=el('button','hb-btn',window.__hubNice(blocks[id]._name||id));row.type='button';row.dataset.restore=id;row.onclick=function(){revealLayer(id);hid[id]=0;applyBlock(id);resolve(id);save();lookAt(id);trayDraw();list.hidden=true;};cache[id]=row;list.appendChild(row);if(!reduce.matches)row.animate([{opacity:0,height:'0px',minHeight:'0px',paddingTop:'0px',paddingBottom:'0px'},{opacity:1,height:row.offsetHeight+'px',minHeight:'0px'}],{duration:180});});
        var empty=list.querySelector('.hb-tray-empty');if(!ids.length&&!empty)list.appendChild(el('p','hb-tray-empty','No blocks here.'));else if(ids.length&&empty)empty.remove();if(!list.hidden)positionPopup(list);
      });
    }
    // The wheel moves you around the board; Ctrl + wheel (or a trackpad pinch, which arrives the same way) zooms toward the pointer.
    function zoomAt(px, py, factor) { var k = Math.min(2.6, Math.max(.3, V.k * factor)); V.x = px - (px - V.x) * (k / V.k); V.y = py - (py - V.y) * (k / V.k); V.k = k; place(); }
    // A list inside a block that can still scroll the way the wheel turns takes the wheel; when it is at its end (or there is none) the board pans. Same rule in a small window and a large one.
    function innerScroller(t, dy) {
      for (var n = t; n && n !== host; n = n.parentElement) {
        if (n.nodeType !== 1) continue; var cs = getComputedStyle(n);
        if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll') && n.scrollHeight > n.clientHeight + 1 && (dy < 0 ? n.scrollTop > 0 : n.scrollTop + n.clientHeight < n.scrollHeight - 1)) return n;
      }
      return null;
    }
    function onWheel(e) {
      if (!e.ctrlKey && !e.shiftKey && !e.altKey && e.deltaY && innerScroller(e.target, e.deltaY)) { if (view && view.mode() === '3d') { var sc = innerScroller(e.target, e.deltaY); e.preventDefault(); sc.scrollTop += e.deltaMode === 1 ? e.deltaY * 32 : e.deltaY; } return; }
      e.preventDefault(); hideHint(); touched = true; var target = physics.target() || { x: V.x, y: V.y, k: V.k }; stopCam(); if (focusId) { focusId = null; undim(); }
      var r = host.getBoundingClientRect();
      if (view && view.wheel(e, target, r, function (t) { physics.aim(t); })) return;
      if (e.ctrlKey) { var k = Math.min(2.6, Math.max(.3, target.k * Math.exp(-e.deltaY * .004))), px = e.clientX - r.left, py = e.clientY - r.top; physics.aim({ x: px - (px - target.x) * k / target.k, y: py - (py - target.y) * k / target.k, k: k }); return; }
      var dx = e.deltaX, dy = e.deltaY; if (e.shiftKey && !dx) { dx = dy; dy = 0; }
      if (e.deltaMode === 1) { dx *= 32; dy *= 32; }
      target.x -= dx; target.y -= dy; physics.aim(target);
    }
    // the how-to line fades once you have used the board (or after a while) so it never sits on top of a block
    function hideHint() { hint.style.opacity = '0'; }
    var hintTimer = setTimeout(hideHint, 12000); host.addEventListener('pointerdown', hideHint, { once: true });
    host.addEventListener('wheel', onWheel, { passive: false });
    // Two fingers: pinch to zoom around the point between them (a trackpad pinch arrives as Ctrl + wheel and is handled above).
    var pts = {}, pinch = null;
    function two() { var k = Object.keys(pts); return k.length === 2 ? [pts[k[0]], pts[k[1]]] : null; }
    host.addEventListener('pointerdown', function (e) { if (e.pointerType !== 'touch' || e.target.closest('.hb-bar,.hb-more-menu,.hb-session-detail,.hb-gizmo,.hb-tray,.hb-map,.hb-batch-controls,.hb-jump,.hb-right-panel,.hands-log,.hb-glass-panel,#voice,.hb-layer-menu,.hb-ctx')) return; pts[e.pointerId] = [e.clientX, e.clientY]; var p = two(); if (p) { stopCam(); touched = true; var r = host.getBoundingClientRect(), cx = (p[0][0] + p[1][0]) / 2 - r.left, cy = (p[0][1] + p[1][1]) / 2 - r.top; pinch = { d: Math.hypot(p[0][0] - p[1][0], p[0][1] - p[1][1]) || 1, k: V.k, wx: (cx - V.x) / V.k, wy: (cy - V.y) / V.k }; } }, true);
    host.addEventListener('pointermove', function (e) { if (!pts[e.pointerId]) return; pts[e.pointerId] = [e.clientX, e.clientY]; var p = two(); if (!p || !pinch) return; var r = host.getBoundingClientRect(), cx = (p[0][0] + p[1][0]) / 2 - r.left, cy = (p[0][1] + p[1][1]) / 2 - r.top, k = Math.min(2.6, Math.max(.3, pinch.k * Math.hypot(p[0][0] - p[1][0], p[0][1] - p[1][1]) / pinch.d)); V.k = k; V.x = cx - pinch.wx * k; V.y = cy - pinch.wy * k; place(); }, true);
    ['pointerup', 'pointercancel'].forEach(function (t) { host.addEventListener(t, function (e) { delete pts[e.pointerId]; if (Object.keys(pts).length < 2) pinch = null; }, true); });
    host.addEventListener('pointerdown', function (e) {
      if (e.button || e.target.closest('.hk,.hb-bar,.hb-more-menu,.hb-session-detail,.hb-gizmo,.hb-tray,.hb-map,.hb-batch-controls,.hb-jump,.hb-right-panel,.hands-log,.hb-glass-panel,#voice,.hb-layer-menu,.hb-ctx')) return;
      touched = true; stopCam(); host.classList.add('panning'); var sx = e.clientX - V.x, sy = e.clientY - V.y;
      var lastX = e.clientX, lastY = e.clientY, lastT = performance.now(), vx = 0, vy = 0;
      function mv(ev) { if (pinch || Object.keys(pts).length > 1) { sx = ev.clientX - V.x; sy = ev.clientY - V.y; return; } var now = performance.now(), dt = Math.max(8, now - lastT); vx = vx * .4 + (ev.clientX - lastX) / dt * .6; vy = vy * .4 + (ev.clientY - lastY) / dt * .6; lastX = ev.clientX; lastY = ev.clientY; lastT = now; V.x = ev.clientX - sx; V.y = ev.clientY - sy; place(); }
      function up(event) { host.classList.remove('panning'); removeEventListener('pointermove', mv); removeEventListener('pointerup', up); removeEventListener('pointercancel', up); if ((!event || event.type !== 'pointercancel') && performance.now() - lastT < 100) physics.coast(vx, vy); dragCleanups = []; }
      addEventListener('pointermove', mv); addEventListener('pointerup', up); addEventListener('pointercancel', up); dragCleanups.push(function () { removeEventListener('pointermove', mv); removeEventListener('pointerup', up); removeEventListener('pointercancel', up); });
    });
    host.addEventListener('dblclick', function (e) { if (!e.target.closest('.hk,.hb-btn,.hb-tray')) { focusId = null; undim(); fit(true); } });
    world.addEventListener('pointerdown', function (e) {
      var b = e.target.closest('.hk'); if (!b || e.button) return;
      if(host.classList.contains('hb-3d')){var projected=document.elementFromPoint(e.clientX,e.clientY);if(projected&&b.contains(projected)&&projected.closest('button,a,[role=button]')){touched=true;stopCam();return;}} var id = b.dataset.id, l = L[id]; touched = true; stopCam();
      var dragRect=host.getBoundingClientRect(), depth=Number.parseFloat(getComputedStyle(b).getPropertyValue('--hb-dz'))||0,lift=Number.parseFloat(getComputedStyle(b).getPropertyValue('--hb-dy'))||0;
      function point(ev){if(view){var w=view.toWorld(ev.clientX,ev.clientY,depth,dragRect);return w&&typeof w.y==='number'?{x:w.x,y:w.y-lift}:w;}return {x:(ev.clientX-dragRect.left-V.x)/V.k,y:(ev.clientY-dragRect.top-V.y)/V.k};}
      var press=point(e);
      if (e.target.closest('.hk-rz')) {
        e.preventDefault(); var sw = l.w, sh = l.h, sx = e.clientX, sy = e.clientY;
        var mv = function (ev) { var p=point(ev);l.w = Math.max(130, sw + p.x-press.x); l.h = Math.max(70, sh + p.y-press.y); applyBlock(id); };
        var up = function () { removeEventListener('pointermove', mv); removeEventListener('pointerup', up); removeEventListener('pointercancel', up); l.u = 1; l.rz = 1; resolve(id); save(); dragCleanups = []; };
        addEventListener('pointermove', mv); addEventListener('pointerup', up); addEventListener('pointercancel', up); dragCleanups.push(function () { removeEventListener('pointermove', mv); removeEventListener('pointerup', up); removeEventListener('pointercancel', up); }); return;
      }
      if (e.target.closest('button')) return;
      var grab = e.target.closest('.hk-h') || (b._open && !l.exp ? b : null); if (!grab) return;
      e.preventDefault(); if(b._flip)b._flip.cancel(); b.classList.remove('settle'); l.z = ++zTop; applyBlock(id); if (stackDepth) stackDepth(); b.classList.add('pick'); host.classList.add('hb-dragging');
      var sx2 = e.clientX, sy2 = e.clientY, ox = l.x, oy = l.y, moved = false, multiTouch = false, dragFrame = 0;
      function drawDrag(){dragFrame=0;if(b._solid)b._solid.style.transform='translate3d('+(l.x-ox)+'px,'+(l.y-oy)+'px,0)';b.style.transform='translate3d('+(l.x-ox)+'px,'+(l.y-oy)+'px,0)';if(nav)nav.refresh();updateTrayLive();}
      function mv2(ev) { if(pinch||Object.keys(pts).length>1){multiTouch=true;return;}if(bin)bin.classList.toggle('drop-target',overBin(ev));var dx = ev.clientX - sx2, dy = ev.clientY - sy2; if (Math.abs(dx) + Math.abs(dy) > 5) moved = true; var p=point(ev); l.x = ox + p.x-press.x; l.y = oy + p.y-press.y; guides.snap(id, false); if(!dragFrame)dragFrame=requestAnimationFrame(drawDrag); }
      function up2(event) { removeEventListener('pointermove', mv2); removeEventListener('pointerup', up2); removeEventListener('pointercancel', up2); if(dragFrame)cancelAnimationFrame(dragFrame);b.style.transform='';if(b._solid)b._solid.style.transform=''; b.classList.remove('pick'); applyBlock(id); host.classList.remove('hb-dragging'); if(moved&&event&&event.type!=='pointercancel'&&overBin(event)){hideBlock(id);bin.classList.remove('drop-target');guides.clear();dragCleanups=[];return;}if(bin)bin.classList.remove('drop-target');if (moved) { var before = b.getBoundingClientRect(); guides.snap(id, true); l.u = 1; applyBlock(id); resolve(id); if (motion) motion.flip(b, before, V.k, 'drop'); } guides.clear();save();trayDraw();dragCleanups = []; if ((!event || event.type !== 'pointercancel') && !moved && !multiTouch && !l.exp) { if (l.min) { l.min = 0; applyBlock(id); resolve(id); save(); } else if (b._open) b._open(); } }
      addEventListener('pointermove', mv2); addEventListener('pointerup', up2); addEventListener('pointercancel', up2); dragCleanups.push(function () { removeEventListener('pointermove', mv2); removeEventListener('pointerup', up2); removeEventListener('pointercancel', up2); });
    });
    world.addEventListener('click', function (e) {
      var bt = e.target.closest('button[data-a]'); if (!bt) return; var id = bt.closest('.hk').dataset.id, a = bt.dataset.a;
      if(a==='stop'){stopApp(id);return;}
      if (a === 'dup') { duplicate(id); return; }
      if ((a === 'col' || a === 'x') && id.indexOf('#') > 0) { closeWindow(id); return; }
      if (a === 'col') collapse(id);
      if (a === 'out') { var bb = blocks[id]; if (bb._url) window.open(bb._url, '_blank'); else if (bb._app && typeof openApp === 'function') openApp(bb._app.id, bb._app.name); }
      if (a === 'min') { L[id].min = L[id].min ? 0 : 1; applyBlock(id); resolve(id); save(); }
      if (a === 'foc') focusBlock(id);
      if (a === 'x') hideBlock(id);
    });
    // RIGHT CLICK (mouse, or the thumb-to-middle-finger press of HANDS): a small menu of what can be done to the thing under the pointer.
    // On a block it lists that block's own title-bar actions (so it can never offer something the buttons do not), on the empty board the board's actions.
    var ctxMenu = null, ctxDown = null;
    function closeCtx() { if (ctxMenu) { ctxMenu.remove(); ctxMenu = null; } }
    function openCtx(x, y, items, label) {
      closeCtx(); if (!items.length) return;
      var m = el('div', 'hb-ctx'); m.setAttribute('role', 'menu'); m.setAttribute('aria-label', label);
      items.forEach(function (it) { var b = el('button', 'hb-btn', it[0]); b.type = 'button'; b.setAttribute('role', 'menuitem'); b.onclick = function () { closeCtx(); it[1](); }; m.appendChild(b); });
      host.appendChild(m); ctxMenu = m;
      var hr = host.getBoundingClientRect(), w = m.offsetWidth, h = m.offsetHeight;
      m.style.left = Math.max(6, Math.min(x - hr.left, hr.width - w - 6)) + 'px'; m.style.top = Math.max(6, Math.min(y - hr.top, hr.height - h - 6)) + 'px';
      var first = m.querySelector('button'); if (first) first.focus({ preventScroll: true });
    }
    host.addEventListener('pointerdown', function (e) { if (e.button === 2) ctxDown = [e.clientX, e.clientY]; if (ctxMenu && !ctxMenu.contains(e.target)) closeCtx(); }, true);
    host.addEventListener('contextmenu', function (e) {
      if ((e.defaultPrevented&&!(view&&view.mode()==='3d'&&[host,world,stageClip].indexOf(e.target)>=0)) || e.target.closest('.hb-bar,.hb-viewbar,.hb-tray,.hb-more-menu,.hb-ctx,.hb-session-detail,.hb-gizmo,.hb-map,.hb-batch-controls,.hb-jump,.hb-right-panel,.hands-log,.hb-glass-panel,#voice,.hb-layer-menu,.hb-ctx')) return;
      e.preventDefault();
      if (ctxDown && Math.abs(e.clientX - ctxDown[0]) + Math.abs(e.clientY - ctxDown[1]) > 8) return;        // the end of a right-drag turn is not a request for a menu
      var blk = e.target.closest('.hk');
      if (blk) {
        var id = blk.dataset.id, items = [];
        Array.prototype.forEach.call(blk.querySelectorAll('.hk-h button[data-a]'), function (b) { if (!b.hidden && b.title) items.push([b.title.toUpperCase(), function () { b.click(); }]); });
        ['system','tools','apps'].forEach(function(key){items.push(['MOVE TO LAYER: '+key.toUpperCase(),function(){changeLayer(id,key);}]);});openCtx(e.clientX, e.clientY, items, (blocks[id]._name || id) + ' actions');
      } else {
        var items2 = [['RESET LAYOUT',resetLayout],['TIDY', function () { tidyBtn.click(); }], ['FIT EVERYTHING', function () { fitBtn.click(); }]];
        if (view) items2.push([view.btn.textContent === 'VIEW: 3D' ? 'SWITCH TO 2D' : 'SWITCH TO 3D', function () { view.btn.click(); }]);
        items2.push(['BLOCKS LIST', function () { blocksBtn.click(); }], ['TALK', function () { talkBtn.click(); }]);
        openCtx(e.clientX, e.clientY, items2, 'Board actions');
      }
    });
    function ctxKey(e) { if (e.key === 'Escape') closeCtx(); }
    document.addEventListener('keydown', ctxKey, true); addEventListener('blur', closeCtx);
    world.addEventListener('dblclick', function (e) { var h = e.target.closest('.hk-h'); if (h && !e.target.closest('button')) focusBlock(h.closest('.hk').dataset.id); });
    // the old cards' controls, reached from the bar: they stay in the page (hidden) and the bar buttons press them
    ingestBtn.onclick = function () { var c = document.querySelector('.ingest-card'); if (c) c.click(); };
    talkBtn.removeAttribute('onclick');talkBtn.setAttribute('data-talk','');talkBtn.title='Talk to the Hub\nAlt-click to open chat';
    pcBtn.onclick = function () { var w = document.getElementById('mcp-wire'); if (w) w.click(); };
    blocksBtn.onclick = function () { if(typeof closeMore==='function')closeMore();if (nav && nav.toggle) nav.toggle(); };
    function legacy() { var w = document.getElementById('mcp-wire'); if (w) { pcBtn.className = 'hb-btn hb-pc ' + (w.classList.contains('off') ? 'off' : 'on'); pcBtn.title = w.title || 'PC control'; pcBtn.disabled = !!w.disabled; pcBtn.setAttribute('aria-label','PC control');pcBtn.setAttribute('aria-pressed',String(!w.classList.contains('off'))); } talkBtn.hidden = !document.querySelector('[data-talk]'); ingestBtn.hidden = !document.querySelector('.ingest-card'); pcBtn.hidden = !w; var issues = document.querySelectorAll('#setup-banner .setup-issue').length; setupBtn.hidden = !issues; setupBtn.textContent = 'SETUP · ' + issues; }
    zin.onclick = function () { touched = true; stopCam(); var r = host.getBoundingClientRect(); zoomAt(r.width / 2, r.height / 2, 1.25); };
    zout.onclick = function () { touched = true; stopCam(); var r = host.getBoundingClientRect(); zoomAt(r.width / 2, r.height / 2, 0.8); };
    fitBtn.onclick = function () { focusId = null; undim(); fit(true); };
    function resetLayout() {
      stopCam();
      defs.forEach(function (d) { var l = L[d[0]]; hid[d[0]] = 0; l.u = 0; l.rz = 0; l.min = 0; l.from = null; if (!l.exp) { l.w = d[1].w; } });
      autosize(); var T = grid(), from = {}; touched = false;
      defs.forEach(function (d) { var l = L[d[0]]; from[d[0]] = { x: l.x, y: l.y }; });
      var t0 = performance.now(); focusId = null; undim();
      (function s(n) { if (!alive) return; var u = Math.min(1, (n - t0) / (motion.allowed() ? 620 : 1)), e = 1 - Math.pow(1 - u, 3.4);
        defs.forEach(function (d) { var f = from[d[0]], t = T[d[0]], l = L[d[0]]; if (l.exp) return; l.x = f.x + (t.x - f.x) * e; l.y = f.y + (t.y - f.y) * e; applyBlock(d[0]); });
        if (u < 1) requestAnimationFrame(s); else { relayout(); save(); trayDraw(); fit(true); } })(t0);
    }
    // All three commands share one packer. Minimise changes only the title-bar flag;
    // w/h remain the saved full size, including an already-open tool window.
    var settlePack=null;
    function arrangeLayerBands(minimise){
      if(settlePack)settlePack();
      stopCam();touched=true;focusId=null;undim();var ids=Object.keys(blocks).filter(function(id){return !isHidden(id);});
      if(!ids.length)return;
      ids.sort(function(a,b){return L[a].y-L[b].y||L[a].x-L[b].x;});
      var from={},to={},unit=16;
      ids.forEach(function(id){var l=L[id];from[id]={x:l.x,y:l.y};if(minimise!==null)l.min=minimise?1:0;});
      // One band per layer, in the order of the layer list (front layer first; INVERT flips it). Rows are as wide as the window allows:
      // try a range of widths and keep the one that lets the whole board be shown largest.
      var r=stageRect(),order=layerState.invert?layerState.order.slice():layerState.order.slice().reverse();
      function packAt(width){var y=0,pos={};order.forEach(function(layer){var band=ids.filter(function(id){return layerOf(id)===layer;});if(!band.length)return;var x=0,row=0;
        band.forEach(function(id){var l=L[id];if(x&&x+l.w>width){x=0;y+=Math.ceil((row+GAP)/unit)*unit;row=0;}pos[id]={x:x,y:y};x+=Math.ceil((l.w+GAP)/unit)*unit;row=Math.max(row,bh(l));});y+=Math.ceil((row+GAP*2)/unit)*unit;});
        var W=0;ids.forEach(function(id){W=Math.max(W,pos[id].x+L[id].w);});return {pos:pos,W:W,H:y};}
      var minW=0,sumW=0;ids.forEach(function(id){minW=Math.max(minW,L[id].w);sumW+=L[id].w+GAP;});
      var best=null;for(var wi=0;wi<=18;wi++){var wd=minW+(sumW-minW)*Math.pow(wi/18,1.6),pk=packAt(wd),kk=Math.min((r.width-16)/Math.max(1,pk.W),(r.height-16)/Math.max(1,pk.H));if(!best||kk>=best.k-1e-6)best={k:kk,pk:pk};}
      ids.forEach(function(id){var l=L[id],q=best.pk.pos[id];l.x=q.x;l.y=q.y;l.u=1;to[id]={x:q.x,y:q.y};});
      // The 3D fit solver measures DOM bounds, so measure the destination layout,
      // then restore it synchronously before the first animated paint.
      ids.forEach(applyBlock);if(stackDepth)stackDepth();
      var cto=cameraFor(ids,1.2);
      if(reducedMotion.matches){ids.forEach(applyBlock);if(cto){V=cto;place();}save();trayDraw();return;}
      ids.forEach(function(id){L[id].x=from[id].x;L[id].y=from[id].y;applyBlock(id);});
      var cf={x:V.x,y:V.y,k:V.k},tok=++camTok,t0=performance.now();
      var finished=false;
      function finishPack(){if(finished)return;finished=true;settlePack=null;ids.forEach(function(id){if(L[id]){L[id].x=to[id].x;L[id].y=to[id].y;applyBlock(id);}});if(alive){if(stackDepth)stackDepth();save();trayDraw();}}
      settlePack=finishPack;
      (function s(n){if(finished)return;if(!alive||tok!==camTok){finishPack();return;}
        var u=Math.min(1,(n-t0)/620),e=1-Math.pow(1-u,3.4);
        ids.forEach(function(id){var l=L[id];if(!l)return;l.x=from[id].x+(to[id].x-from[id].x)*e;l.y=from[id].y+(to[id].y-from[id].y)*e;applyBlock(id);});
        if(cto){V={x:cf.x+(cto.x-cf.x)*e,y:cf.y+(cto.y-cf.y)*e,k:cf.k+(cto.k-cf.k)*e};place();}
        if(u<1)requestAnimationFrame(s);else{finishPack();}})(t0);
    }
    // TIDY only neatens what you left: every block snaps to the grid, tops and left edges that were nearly level are made level, and a block that
    // overlaps another one in the SAME layer steps to the nearest free place. Nothing changes layer, size, minimised or hidden state, and the camera stays.
    // (MINIMISE ALL / MAXIMISE ALL are the ones that deal everything out again, one band per layer.)
    function tidyInPlace(){
      if(settlePack)settlePack();
      stopCam();touched=true;focusId=null;undim();
      var U=16,G=GAP,ids=Object.keys(blocks).filter(function(id){return !isHidden(id)&&L[id]&&!L[id].exp;});
      ids.sort(function(a,b){return L[a].y-L[b].y||L[a].x-L[b].x;});
      var from={},to={},placed={};
      function snap(v){return Math.round(v/U)*U;}
      function free(list,x,y,w,h){return !list.some(function(m){return x<m.x+m.w+G&&m.x<x+w+G&&y<m.y+m.h+G&&m.y<y+h+G;});}
      ids.forEach(function(id){
        var l=L[id],w=l.w,h=bh(l),x=snap(l.x),y=snap(l.y),key=(view&&view.mode()==='3d')?layerOf(id):'all',list=placed[key]||(placed[key]=[]);   // in 3D the layers are apart in depth; flat, everything shares one plane
        from[id]={x:l.x,y:l.y};
        list.forEach(function(m){                                                          // nearly level with a neighbour: make it level
          if(m.y!==y&&Math.abs(m.y-y)<=24&&free(list,x,m.y,w,h))y=m.y;
          if(m.x!==x&&Math.abs(m.x-x)<=24&&free(list,m.x,y,w,h))x=m.x;
        });
        for(var n=0;n<120&&!free(list,x,y,w,h);n++){                                       // overlapping: the nearest free place around the block in the way
          var m=list.filter(function(k){return x<k.x+k.w+G&&k.x<x+w+G&&y<k.y+k.h+G&&k.y<y+h+G;})[0];if(!m)break;
          var cands=[[x,snap(m.y+m.h+G+U-1)],[snap(m.x+m.w+G+U-1),y],[snap(m.x-w-G),y],[x,snap(m.y-h-G)]];
          cands=cands.filter(function(c){return free(list,c[0],c[1],w,h);}).sort(function(a,b){return Math.abs(a[0]-x)+Math.abs(a[1]-y)-Math.abs(b[0]-x)-Math.abs(b[1]-y);});
          if(cands.length){x=cands[0][0];y=cands[0][1];}else y=snap(m.y+m.h+G+U-1);
        }
        if(!free(list,x,y,w,h))y=snap(list.reduce(function(a,m){return Math.max(a,m.y+m.h);},0)+G+U-1);
        list.push({x:x,y:y,w:w,h:h});to[id]={x:x,y:y};
      });
      ids.forEach(function(id){L[id].u=1;});
      if(reducedMotion.matches){ids.forEach(function(id){L[id].x=to[id].x;L[id].y=to[id].y;applyBlock(id);});save();trayDraw();return;}
      var tok=++camTok,t0=performance.now(),finished=false;
      function finishPack(){if(finished)return;finished=true;settlePack=null;ids.forEach(function(id){if(L[id]){L[id].x=to[id].x;L[id].y=to[id].y;applyBlock(id);}});if(alive){if(stackDepth)stackDepth();save();trayDraw();}}
      settlePack=finishPack;
      (function step(n){if(finished)return;if(!alive||tok!==camTok){finishPack();return;}
        var u=Math.min(1,(n-t0)/420),e=1-Math.pow(1-u,3.4);
        ids.forEach(function(id){var l=L[id];if(!l)return;l.x=from[id].x+(to[id].x-from[id].x)*e;l.y=from[id].y+(to[id].y-from[id].y)*e;applyBlock(id);});
        if(u<1)requestAnimationFrame(step);else finishPack();})(t0);
    }
    tidyBtn.onclick=function(){hubNote('TIDY: blocks packed'+(view&&view.mode()==='3d'?' by layer':''));if(view&&view.mode()==='3d')arrangeLayerBands(null);else tidyInPlace();};
    readBoardPrefs();
    var batchControls=el('div','hb-batch-controls'),minAll=el('button','hb-btn','MINIMISE ALL'),maxAll=el('button','hb-btn','MAXIMISE ALL');
    batchControls.setAttribute('role','group');batchControls.setAttribute('aria-label','Arrange all shown blocks');
    minAll.type=maxAll.type='button';minAll.setAttribute('aria-label','MINIMISE ALL');maxAll.setAttribute('aria-label','MAXIMISE ALL');minAll.textContent=maxAll.textContent='';minAll.appendChild(svg('M4 6h16M6 12h12M8 18h8'));maxAll.appendChild(svg('M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5'));minAll.dataset.batch='minimise';maxAll.dataset.batch='maximise';
    minAll.title='Collapse shown blocks into layer bands';maxAll.title='Restore shown blocks to full size in layer bands';
    minAll.onclick=function(){arrangeLayerBands(true);};maxAll.onclick=function(){arrangeLayerBands(false);};
    batchControls.appendChild(minAll);batchControls.appendChild(maxAll);host.appendChild(batchControls);
    var wire = document.getElementById('mcp-wire'), wireWatch = wire && window.MutationObserver ? new MutationObserver(legacy) : null;   // the bar mirrors the page's PC-control button the moment it changes, not at the next 10 s poll
    var banner = document.getElementById('setup-banner'), bannerWatch = banner && window.MutationObserver ? new MutationObserver(legacy) : null;   // the banner is hidden under the board; its issues show as a SETUP button
    if (bannerWatch) bannerWatch.observe(banner, { childList: true });
    if (wireWatch) wireWatch.observe(wire, { attributes: true, attributeFilter: ['class', 'title', 'disabled'] });
    function onKey(e) { if (nav && nav.key(e)) return; if (e.key === 'Escape' && focusId) { focusId = null; undim(); fit(true); } }
    nav = __hubBoardNav.mount(host, blocks, L, new Proxy(hid,{get:function(target,id){return isHidden(String(id));}}), function () { return V; }, function (id, point) { touched = true; stopCam(); if (id) { revealLayer(id);if (hid[id]) { hid[id] = 0; applyBlock(id); resolve(id); trayDraw(); save(); } lookAt(id); } else {var free=stageRect();cam({x:(free.left+free.right)/2-point.x*V.k,y:(free.top+free.bottom)/2-point.y*V.k,k:V.k},350);}; }, expand, collapse);
    document.addEventListener('keydown', onKey);
    var resizeFrame=0; function onResize() { document.documentElement.style.setProperty('--hub-visible-top',(window.visualViewport?visualViewport.offsetTop:0)+'px');document.documentElement.style.setProperty('--hub-visible-height',(window.visualViewport?visualViewport.height:innerHeight)+'px');if(resizeFrame)return;resizeFrame=requestAnimationFrame(function(){resizeFrame=0;if(!alive)return;setTop();relayout();if(!touched)fit(false);}); }
    addEventListener('resize', onResize);if(window.visualViewport)visualViewport.addEventListener('resize',onResize);onResize();setTop();
    relayout(); trayDraw(); paint(); requestAnimationFrame(function () { setTop(); fit(false); });
    var hands = window.HubHandsBoard ? HubHandsBoard.mount({host:host,bar:bar,fitButton:fitBtn}) : null;
    var CONTROL_HOME={talk:'actions',pc:'actions',ingest:'ingest',setup:'actions',hands:'ingest',handSetup:'hands',saveTrace:'hands',legend:'hands',graphics:'health',readout:'view',view:'view',axis:'view',zoom:'view',fit:'view',blocks:'view',tidy:'view',layers:'view'};
    var more=el('button','hb-btn hb-hands-menu-button',''),menu=el('div','hb-more-menu');more.appendChild(svg('M5 9l7 7 7-7'));more.type='button';more.title='Hand control options';more.setAttribute('aria-label','Hand control options');more.setAttribute('aria-expanded','false');menu.hidden=true;menu.setAttribute('role','group');menu.setAttribute('aria-label','Hand control options');bar.appendChild(more);host.appendChild(menu);
    function closeMore(){menu.hidden=true;more.setAttribute('aria-expanded','false');}
    more.onclick=function(){menu.hidden=!menu.hidden;more.setAttribute('aria-expanded',String(!menu.hidden));};
    var rightPanel=fadePanel(el('aside','hb-right-panel')),ingestDock=el('div','hb-ingest-dock'),rightScroll=el('div','hb-right-scroll'),viewBar=el('div','hb-viewbar'),zoomRow=el('div','hb-zoomrow');viewBar.setAttribute('role','group');viewBar.setAttribute('aria-label','View controls');zoomRow.append(zout,zin);viewBar.append(zh);if(view)viewBar.append(view.btn,view.gizmoBtn);viewBar.append(fitBtn,tidyBtn,blocksBtn,zoomRow);rightScroll.appendChild(viewBar);rightPanel.appendChild(rightScroll);ingestDock.classList.add('hb-top-tools');host.append(ingestDock,rightPanel);
    var controls={readout:zh,view:view&&view.btn,axis:view&&view.gizmoBtn,zoom:zoomRow,fit:fitBtn,blocks:blocksBtn,tidy:tidyBtn,talk:talkBtn,pc:pcBtn,ingest:ingestBtn,setup:setupBtn,hands:hands&&hands.button};
    Array.from(bar.children).forEach(function(b){if(b.textContent==='HAND SETUP')controls.handSetup=b;if(b.textContent==='SAVE TRACE')controls.saveTrace=b;});
    var legend=el('button','hb-btn','HAND CONTROLS');legend.type='button';controls.legend=legend;
    legend.onclick=function(){var d=document.querySelector('.hands-setup');if(d&&!d.hidden&&d.querySelector('.hs-table')){var x=d.querySelector('.hs-x');if(x)x.click();}else openHandControls();};
    var logPending=[];function toLog(node){if(node===controls.handSetup||node===controls.saveTrace){node.remove();return;}var t=document.querySelector('.hands-log .hl-tools');if(t){if(node.parentNode!==t)t.appendChild(node);}else if(logPending.indexOf(node)<0)logPending.push(node);}function onLogReady(){var all=logPending.slice();[controls.legend].forEach(function(n){if(n&&all.indexOf(n)<0)all.push(n);});all.forEach(toLog);logPending=[];}window.addEventListener('hub-log-ready',onLogReady);
    function placeControl(key,node){if(!node)return;var home=CONTROL_HOME[key];if(home==='hands')toLog(node);else if(home==='health'){if(node.parentNode!==blocks.hlt._in)blocks.hlt._in.appendChild(node);}else if(home==='ingest')ingestDock.appendChild(node);else if(home==='view')viewBar.appendChild(node);else bar.appendChild(node);}
    Object.keys(controls).forEach(function(k){placeControl(k,controls[k]);});if(view)viewBar.append(view.btn);viewBar.append(fitBtn,tidyBtn,blocksBtn);if(view)viewBar.append(view.gizmoBtn);viewBar.append(zoomRow);zoomRow.dataset.only3d='1';zh.dataset.only3d='1';hint.hidden=true;menu.appendChild(hint);more.hidden=true;
    var layerButton=el('button','hb-btn','LAYERS'),layerMenu=el('div','hb-layer-menu');layerButton.type='button';layerButton.dataset.layers='1';layerButton.setAttribute('aria-expanded','false');layerMenu.hidden=true;layerMenu.setAttribute('aria-label','Layers');host.appendChild(layerMenu);placeControl('layers',layerButton);
    function commitLayers(quiet){host.classList.add('hb-layer-moving');saveLayers();refreshLayers();setTimeout(function(){host.classList.remove('hb-layer-moving');},350);if(!quiet)arrangeLayerBands(null);}
    // The layer list: drag a layer by its grip to put it in front of or behind another, drag an app onto a layer to move it there,
    // fold a layer so its apps are out of the way, and (in 3D) choose whether layers sit apart in depth, in height or both.
    function dragThing(grip,source,kind,done){
      grip.addEventListener('pointerdown',function(e){
        if(e.button&&e.pointerType==='mouse')return;e.preventDefault();e.stopPropagation();
        try{grip.setPointerCapture(e.pointerId);}catch(x){}
        source.classList.add('dragging');var target=null,after=false;
        function clear(){layerMenu.querySelectorAll('.drop-before,.drop-after,.drop-into').forEach(function(n){n.classList.remove('drop-before','drop-after','drop-into');});}
        function over(ev){
          clear();var hit=document.elementFromPoint(ev.clientX,ev.clientY),sec=hit&&hit.closest('.hb-layer-section');target=null;
          if(!sec||!layerMenu.contains(sec))return;
          if(kind==='layer'){if(sec===source)return;var r=sec.getBoundingClientRect();after=ev.clientY>r.top+r.height/2;sec.classList.add(after?'drop-after':'drop-before');target=sec;}
          else{if(sec.dataset.layer===source.dataset.from)return;sec.classList.add('drop-into');target=sec;}
        }
        function move(ev){over(ev);var box=layerMenu.getBoundingClientRect();if(ev.clientY<box.top+28)layerMenu.scrollTop-=12;else if(ev.clientY>box.bottom-28)layerMenu.scrollTop+=12;}
        function end(ev){
          grip.removeEventListener('pointermove',move);grip.removeEventListener('pointerup',end);grip.removeEventListener('pointercancel',end);
          try{grip.releasePointerCapture(e.pointerId);}catch(x){}
          over(ev);source.classList.remove('dragging');var t=target;clear();if(t&&ev.type==='pointerup')done(t,after);
        }
        grip.addEventListener('pointermove',move);grip.addEventListener('pointerup',end);grip.addEventListener('pointercancel',end);
      });
    }
    function drawLayers(){
      var keep=layerMenu.scrollTop;layerMenu.replaceChildren();
      var is3d=host.classList.contains('hb-3d');
      var add=el('form','hb-layer-add'),name=el('input'),create=el('button','hb-btn','ADD LAYER');name.placeholder='Layer name';name.maxLength=40;name.setAttribute('aria-label','New layer name');create.type='submit';create.disabled=layerState.order.length>=32;add.append(name,create);add.onsubmit=function(e){e.preventDefault();var label=name.value.trim();if(!label||layerState.order.length>=32)return;var key='layer-'+Date.now().toString(36);while(layerState.order.includes(key))key+='x';layerState.order.push(key);layerState.labels[key]=label;commitLayers(true);};
      layerMenu.append(add);
      if(is3d){
        var axisRow=el('div','hb-layer-axis');axisRow.appendChild(el('span','','LAYERS SIT APART IN'));
        [['depth','DEPTH','Front to back'],['height','HEIGHT','Top to bottom'],['both','BOTH','Diagonal']].forEach(function(o){var b=el('button','hb-btn',o[1]);b.type='button';b.title=o[2];b.setAttribute('aria-pressed',String((layerState.axis||'depth')===o[0]));b.onclick=function(){layerState.axis=o[0];hubNote('Layers apart in '+o[1].toLowerCase());commitLayers();};axisRow.appendChild(b);});
        var inv=el('button','hb-btn','INVERT');inv.type='button';inv.title='Put the deepest layer at the front or the top instead';inv.setAttribute('aria-pressed',String(!!layerState.invert));inv.onclick=function(){layerState.invert=!layerState.invert;hubNote('Layer order inverted');commitLayers();};axisRow.appendChild(inv);
        layerMenu.appendChild(axisRow);
      }
      layerMenu.appendChild(el('small','','Top of the list is in front. Drag a layer by its grip to reorder it; drag an app onto a layer to move it. TIDY packs each layer into its own band.'));
      layerState.order.slice().reverse().forEach(function(key){
        var section=el('section','hb-layer-section'),row=el('div','hb-layer-row'),ids=Object.keys(blocks).filter(function(id){return layerOf(id)===key;}),folded=!!(layerState.collapsed&&layerState.collapsed[key]);
        section.dataset.layer=key;section.classList.toggle('folded',folded);
        var grip=el('button','hb-btn hb-layer-grip');grip.type='button';grip.title='Drag to move this layer in front of or behind another';grip.setAttribute('aria-label','Drag layer '+layerName(key));grip.appendChild(svg('M5 8h14M5 12h14M5 16h14'));
        var fold=el('button','hb-btn hb-layer-fold');fold.type='button';fold.title=folded?'Show the apps in this layer':'Fold this layer';fold.setAttribute('aria-expanded',String(!folded));fold.setAttribute('aria-label',(folded?'Show apps in ':'Fold ')+layerName(key));fold.appendChild(svg(folded?'M9 6l6 6-6 6':'M6 9l6 6 6-6'));
        fold.onclick=function(){layerState.collapsed=layerState.collapsed||{};layerState.collapsed[key]=!folded;saveLayers();drawLayers();};
        var nameEl=el('b','',layerName(key)+' · '+ids.length);nameEl.title='Double-click to rename';
        function rename(){var inp=el('input');inp.className='hb-layer-name';inp.value=layerName(key);inp.maxLength=40;inp.setAttribute('aria-label','Layer name');nameEl.replaceWith(inp);inp.focus();inp.select();var done=false;
          function finish(ok){if(done)return;done=true;var v=inp.value.trim();if(ok&&v&&v!==layerName(key)){layerState.labels[key]=v;hubNote('Layer renamed to '+v);commitLayers(true);}else drawLayers();}
          inp.onkeydown=function(e){if(e.key==='Enter'){e.preventDefault();finish(true);}else if(e.key==='Escape'){e.preventDefault();finish(false);}};inp.onblur=function(){finish(true);};}
        nameEl.ondblclick=rename;row.classList.toggle('off',!!layerState.hidden[key]);row.append(grip,fold,nameEl);
        function action(label,path,fn,disabled){var btn=el('button','hb-btn');btn.type='button';btn.title=label;btn.setAttribute('aria-label',label+' '+layerName(key));btn.appendChild(svg(path));btn.disabled=!!disabled;btn.onclick=fn;row.appendChild(btn);return btn;}
        action('Rename layer','M4 20h4l10-10-4-4L4 16v4zM13 7l4 4',rename);
        var off=!!layerState.hidden[key],eye=action(off?'Show this layer':'Hide this layer',off?'M3 3l18 18M10.6 6.2A9.8 9.8 0 0 1 12 6c6 0 10 6 10 6a17 17 0 0 1-3.2 3.8M6.5 7.6C3.9 9.4 2 12 2 12s4 7 10 7a9.6 9.6 0 0 0 4-.9M9.9 10a3 3 0 0 0 4.1 4.1':'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM9 12a3 3 0 1 0 6 0 3 3 0 1 0-6 0',function(){layerState.hidden[key]=!layerState.hidden[key];hubNote('Layer '+layerName(key)+(layerState.hidden[key]?' hidden':' shown'));commitLayers();});eye.setAttribute('aria-pressed',String(!off));eye.classList.toggle('is-off',off);
        function shift(by){var i=layerState.order.indexOf(key),j=i+by;if(j<0||j>=layerState.order.length)return;layerState.order.splice(i,1);layerState.order.splice(j,0,key);commitLayers();}
        action('Move forward','M6 14l6-6 6 6',function(){shift(1);},layerState.order.indexOf(key)===layerState.order.length-1);
        action('Move backward','M6 10l6 6 6-6',function(){shift(-1);},layerState.order.indexOf(key)===0);
        var removal=el('div','hb-layer-remove');removal.hidden=true;
        action('Remove layer','M6 6l12 12M18 6L6 18',function(){removal.hidden=!removal.hidden;},layerState.order.length===1);
        var target=el('select');target.setAttribute('aria-label','Move removed layer blocks to');layerState.order.filter(function(k){return k!==key;}).forEach(function(k){var o=el('option','',layerName(k));o.value=k;target.appendChild(o);});var confirm=el('button','hb-btn','MOVE BLOCKS AND REMOVE');confirm.type='button';confirm.onclick=function(){var dest=target.value;if(!dest)return;Object.keys(blocks).forEach(function(id){if(layerOf(id)===key){if(layerState.hidden[key])hid[id]=1;layerState.members[id.split('#')[0]]=dest;}});Object.keys(layerState.members).forEach(function(id){if(layerState.members[id]===key)layerState.members[id]=dest;});layerState.order.splice(layerState.order.indexOf(key),1);delete layerState.labels[key];delete layerState.hidden[key];if(layerState.collapsed)delete layerState.collapsed[key];commitLayers();save();};removal.append(target,confirm);section.append(row,removal);
        dragThing(grip,section,'layer',function(t,after){
          var shown=layerState.order.slice().reverse(),from=shown.indexOf(key);shown.splice(from,1);var to=shown.indexOf(t.dataset.layer)+(after?1:0);shown.splice(to,0,key);layerState.order=shown.reverse();commitLayers();
        });
        if(!folded){
          var seen={};ids.forEach(function(id){var base=id.split('#')[0];if(seen[base])return;seen[base]=1;var line=el('div','hb-layer-block'),title=(blocks[id]&&blocks[id]._name)||base,pick=el('select');
            var g=el('button','hb-btn hb-layer-grip');g.type='button';g.title='Drag onto another layer to move '+title+' there';g.setAttribute('aria-label','Drag '+title+' to another layer');g.appendChild(svg('M5 8h14M5 12h14M5 16h14'));
            line.dataset.from=key;line.append(g,el('span','',title));
            pick.setAttribute('aria-label','Layer for '+title);pick.dataset.layerBlock=base;layerState.order.slice().reverse().forEach(function(k){var o=el('option','',layerName(k));o.value=k;pick.appendChild(o);});pick.value=key;pick.onchange=function(){changeLayer(base,pick.value);};line.appendChild(pick);
            dragThing(g,line,'app',function(t){changeLayer(base,t.dataset.layer);});section.appendChild(line);});
        }
        layerMenu.appendChild(section);
      });
      layerMenu.scrollTop=keep;
    }
    layerButton.onclick=function(){layerMenu.hidden=!layerMenu.hidden;layerButton.setAttribute('aria-expanded',String(!layerMenu.hidden));if(!layerMenu.hidden)drawLayers();};
    function outsideMore(e){Object.keys(trayLists).forEach(function(k){if(!trayLists[k].hidden&&!trayLists[k].contains(e.target)&&!trayButtons[k].contains(e.target))trayLists[k].hidden=true;});if(!menu.hidden&&!menu.contains(e.target)&&!more.contains(e.target))closeMore();if(!layerMenu.hidden&&!layerMenu.contains(e.target)&&e.target!==layerButton)layerMenu.hidden=true;var jump=host.querySelector('.hb-jump');if(jump&&!jump.hidden&&!jump.contains(e.target)&&!menu.contains(e.target)&&!e.target.closest('.hb-viewbar')&&nav)nav.toggle();}
    function moreKey(e){if(e.key==='Escape'){var glass=document.querySelector('.hb-glass-panel');if(glass)glass.remove();var voice=document.getElementById('voice');if(voice&&!voice.hidden)document.getElementById('v-close').click();Object.keys(trayLists).forEach(function(k){trayLists[k].hidden=true;});closeMore();layerMenu.hidden=true;var d=host.querySelector('.hb-session-detail');if(d)d.remove();}}
    document.addEventListener('pointerdown',outsideMore,true);document.addEventListener('keydown',moreKey,true);
    function notices(){document.querySelectorAll('#hub-graphics-chip').forEach(function(n,i){if(i||graphicsDismissed)n.remove();else{graphicsNotice=n;var x=n.querySelector('button');if(x&&!x._hubDismiss){x._hubDismiss=true;x.addEventListener('click',function(){graphicsDismissed=true;graphicsNotice=null;});}}});if(graphicsNotice&&!graphicsDismissed)placeControl('graphics',graphicsNotice);}
    var noticeWatch=new MutationObserver(function(){notices();});noticeWatch.observe(document.body,{childList:true});notices();
    // Primary controls retain the original actions; no sensor is started by mounting these icons.
    talkBtn.textContent='';talkBtn.classList.add('talk-btn');talkBtn.setAttribute('aria-label','Talk to the Hub');var smith=el('img');smith.src='/smith-icon.png';smith.alt='';talkBtn.appendChild(smith);
    pcBtn.textContent='';var wire=document.querySelector('#mcp-wire svg');if(wire)pcBtn.appendChild(wire.cloneNode(true));pcBtn.setAttribute('aria-label','PC control');
    if(hands){hands.button.setAttribute('aria-label','Hand control');hands.button.title='Hand control';hands.button.querySelectorAll('span').forEach(function(n){n.remove();});Array.from(hands.button.childNodes).forEach(function(n){if(n.nodeType===3)n.textContent='';});}
    var learning=el('button','hb-btn hb-learning','R');learning.type='button';learning.hidden=true;       // experimental: hidden until it is switched on in Settings
    learning.title='Reinforcement learning (experimental)';learning.setAttribute('aria-label','Reinforcement learning, experimental');learning.onclick=function(){
      // Light on: this click only switches shadow mode off (so it cannot stay on by accident). Light off: it opens the panel, where the switch to turn it on lives.
      if(learning.classList.contains('lit')){fetch('/api/yard/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({shadow:false,learning:false})}).then(function(){shadowLight(false);}).catch(function(){});return;}
      glassPage('/yard','REINFORCEMENT LEARNING · EXPERIMENTAL');};bar.appendChild(learning);
    // The small light on R is on only while shadow mode is on (off by default). The panel's own switch tells the board at once; a slow check keeps it honest if it changes elsewhere.
    function shadowLight(on){learning.classList.toggle('lit',!!on);learning.title=on?'Shadow mode is ON (experimental). Click to switch it off.':'Reinforcement learning (experimental). Click to open.';}
    function shadowPoll(){if(!alive)return;fetch('/api/yard/settings',{cache:'no-store'}).then(function(r){return r.json();}).then(function(j){learning.hidden=!(j&&j.experimental&&j.experimental.on);shadowLight(j&&j.shadow&&j.shadow.on);}).catch(function(){learning.hidden=true;});}
    window.addEventListener('message',function(e){if(e.origin===location.origin&&e.data&&typeof e.data.hubShadow==='boolean')shadowLight(e.data.hubShadow);});
    shadowPoll();var shadowTimer=setInterval(function(){if(!alive){clearInterval(shadowTimer);return;}shadowPoll();},20000);
    setupBtn.hidden=true;setupBtn.classList.add('hb-setup-secondary');
    var gizmo=host.querySelector('.hb-gizmo');if(gizmo)rightScroll.appendChild(gizmo);
    // LOG is a per-device presentation choice; recording its lines remains active.
    var logToggle=el('button','hb-btn hb-log-toggle','LOG');logToggle.type='button';logToggle.title='Show or hide the chat, hands and Hub log';
    function showLog(on){document.documentElement.classList.toggle('hub-log-visible',on);if(on)window.dispatchEvent(new CustomEvent('hub-log-open'));else{var lg=document.querySelector('.hands-log');if(lg)lg.classList.remove('open');}logToggle.setAttribute('aria-pressed',String(on));try{localStorage.setItem('agenthub:log:visible',on?'1':'0');}catch(e){}requestAnimationFrame(function(){if(alive){stageRect();if(!touched)fit(false);}});}
    logToggle.onclick=function(){showLog(!document.documentElement.classList.contains('hub-log-visible'));};
    showLog(false);
    // The controls fade when nothing is touched for a few seconds, and come back at the first touch, move or key.
    var idleTimer=0;function wakeControls(){if(!alive)return;host.classList.remove('hb-idle');clearTimeout(idleTimer);idleTimer=setTimeout(function(){if(alive&&!document.querySelector('.hb-layer-menu:not([hidden]),.hb-tray-list:not([hidden]),.hb-more-menu:not([hidden]),.hb-session-detail,.hb-glass-panel'))host.classList.add('hb-idle');},4500);}
    ['pointermove','pointerdown','keydown','wheel','touchstart'].forEach(function(t){host.addEventListener(t,wakeControls,{passive:true});});wakeControls();
    // Primary clicks retain their original actions. Context clicks expose tools, never capture.
    var handsToggle=hands&&hands.button.onclick,handAction=el('button','hb-btn','START HANDS');handAction.type='button';handAction.dataset.logKind='hands';
    handAction.onclick=function(e){if(handsToggle)return handsToggle.call(hands.button,e);};
    function utilityPanel(title){var old=document.querySelector('.hb-context-panel');if(old)old.remove();var pane=fadePanel(el('section','hb-glass-panel hb-context-panel')),head=el('div','hb-glass-head'),close=el('button','hb-btn');close.appendChild(svg(ICON.x));pane.setAttribute('role','dialog');pane.setAttribute('aria-label',title);close.type='button';close.setAttribute('aria-label','Close '+title);close.onclick=function(){pane.remove();};head.append(el('h2','',title),close);pane.appendChild(head);document.body.appendChild(pane);pane._fadeOpen();close.focus({preventScroll:true});return pane;}
    function openHandControls(){if(controls.handSetup&&controls.handSetup.onclick)controls.handSetup.onclick();}
    function paintLogContext(){var box=document.querySelector('.hands-log');if(!box)return;var selected=box.querySelector('.hl-filters .on'),kind=selected?selected.dataset.kind:'all';box.dataset.context=kind;box.querySelectorAll('.hl-tools button').forEach(function(b){if(!b.dataset.logKind)b.dataset.logKind=b.textContent==='OPEN CHAT'?'chat':'hands';});handAction.textContent=hands&&hands.button.classList.contains('live')?'STOP HANDS':'START HANDS';var live=document.querySelector('.hb-hand-state');if(live&&hands){var stats=hands.tracker.stats;live.textContent=stats.loading?'Starting hand tracking…':stats.enabled?'CAMERA ON · Local hand tracking':stats.error?'Camera off · '+stats.error:'Camera off · Tracking stopped';}}
    function openHandsLog(e){if(e)e.preventDefault();openHandControls(false);}
    function logContextClick(e){if(e.target.closest('.hl-filters button'))paintLogContext();}
    document.addEventListener('click',logContextClick);
    if(hands){hands.button.onclick=handsToggle;hands.button.addEventListener('contextmenu',openHandsLog);hands.button.title='Left-click: start/stop hand tracking. Right-click: controls and gesture guide.';}
    var contextWatch=new MutationObserver(paintLogContext);if(hands)contextWatch.observe(hands.button,{attributes:true,attributeFilter:['class','title','aria-busy']});paintLogContext();
    // A separate 500-message, per-tab archive lives inside Talk; it never changes model context.
    var chatKey='agenthub:chat:history:v1',chatArchive={rows:[],after:0},chatWatch=null,originalLog=window.__hubLogAdd,archiveLog=null;
    try{var ca=JSON.parse(sessionStorage.getItem(chatKey)||'null');if(ca&&Array.isArray(ca.rows))chatArchive=ca;}catch(e){}
    function saveChatArchive(){try{sessionStorage.setItem(chatKey,JSON.stringify(chatArchive));}catch(e){}}
    function archiveChat(row){if(!row||row.kind!=='chat'||!row.t||row.at<=chatArchive.after)return;var last=chatArchive.rows[chatArchive.rows.length-1];if(last&&last.at===row.at&&last.t===row.t)return;chatArchive.rows.push({at:row.at,t:String(row.t)});chatArchive.rows=chatArchive.rows.slice(-500);saveChatArchive();if(document.getElementById('hb-chat-history')&&!document.getElementById('hb-chat-history').hidden)drawChatHistory();}
    if(!chatArchive.rows.length)try{JSON.parse(sessionStorage.getItem('agenthub:log')||'[]').filter(function(r){return r.kind==='chat';}).reverse().forEach(archiveChat);}catch(e){}
    if(originalLog){archiveLog=function(kind,text,err){if(kind==='chat')archiveChat({kind:kind,t:text,at:Date.now()});return originalLog(kind,text,err);};window.__hubLogAdd=archiveLog;}
    function archiveEvent(e){var d=e.detail||{};if(d.kind==='chat')archiveChat({kind:'chat',t:d.text,at:Date.now()});}window.addEventListener('hub-log',archiveEvent);
    function drawChatHistory(){var list=document.getElementById('hb-chat-history-rows');if(!list)return;list.replaceChildren();if(!chatArchive.rows.length)list.appendChild(el('p','','No saved chat messages in this tab yet.'));chatArchive.rows.forEach(function(row){var line=el('article','hb-chat-history-row'),time=el('time','',new Date(row.at).toLocaleString());line.append(time,el('p','',row.t));list.appendChild(line);});}
    function installChatHistory(){var voice=document.getElementById('voice'),log=document.getElementById('v-log');if(!voice||!log||document.getElementById('hb-chat-history'))return;
      var tabs=el('div','hb-chat-tabs'),current=el('button','vbtn','CONVERSATION'),history=el('button','vbtn','HISTORY'),panel=el('section','hb-chat-history'),note=el('p','hb-context-note','Up to 500 messages saved in this browser tab. Read-only history; it is not added to the current conversation.'),rows=el('div'),clear=el('button','vbtn','CLEAR HISTORY');tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','Chat views');current.id='hb-chat-current-tab';history.id='hb-chat-history-tab';panel.id='hb-chat-history';rows.id='hb-chat-history-rows';panel.hidden=true;clear.type='button';clear.onclick=function(){if(clear.dataset.confirm!=='1'){clear.dataset.confirm='1';clear.textContent='CONFIRM CLEAR HISTORY';return;}chatArchive={rows:[],after:Date.now()};saveChatArchive();drawChatHistory();clear.dataset.confirm='';clear.textContent='CLEAR HISTORY';};
      function selectHistory(on){log.classList.toggle('hb-chat-current-hidden',on);panel.hidden=!on;current.setAttribute('aria-selected',String(!on));history.setAttribute('aria-selected',String(on));if(on)drawChatHistory();}
      [current,history].forEach(function(b){b.type='button';b.setAttribute('role','tab');});current.setAttribute('aria-controls','v-log');history.setAttribute('aria-controls',panel.id);current.onclick=function(){selectHistory(false);};history.onclick=function(){selectHistory(true);};tabs.append(current,history);panel.setAttribute('role','tabpanel');panel.setAttribute('aria-labelledby',history.id);log.setAttribute('role','tabpanel');log.setAttribute('aria-labelledby',current.id);panel.append(note,clear,rows);log.before(tabs);log.after(panel);selectHistory(false);
      var fresh=document.getElementById('v-new');if(fresh){fresh.addEventListener('click',current.onclick);dragCleanups.push(function(){fresh.removeEventListener('click',current.onclick);});}
    }
    installChatHistory();
    var fullChatLog=document.getElementById('v-log');if(fullChatLog){chatWatch=new MutationObserver(function(changes){changes.forEach(function(c){c.addedNodes.forEach(function(n){if(n.nodeType!==1||!n.matches('.v-msg.you,.v-msg.hub'))return;var text=(n.classList.contains('you')?'You: ':'Smith: ')+Array.from(n.childNodes).filter(function(x){return x.nodeType===3;}).map(function(x){return x.textContent;}).join(''),short=text.replace(/\s+/g,' ').trim().slice(0,400),row=chatArchive.rows[chatArchive.rows.length-1];if(row&&row.t===short){row.t=text;saveChatArchive();}});});});chatWatch.observe(fullChatLog,{childList:true});}

    if(view)viewBar.append(view.btn,view.gizmoBtn);viewBar.append(zoomRow,fitBtn,tidyBtn,blocksBtn,layerButton);host.appendChild(logToggle);
    if(hands)ingestDock.appendChild(hands.button);ingestDock.appendChild(ingestBtn);
    var hidePanel=el('span','hb-panel-hide','HIDE'),showPanel=el('span','hb-panel-show','SHOW');[hidePanel,showPanel].forEach(function(e){e.setAttribute('role','button');e.tabIndex=0;e.onkeydown=function(k){if(k.key==='Enter'||k.key===' '){k.preventDefault();e.click();}};});hidePanel.setAttribute('aria-label','Hide view controls');showPanel.setAttribute('aria-label','Show view controls');host.appendChild(hidePanel);host.appendChild(showPanel);showPanel.hidden=true;
    function toggleRight(hide){rightPanel.hidden=hide;showPanel.hidden=!hide;hidePanel.hidden=hide;try{localStorage.setItem('agenthub:board:right-hidden',hide?'1':'0');}catch(e){}setTimeout(function(){if(alive){stageRect();if(!touched)fit(false);}},190);}
    hidePanel.onclick=function(){toggleRight(true);};showPanel.onclick=function(){toggleRight(false);};try{toggleRight(localStorage.getItem('agenthub:board:right-hidden')==='1');}catch(e){}
    function decoratePanels(root){var selector='#voice,.hands-setup,.hb-more-menu,.hb-layer-menu,.hb-jump,.hb-ctx,.hb-session-detail';if(root.matches&&root.matches(selector)){var fresh=!root._hubFade;fadePanel(root);if(fresh&&!root.hidden&&root.isConnected)root._fadeOpen();}if(root.querySelectorAll)root.querySelectorAll(selector).forEach(function(n){var fresh=!n._hubFade;fadePanel(n);if(fresh&&!n.hidden&&n.isConnected)n._fadeOpen();});}
    decoratePanels(document);panelObserver=new MutationObserver(function(changes){changes.forEach(function(c){c.addedNodes.forEach(function(n){if(n.nodeType===1)decoratePanels(n);});});syncModal();});panelObserver.observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['hidden']});
    var stageWatch=new ResizeObserver(function(){if(alive){stageRect();panelNodes.forEach(function(n){if(n.isConnected&&!n.hidden)positionPopup(n);});}});[bar,rightPanel,tray,batchControls].forEach(function(e){stageWatch.observe(e);});
    stackDepth();
    var instance = {
      update: function (d) { data = d; paint(); HubBlocks.graphics(); if (!arrived) { arrived = true; HubBlocks.arrive(blocks, function () { return V.k; }, releaseArrival); } },
      destroy: function () { if (!alive) return; alive = false;document.querySelectorAll('.hb-context-panel').forEach(function(n){n.remove();}); window.removeEventListener('hub-log-ready', onLogReady);document.removeEventListener('click',logContextClick);contextWatch.disconnect();if(chatWatch)chatWatch.disconnect();window.removeEventListener('hub-log',archiveEvent);if(window.__hubLogAdd===archiveLog)window.__hubLogAdd=originalLog;if(hands)hands.button.removeEventListener('contextmenu',openHandsLog); closeCtx(); document.removeEventListener('keydown', ctxKey, true); removeEventListener('blur', closeCtx); if(hands)hands.destroy();document.removeEventListener('pointerdown',holdPaint,true);window.removeEventListener('pointerup',releasePaint,true);window.removeEventListener('pointercancel',releasePaint,true);window.removeEventListener('blur',releasePaint);clearTimeout(paintReleaseTimer);noticeWatch.disconnect();stageWatch.disconnect();if(panelObserver)panelObserver.disconnect();panelNodes.forEach(function(n){if(n._hubResetFade)n._hubResetFade();});panelNodes.clear();document.documentElement.classList.remove('hub-modal-open');document.removeEventListener('pointerdown',outsideMore,true);document.removeEventListener('keydown',moreKey,true);if(bin)bin.classList.remove('drop-target'); if (view) view.destroy(); if (setupHome && setupHome.parent) setupHome.parent.insertBefore(setupCard, setupHome.next); if (wireWatch) wireWatch.disconnect(); if (bannerWatch) bannerWatch.disconnect(); if (window.__hubBoard.active === instance) window.__hubBoard.active = null; releaseArrival(); clearTimeout(hintTimer);clearTimeout(recoveryTimer);clearTimeout(rasterTimer); dragCleanups.forEach(function (fn) { fn(); }); stopCam(); stopEdge(); guides.destroy(); if (nav) nav.destroy(); document.removeEventListener('keydown', onKey); removeEventListener('resize', onResize);if(window.visualViewport)visualViewport.removeEventListener('resize',onResize); if(resizeFrame)cancelAnimationFrame(resizeFrame); tray.remove(); root.replaceChildren(); root.style.width = root.style.maxWidth = root.style.marginLeft = ''; root.__hubBoardInstance = null; },
      state: function () { return { V: V, L: L, hid: hid }; },
      stage:stageRect,layers:function(){return layerState;},
      view: function () { return view; },
      // what Talk can see of the board, and what it may do to it (the answer's `ui`: a panel to bring up, tidy, fit, zoom, the mouse scheme)
      scene: function () { return Object.keys(blocks).filter(function (i) { return !hid[i]; }).map(function (i) { return { id: i, t: String(blocks[i]._name || (blocks[i].querySelector('.hk-h .t') || {}).textContent || i) }; }); },
      applyUi: function (ui) {
        if (!alive || !ui) return false;
        if (ui.window && ui.window.url) return openWindow(ui.window.title || 'Window', ui.window.url);
        if (ui.board) {
          var b = ui.board; touched = true;
          if (b === 'tidy') tidyBtn.onclick(); else if (b === 'fit') fitBtn.onclick(); else if (b === 'zoom-in') zin.onclick(); else if (b === 'zoom-out') zout.onclick();
          else if (b.indexOf('view:') === 0 && view) view.setMode(b.slice(5)); else return false;
          return true;
        }
        var MAP = { attention: 'att', runs: 'runs', sessions: 'ses', health: 'hlt', usage: 'use', disk: 'hlt' };
        var ids = (ui.focus ? [ui.focus] : (ui.blocks || []).map(function (x) { return x.id; })).map(function (i) { return blocks[i] ? i : MAP[i]; }).filter(function (i, n, a) { return i && blocks[i] && a.indexOf(i) === n; });
        if (!ids.length) return false;
        touched = true; stopCam();
        ids.forEach(function (i) { revealLayer(i);if (hid[i]) { hid[i] = 0; applyBlock(i); resolve(i); } });
        trayDraw(); save();
        if (ids.length === 1) { if (focusId !== ids[0]) focusBlock(ids[0]); } else { focusId = null; undim(); lookAt(ids[0]); }
        return true;
      },
      // Talk asked for a window of this PC, or a session, as a panel ("open Claude Desktop in the dashboard"): a block of its own, opened at once.
      openWindow: function (title, url) { return openWindow(title, url); },
      // Talk asked for a Hub page ("open missions"): it opens inside the board, on the right tab, never as a separate page.
      openTool: function (url) {
        var u = new URL(url, location.href), id = u.pathname === '/support' ? 'extra:support' : (['/missions', '/agents', '/graph', '/yard', '/chats'].indexOf(u.pathname) >= 0 ? 'card:oc' : null);
        if (!alive || !id || !blocks[id] || !L[id]) return false;
        touched = true; stopCam();
        if (hid[id]) { hid[id] = 0; applyBlock(id); resolve(id); trayDraw(); save(); }
        revealLayer(id);var b = blocks[id]; if (!L[id].exp) expand(id);
        var fr = b.querySelector('iframe'), want = u.pathname.slice(1).toUpperCase();
        Array.prototype.forEach.call(b.querySelectorAll('.hk-tabs button'), function (t) { t.classList.toggle('on', t.textContent === want); });
        if (fr) { var next = embedUrl(u.pathname + u.search); if (fr.src !== next) { fr.src = next; if (motion) motion.frame(fr); } b._url = u.pathname + u.search; }
        L[id].z = ++zTop; applyBlock(id); if (stackDepth) stackDepth(); lookAt(id); return true;
      }
    };
    root.__hubBoardInstance = instance; window.__hubBoard.active = instance;
    if(new URLSearchParams(location.search).get('chat')==='1')requestAnimationFrame(function(){if(window.HubVoice)HubVoice.open(false);}); return instance;
  }
  window.__hubBoard = { mount: mount, active: null, openWindow: function (t, u) { return !!(this.active && this.active.openWindow(t, u)); }, open: function (url) { return !!(this.active && this.active.openTool(url)); }, scene: function () { return this.active ? this.active.scene() : null; }, applyUi: function (ui) { return !!(this.active && this.active.applyUi(ui)); } };
})();
