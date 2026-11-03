// Keyboard navigation and a lightweight SVG overview; no polling or permanent animation.
(function () {
  function mount(host, blocks, layout, hidden, read, visit, open, close) {
    var map = document.createElement('button'); map.className = 'hb-map'; map.type = 'button'; map.setAttribute('aria-label', 'Board overview. Click to centre the camera');
    var ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns, 'svg'); svg.setAttribute('viewBox', '0 0 150 90'); svg.setAttribute('aria-hidden', 'true'); map.appendChild(svg); host.appendChild(map);
    var frame = document.createElementNS(ns, 'rect'); frame.classList.add('viewport'); svg.appendChild(frame); var rects = {}, bounds = null, raf = 0;
    function attr(e, k, v) { var s = String(v); if (e.getAttribute(k) !== s) e.setAttribute(k, s); }
    function paint() {
      raf = 0; var ids = Object.keys(blocks).filter(function (id) { return !hidden[id]; }); if (!ids.length) return;
      var x = Math.min.apply(null, ids.map(function (id) { return layout[id].x; })), y = Math.min.apply(null, ids.map(function (id) { return layout[id].y; }));
      var w = Math.max.apply(null, ids.map(function (id) { return layout[id].x + layout[id].w; })) - x, h = Math.max.apply(null, ids.map(function (id) { return layout[id].y + layout[id].h; })) - y;
      var s = Math.min(138 / Math.max(1, w), 78 / Math.max(1, h)); bounds = { x:x, y:y, scale:s };
      Object.keys(rects).forEach(function (id) { rects[id].setAttribute('visibility', hidden[id] ? 'hidden' : 'visible'); });
      ids.forEach(function (id) { var l = layout[id], e = rects[id]; if (!e) { e = rects[id] = document.createElementNS(ns, 'rect'); svg.insertBefore(e, frame); } attr(e,'x',6+(l.x-x)*s); attr(e,'y',6+(l.y-y)*s); attr(e,'width',l.w*s); attr(e,'height',(l.min?32:l.h)*s); });
      var v=read();attr(frame,'x',6+(-v.x/v.k-x)*s);attr(frame,'y',6+(-v.y/v.k-y)*s);attr(frame,'width',host.clientWidth/v.k*s);attr(frame,'height',host.clientHeight/v.k*s);
    }
    function refresh() { if (!raf) raf=requestAnimationFrame(paint); }
    map.onclick=function(e){e.stopPropagation();if(!bounds)return;var r=map.getBoundingClientRect(),x=e.detail?(e.clientX-r.left)/r.width*150:75,y=e.detail?(e.clientY-r.top)/r.height*90:45;visit(null,{x:bounds.x+(x-6)/bounds.scale,y:bounds.y+(y-6)/bounds.scale});};
    var dialog=document.createElement('div');dialog.className='hb-jump';dialog.hidden=true;dialog.setAttribute('role','dialog');dialog.setAttribute('aria-modal','true');dialog.setAttribute('aria-label','Jump to block');
    var input=document.createElement('input');input.placeholder='Jump to a block';input.setAttribute('aria-label','Find a block');var list=document.createElement('div');var head=document.createElement('div');head.className='hb-jump-h';var title=document.createElement('span');title.textContent='BLOCKS';var closeBtn=document.createElement('button');closeBtn.type='button';closeBtn.className='hb-jump-x';closeBtn.setAttribute('aria-label','Close the block list');closeBtn.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>';head.append(title,closeBtn);dialog.append(head,input,list);host.appendChild(dialog);var origin=null, closing=null;
    function dismiss(){if(window.HubBlocks&&HubBlocks.allowed()){closing=dialog.animate([{opacity:1},{opacity:0}],{duration:140});closing.onfinish=function(){dialog.hidden=true;closing=null;};}else dialog.hidden=true;if(origin&&origin.isConnected)origin.focus({preventScroll:true});}
    function choose(id){dismiss();visit(id);blocks[id].focus({preventScroll:true});if(blocks[id]._open)open(id);}
    function search(){list.replaceChildren();Object.keys(blocks).filter(function(id){return blocks[id]._name.toLowerCase().includes(input.value.toLowerCase());}).forEach(function(id){var b=document.createElement('button');b.type='button';b.textContent=blocks[id]._name;b.onclick=function(){choose(id);};list.appendChild(b);});}
    input.oninput=search;input.onkeydown=function(e){if(e.key==='Enter'&&list.firstChild){e.preventDefault();list.firstChild.click();}if(e.key==='ArrowDown'&&list.firstChild){e.preventDefault();list.firstChild.focus();}};
    dialog.addEventListener('keydown',function(e){if(e.key!=='Tab')return;var all=[input].concat(Array.from(list.children)),at=all.indexOf(document.activeElement);if(e.shiftKey&&at===0){e.preventDefault();all[all.length-1].focus();}else if(!e.shiftKey&&at===all.length-1){e.preventDefault();input.focus();}});
    closeBtn.onclick=function(){dismiss();};
    // the list sits below the bar so the BLOCKS button stays reachable, and a click anywhere else on the board closes it
    function outside(e){if(dialog.hidden||e.target.closest('.hb-jump,.hb-btn'))return;dismiss();}
    host.addEventListener('pointerdown',outside,true);
    function place(){var bar=host.querySelector('.hb-bar');if(bar)dialog.style.setProperty('--jump-top',Math.round(bar.getBoundingClientRect().bottom-host.getBoundingClientRect().top+8)+'px');}
    function key(e){
      if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();if(!dialog.hidden){dismiss();return true;}if(closing){closing.cancel();closing=null;}origin=document.activeElement;input.value='';search();place();dialog.hidden=false;input.focus();return true;}
      if(e.key==='Escape'&&!dialog.hidden){e.preventDefault();dismiss();return true;}
      if(e.target.closest('input,textarea,select,[contenteditable=true],button'))return false;
      var block=e.target.closest('.hk'),id=block&&block.dataset.id;
      if(e.key==='Escape'){var expanded=Object.keys(layout).filter(function(i){return layout[i].exp;}).sort(function(a,b){return (layout[b].z||0)-(layout[a].z||0);});if(expanded.length){e.preventDefault();close(expanded[0]);return true;}return false;}
      if(e.key==='Enter'&&id){e.preventDefault();if(block._open)open(id);else visit(id);return true;}
      var axes={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]},axis=axes[e.key];if(!axis||!id)return false;
      var a=layout[id],best=null,score=Infinity;
      Object.keys(blocks).forEach(function(i){if(i===id||hidden[i])return;var b=layout[i],dx=b.x+b.w/2-a.x-a.w/2,dy=b.y+b.h/2-a.y-a.h/2,along=dx*axis[0]+dy*axis[1],cross=Math.abs(dx*axis[1]-dy*axis[0]);if(along>0&&along+cross*2<score){score=along+cross*2;best=i;}});
      if(best){e.preventDefault();blocks[best].focus({preventScroll:true});visit(best);}return true;
    }
    refresh();return {refresh:refresh,key:key,toggle:function(){key({ctrlKey:true,key:'k',preventDefault:function(){},target:host});},destroy:function(){if(raf)cancelAnimationFrame(raf);host.removeEventListener('pointerdown',outside,true);map.remove();dialog.remove();}};
  }
  window.__hubBoardNav={mount:mount};
})();
