// Compact server-side folder picker (a browser cannot give absolute paths). FolderPicker.pick(startPath, cb) -> cb(chosenPath). Uses GET /api/fs/list, POST /api/fs/mkdir.
window.FolderPicker = (function () {
  let box, dirsEl, crumbsEl, okBtn, cur = { path: '', parent: '' }, done = null;
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const FOLDER = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="flex:none"><path d="M3 7.5A1.5 1.5 0 0 1 4.5 6H9l2 2.5h8.5A1.5 1.5 0 0 1 21 10v8a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 18z"/></svg>';
  function build() {
    const st = document.createElement('style');
    st.textContent = '#fp-scrim{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:80;display:none}#fp-box{position:fixed;top:8vh;left:50%;transform:translateX(-50%);width:600px;max-width:96vw;max-height:84vh;display:none;flex-direction:column;background:#0d1050;border:1px solid rgba(0,230,118,.55);border-radius:12px;padding:14px;z-index:81;color:#d9ffe9;font-family:Outfit,system-ui,sans-serif}' +
      '#fp-box h3{font:700 11px Orbitron,monospace;letter-spacing:1.5px;color:#00e676;margin:0 0 8px}#fp-crumbs{display:flex;flex-wrap:wrap;gap:4px;font-size:12px;margin-bottom:8px;color:rgba(0,230,118,.6)}#fp-crumbs a{cursor:pointer;color:#00e676}' +
      '#fp-dirs{overflow-y:auto;border:1px solid rgba(0,230,118,.22);border-radius:8px;background:#080c28;min-height:170px;max-height:44vh}#fp-dirs div{display:flex;align-items:center;gap:8px;padding:9px 11px;font-size:13px;cursor:pointer;border-bottom:1px solid rgba(0,230,118,.12)}#fp-dirs div:hover{background:rgba(0,230,118,.08)}' +
      '#fp-row{display:flex;gap:8px;margin-top:10px}#fp-row .btn{flex:0 0 auto}#fp-row .sp{flex:1}';
    document.head.appendChild(st);
    const scrim = document.createElement('div'); scrim.id = 'fp-scrim';
    box = document.createElement('div'); box.id = 'fp-box';
    box.innerHTML = '<h3>CHOOSE A FOLDER</h3><div id="fp-crumbs"></div><div id="fp-dirs"></div><div id="fp-row"><button type="button" class="btn" id="fp-up">UP</button><button type="button" class="btn" id="fp-new">NEW FOLDER</button><span class="sp"></span><button type="button" class="btn" id="fp-cancel">CANCEL</button><button type="button" class="btn go" id="fp-ok">USE THIS FOLDER</button></div>';
    document.body.appendChild(scrim); document.body.appendChild(box);
    dirsEl = box.querySelector('#fp-dirs'); crumbsEl = box.querySelector('#fp-crumbs'); okBtn = box.querySelector('#fp-ok');
    const close = () => { scrim.style.display = 'none'; box.style.display = 'none'; };
    scrim.onclick = close; box.querySelector('#fp-cancel').onclick = close;
    box.querySelector('#fp-up').onclick = () => load(cur.parent || '');
    okBtn.onclick = () => { const cb = done, p = cur.path; close(); if (cb && p) cb(p); };
    box.querySelector('#fp-new').onclick = async () => {
      if (!cur.path) return; const n = prompt('New folder name'); if (!n) return;
      try { const r = await fetch('/api/fs/mkdir', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: cur.path.replace(/[\\/]+$/, '') + '\\' + n }) }); if (!r.ok) throw new Error(await r.text()); load((await r.json()).path); } catch (e) { alert(e.message); }
    };
    box._close = close; box._scrim = scrim;
  }
  async function load(path) {
    let d; try { const r = await fetch('/api/fs/list?path=' + encodeURIComponent(path || '')); if (!r.ok) throw new Error(await r.text()); d = await r.json(); } catch (e) { alert(e.message); return; }
    cur = { path: d.path || '', parent: d.parent || '' };
    const parts = cur.path ? cur.path.split(/[\\/]+/).filter(Boolean) : []; let acc = '';
    crumbsEl.innerHTML = '<a data-p="">this computer</a>' + parts.map((p, i) => { acc = i === 0 ? p + '\\' : acc.replace(/\\$/, '') + '\\' + p; return ' / <a data-p="' + esc(acc) + '">' + esc(p) + '</a>'; }).join('');
    crumbsEl.querySelectorAll('a').forEach((a) => { a.onclick = () => load(a.dataset.p); });
    const items = !cur.path ? [...(d.drives || []), ...(d.places || [])].map((x) => ({ name: x, full: x })) : d.dirs.map((x) => ({ name: x.name, full: cur.path.replace(/[\\/]+$/, '') + '\\' + x.name }));
    dirsEl.innerHTML = items.map((x) => '<div data-full="' + esc(x.full) + '">' + FOLDER + esc(x.name) + '</div>').join('') || '<div style="opacity:.5">no sub-folders</div>';
    dirsEl.querySelectorAll('[data-full]').forEach((r) => { r.onclick = () => load(r.dataset.full); });
    okBtn.disabled = !cur.path;
  }
  return { pick(start, cb) { if (!box) build(); done = cb; box._scrim.style.display = 'block'; box.style.display = 'flex'; load(start && /^[A-Za-z]:/.test(start) ? start : ''); } };
})();
