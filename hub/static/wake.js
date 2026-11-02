// The landing page is the interface: say "Smith" and talk to the Hub. Off until you switch it on.
// After the wake word it is a conversation: follow-ups need no wake word until it has been quiet for a while. Answers come back as
// blocks that fade in around the ring (lists, numbers, a chart, notes, the doctor), the ring pulses while it listens and speaks, and
// everything that appears or leaves does so by fading. Commands about the screen ("clear the dashboard", "open Home", "go to sleep",
// "something is wrong with the Hub") are decided by the Hub (/api/voice/chat returns `ui`), so the router never hears them as
// requests to open a page. Audio stays on the PC: each sentence is transcribed by the Hub's local Whisper.
(function () {
  var btn = document.getElementById('wake-toggle'), stage = document.getElementById('wake-stage'), enterBtn = document.getElementById('wake-btn');
  if (!btn || !stage) return;
  // Whisper hears "Smith" as other names ("Kenya" was seen). The Hub also tells it the word to expect; this list is the net.
  var NAMES = ['smith', 'smyth', 'smythe', 'smit', 'smid', 'smif', 'smiff', 'schmidt', 'smeeth', 'smeth', 'kenya', 'kenia', 'semis', 'mith', 'smitt', 'sneth', 'zmith'];
  var KEY = 'agenthub:wake', EASE = 'cubic-bezier(.2,.8,.2,1)', SPRING = 'cubic-bezier(.34,1.45,.64,1)', CONVO_MS = 20000, FADE = 320;
  var reduce = matchMedia('(prefers-reduced-motion: reduce)');
  var S = { on: false, stream: null, ctx: null, an: null, state: 'off', speaking: false, run: 0, actx: null, pending: null, history: [], convoUntil: 0, clear: null, doctor: null, doctorTimer: null };
  var BUF = new Uint8Array(1024);

  function lev(a, b) {
    var m = a.length, n = b.length, d = [], i, j;
    for (i = 0; i <= m; i++) { d[i] = [i]; } for (j = 1; j <= n; j++) d[0][j] = j;
    for (i = 1; i <= m; i++) for (j = 1; j <= n; j++) d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    return d[m][n];
  }
  // the wake word is the first word (after an optional "hey"): an exact name, or within two letters of "smith"
  function wakeSplit(text) {
    var m = /^\W*(?:(?:hey|hi|okay|ok|yo)\W+)?([A-Za-z]{2,10})\b[\s,.!?:-]*/.exec(text);
    if (!m) return null;
    var w = m[1].toLowerCase();
    if (NAMES.indexOf(w) >= 0 || (w.length >= 4 && lev(w, 'smith') <= 1) || (w.length >= 5 && lev(w, 'smith') <= 2 && w.charAt(0) === 's')) return { rest: text.slice(m[0].length).trim() };
    return null;
  }

  var st = document.createElement('style');
  st.textContent = [
    '#wake-ring{position:absolute;inset:6%;border-radius:50%;pointer-events:none;opacity:0;border:2px solid rgba(0,230,118,.7);box-shadow:0 0 28px rgba(0,230,118,.35),inset 0 0 28px rgba(0,230,118,.15);transition:opacity .45s ease}',
    '#wake-ring.on{opacity:.9;animation:wkBreath 2.6s ease-in-out infinite}#wake-ring.hot{animation:wkBreath 1.2s ease-in-out infinite;border-color:#7bffd0}',
    '@keyframes wkBreath{50%{transform:scale(1.035);opacity:.45}}',
    '.wk-wave{position:absolute;inset:6%;border-radius:50%;pointer-events:none;border:2px solid rgba(0,230,118,.8)}',
    '#wake-stage{position:fixed;inset:0;pointer-events:none;z-index:6}',
    '.wb{position:absolute;width:236px;pointer-events:auto;text-align:left}',
    '.wb.amber{border-color:rgba(224,165,60,.6)}.wb.red{border-color:rgba(255,92,92,.6)}.wb.wide{width:300px}',
    '.wb h4{margin:0;padding:7px 10px 3px;font:700 8.5px Orbitron,monospace;letter-spacing:1.4px;color:#8fcfb2;display:flex;justify-content:space-between}',
    '.wb .li{display:flex;gap:8px;align-items:baseline;padding:4px 10px;border-top:1px solid rgba(255,255,255,.05);font-size:12.5px}.wb .li i{width:6px;height:6px;border-radius:50%;background:#00e676;flex:none}.wb .li i.a{background:#e0a53c}.wb .li i.r{background:#ff5c5c}.wb .li i.o{background:#6fae92}.wb .li span{color:#8fcfb2;font-size:11.5px;overflow-wrap:anywhere}',
    '.wb .num{padding:2px 10px 8px}.wb .num b{display:block;font:900 30px Orbitron,monospace;color:#00e676;line-height:1.1}.wb .num span{color:#8fcfb2;font-size:12px}',
    '.wb .nt{padding:2px 10px 9px;font-size:13px;line-height:1.45;overflow-wrap:anywhere}.wb .nt.sm{font-size:11.5px;color:#8fcfb2}',
    '.wb .row{display:flex;gap:8px;padding:2px 10px 10px;flex-wrap:wrap}.wb .go{font:700 9.5px Orbitron,monospace;letter-spacing:1.2px;color:#00e676;background:none;border:1px solid #00e676;border-radius:7px;padding:8px 14px;min-height:34px;cursor:pointer;text-decoration:none;display:inline-block}.wb .go.no{color:#ff8a8a;border-color:rgba(255,92,92,.6)}',
    '#wake-lines{position:fixed;left:50%;bottom:max(12px,env(safe-area-inset-bottom));transform:translateX(-50%);width:min(560px,92vw);display:flex;flex-direction:column;gap:5px;align-items:center;pointer-events:none;z-index:7}',
    '.wl{font-size:13.5px;padding:5px 12px;border-radius:99px;border:1px solid rgba(0,230,118,.3);background:rgba(6,10,36,.92);color:#d9ffe9;max-width:100%}.wl.you{border-color:rgba(59,167,255,.5);color:#cfe6ff}',
    '.wake-toggle .t{transition:opacity .2s}.wake-toggle .t.sw{opacity:0}'
  ].join('\n');
  document.head.appendChild(st);
  var lines = document.createElement('div'); lines.id = 'wake-lines'; document.body.appendChild(lines);
  var globe = document.querySelector('.globe-wrap'), ring = null;
  if (globe) { ring = document.createElement('div'); ring.id = 'wake-ring'; globe.appendChild(ring); }

  // ---- everything that appears or leaves does it by fading
  function fadeIn(e, ms, from) {
    if (reduce.matches) return;
    e.animate([{ opacity: 0, transform: from || 'translateY(10px)' }, { opacity: 1, transform: 'none' }], { duration: ms || FADE, easing: EASE, fill: 'backwards' });
  }
  function fadeOut(e, delay, cb) {
    e._fading = true;
    function done() { e.remove(); if (cb) cb(); }
    if (reduce.matches || !e.isConnected) return done();
    var a = e.animate([{ opacity: 1 }, { opacity: 0 }], { duration: FADE, delay: delay || 0, easing: 'ease-in', fill: 'forwards' });
    a.onfinish = done;
  }
  function mark() { return window.dormantGlobe; }
  function pulse() {
    try { var m = mark(); if (m && m.pulse) m.pulse(); } catch (e) {}
    if (!ring || reduce.matches) return;
    var w = document.createElement('div'); w.className = 'wk-wave'; globe.appendChild(w);
    var a = w.animate([{ transform: 'scale(1)', opacity: .9 }, { transform: 'scale(1.28)', opacity: 0 }], { duration: 900, easing: 'ease-out' }); a.onfinish = function () { w.remove(); };
  }
  var labelT = null;
  function setLabel(text) {
    var t = btn.querySelector('.t'); if (t.textContent === text) return; clearTimeout(labelT);
    if (reduce.matches) { t.textContent = text; return; }
    t.classList.add('sw'); labelT = setTimeout(function () { t.textContent = text; t.classList.remove('sw'); }, 180);
  }
  function setState(s) {
    S.state = s;
    setLabel({ off: 'WAKE WORD · OFF', wake: 'LISTENING FOR SMITH', convo: 'LISTENING', think: 'THINKING', speak: 'SPEAKING' }[s]);
    btn.classList.toggle('on', s !== 'off'); btn.setAttribute('aria-pressed', String(s !== 'off'));
    if (ring) { ring.classList.toggle('on', s !== 'off'); ring.classList.toggle('hot', s === 'convo' || s === 'speak' || s === 'think'); }
  }
  var lineT = null;
  function say(text, who) {
    var l = document.createElement('div'); l.className = 'wl ' + who; l.textContent = (who === 'you' ? 'You: ' : 'Smith: ') + text; lines.appendChild(l); fadeIn(l, 300);
    var live = Array.prototype.slice.call(lines.children).filter(function (c) { return !c._fading; });
    while (live.length > 3) fadeOut(live.shift());
    clearTimeout(lineT); lineT = setTimeout(function () { Array.prototype.slice.call(lines.children).forEach(function (c, i) { fadeOut(c, i * 60); }); }, 25000);
  }
  function secure() { return !!(window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder); }
  function rms() { if (!S.an) return 0; S.an.getByteTimeDomainData(BUF); var s = 0; for (var i = 0; i < BUF.length; i++) { var v = (BUF[i] - 128) / 128; s += v * v; } return Math.sqrt(s / BUF.length); }
  function post(u, body, kind, ms) {
    var c = new AbortController(), t = setTimeout(function () { c.abort(); }, ms || 30000);
    return fetch(u, { method: 'POST', signal: c.signal, headers: { 'Content-Type': kind === 'audio' ? (body.type || 'audio/webm') : 'application/json' }, body: kind === 'audio' ? body : JSON.stringify(body || {}) })
      .then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return kind === 'speech' ? r.arrayBuffer() : r.json(); }).finally(function () { clearTimeout(t); });
  }

  // ---- blocks around the ring
  var blocks = [];
  if (window.HubBlocks) { HubBlocks.edge(stage); enterBtn.addEventListener('click', function () { if (enterBtn.dataset.s === 'enter') HubBlocks.remember(blocks); }, true); }
  function center() { var r = (globe || document.body).getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2, R: r.width / 2 }; }
  // Blocks stand in two columns either side of the ring and stack by their real heights (and their real widths), so a long
  // list or the doctor's wide block never lands on the one below it. On a narrow screen they share one column.
  // A phone has no room beside the ring: blocks fill the free band above the controls, then the band below; one that fits neither is left out.
  function placeNarrow(list) {
    var top = innerHeight, bot = 0;
    ['wake-toggle', 'wake-btn'].forEach(function (id) { var n = document.getElementById(id), r = n && n.getBoundingClientRect(); if (r && r.width) { top = Math.min(top, r.top); bot = Math.max(bot, r.bottom); } });
    var bands = [{ y: 56, end: top - 12 }, { y: bot + 12, end: innerHeight - 12 }];
    list.forEach(function (e) {
      var h = e.offsetHeight, hit = null;
      bands.forEach(function (b) { if (!hit && b.y + h <= b.end) hit = b; });
      e.style.display = hit ? '' : 'none';
      if (hit) { e.style.left = '8px'; e.style.top = hit.y + 'px'; hit.y += h + 10; }
    });
  }
  function place(list) {
    var c = center(), vw = innerWidth, narrow = vw < 760, cols = [[], []];
    if (narrow) return placeNarrow(list);
    list.forEach(function (e, i) { cols[narrow ? 0 : i % 2].push(e); });
    cols.forEach(function (col, ci) {
      var y = Math.max(60, c.y - c.R * .9) + (ci ? 20 : 0);
      col.forEach(function (e) {
        var w = e.offsetWidth, h = e.offsetHeight;
        var x = narrow ? 8 : ci === 0 ? Math.max(12, c.x - c.R * 1.02 - w - 8) : Math.min(vw - w - 12, c.x + c.R * 1.02 + 8);
        e.style.left = x + 'px'; e.style.top = y + 'px'; y += h + 14;
      });
    });
  }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function mkBlock(b) {
    var e = el('div', 'wb hub-block ' + (b.cls || '')); e.dataset.id = b.id || ''; var h = el('h4'); h.appendChild(el('span', '', b.t)); if (b.n) h.appendChild(el('span', '', b.n)); e.appendChild(h);
    if (b.type === 'list') b.rows.forEach(function (r) { var d = el('div', 'li'); d.append(el('i', r[0] || ''), el('b', '', r[1])); if (r[2]) d.appendChild(el('span', '', r[2])); e.appendChild(d); });
    if (b.type === 'num') { var d = el('div', 'num'); d.append(el('b', '', b.big), el('span', '', b.cap)); e.appendChild(d); }
    if (b.type === 'bars') {
      var bx = el('div'); bx.style.cssText = 'display:flex;align-items:flex-end;gap:2px;height:70px;padding:6px 10px 2px'; var mx = Math.max.apply(null, b.values.concat([1]));
      b.values.forEach(function (v) { var i = el('i'); i.style.cssText = 'flex:1;background:linear-gradient(#3ba7ff,rgba(59,167,255,.25));border:1px solid rgba(59,167,255,.6);border-bottom:0;height:' + Math.max(2, Math.round(v / mx * 100)) + '%'; bx.appendChild(i); }); e.appendChild(bx); e.appendChild(el('div', 'nt sm', b.cap));
    }
    if (b.type === 'note') e.appendChild(el('div', 'nt', b.text));
    if (b.type === 'doctor') { e.classList.add('wide'); e._body = el('div', 'nt', 'Starting…'); e._acts = el('div', 'row'); e.append(e._body, e._acts); }
    if (b.home) { var row = el('div', 'row'), g = el('button', 'go', 'OPEN HOME'); g.type = 'button'; g.onclick = openHome; row.appendChild(g); e.appendChild(row); }
    if (b.link) { var r2 = el('div', 'row'), a = el('a', 'go', b.link[0]); a.href = b.link[1]; r2.appendChild(a); e.appendChild(r2); }
    return e;
  }
  function clearBlocks(done) {
    var old = blocks; blocks = []; clearTimeout(S.clear); stopDoctor();
    if (!old.length) { if (done) done(); return; }
    old.forEach(function (e, i) { fadeOut(e, i * 50, i === old.length - 1 ? done : null); });
  }
  function raise(list) {
    clearBlocks(function () {
      list.slice(0, 4).forEach(function (b, i) {
        var e = mkBlock(b); stage.appendChild(e); blocks.push(e);
        if (!reduce.matches) e.animate([{ opacity: 0, transform: 'translateY(14px) scale(.96)' }, { opacity: 1, transform: 'none' }], { duration: 520, delay: 60 + i * 100, easing: SPRING, fill: 'backwards' });
        if (b.type === 'doctor') { S.doctor = e; watchDoctor(); }
      });
      place(blocks);
      S.clear = setTimeout(function () { if (S.state === 'wake' && !S.doctor) clearBlocks(); }, 45000);
    });
  }
  function focusBlock(id) {
    var hit = null; blocks.forEach(function (e) { if (e.dataset.id === id) hit = e; }); if (!hit) return false;
    blocks.forEach(function (e) { if (e === hit) { e.style.zIndex = 5; e.animate([{ transform: 'scale(1)' }, { transform: 'scale(1.7)' }], { duration: reduce.matches ? 1 : 420, easing: EASE, fill: 'forwards' }); } else e.animate([{ opacity: 1 }, { opacity: .1 }], { duration: reduce.matches ? 1 : 300, fill: 'forwards' }); });
    return true;
  }
  function scene() { return blocks.map(function (e) { var h = e.querySelector('h4'); return { id: e.dataset.id, t: h ? h.firstChild.textContent : '' }; }); }

  // ---- the doctor: its work shows in a block that keeps itself current
  function stopDoctor() { clearInterval(S.doctorTimer); S.doctorTimer = null; S.doctor = null; }
  function paintDoctor(state) {
    var e = S.doctor; if (!e || !e.isConnected) return stopDoctor();
    var m = state.missions[0]; if (!m) return;
    var done = m.status === 'awaiting_review';
    e._body.textContent = done ? (m.answer || 'Finished.').slice(0, 420) : m.status === 'applied' ? 'Applied.' : m.status === 'discarded' ? 'Discarded.' : m.status === 'failed' ? ('It failed: ' + (m.error || '')).slice(0, 200) : 'Working in a private copy of the Hub…';
    e._acts.replaceChildren();
    if (done && m.changed) {
      var ap = el('button', 'go', 'APPLY THE FIX'), dc = el('button', 'go no', 'DISCARD'); ap.type = dc.type = 'button';
      ap.onclick = function () { runLine('apply the fix'); }; dc.onclick = function () { runLine('discard it'); };
      e._acts.append(ap, dc);
    }
    if (m.status === 'applied') { var rs = el('button', 'go', 'RESTART THE HUB'); rs.type = 'button'; rs.onclick = function () { runLine('restart the hub'); }; e._acts.appendChild(rs); }
    place(blocks);
  }
  function watchDoctor() {
    clearInterval(S.doctorTimer);
    function tick() { fetch('/api/support/state', { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).then(function (s) { if (s) paintDoctor(s); }).catch(function () {}); }
    tick(); S.doctorTimer = setInterval(tick, 3000);
  }

  function openHome() {
    // the same button, the same cube turn, as a tap on ENTER
    if (enterBtn && !enterBtn.disabled) { if (window.HubBlocks) HubBlocks.remember(blocks); stopAll(false); enterBtn.click(); }
  }

  // ---- speaking, with the ring pulsing to the voice; talking over it cuts it off
  function play(text) {
    return new Promise(function (resolve) {
      var done = false, tick = null, rhythm = null, guard = null, node = null;
      function fin() { if (done) return; done = true; clearInterval(tick); clearInterval(rhythm); clearInterval(guard); try { if (node) node.stop(); } catch (e) {} S.speaking = false; resolve(); }
      S.speaking = true; setState('speak'); pulse(); rhythm = setInterval(pulse, 620);
      var t0 = performance.now(), floor = 0, hi = 0, lastT = t0;
      guard = setInterval(function () {
        var now = performance.now(), r = rms(); if (now - t0 < 600) { floor = Math.max(floor, r); lastT = now; return; }
        var limit = Math.max(0.12, floor * 2.2 + 0.04); hi = r > limit ? hi + (now - lastT) : 0; lastT = now;
        if (hi > 300 && !done) { S.barged = true; pulse(); fin(); }
      }, 30);
      var voice = null; try { voice = localStorage.getItem('hubVoiceName'); } catch (e) {}
      post('/api/voice/speak', { text: text, voice: voice || undefined }, 'speech', 20000).then(function (ab) {
        return S.actx.decodeAudioData(ab.slice(0)).then(function (buf) {
          var src = node = S.actx.createBufferSource(), an = S.actx.createAnalyser(), data = new Uint8Array(512), last = 0;
          an.fftSize = 512; src.buffer = buf; src.connect(an); an.connect(S.actx.destination); src.onended = fin; src.start();
          tick = setInterval(function () { an.getByteTimeDomainData(data); var s = 0; for (var i = 0; i < data.length; i++) { var v = (data[i] - 128) / 128; s += v * v; } if (Math.sqrt(s / data.length) > 0.07 && performance.now() - last > 380) { last = performance.now(); pulse(); } }, 80);
        });
      }).catch(fin);
      setTimeout(fin, 45000);
    });
  }

  // ---- hearing
  function open() {
    if (S.stream && S.stream.active) return Promise.resolve(true);
    return navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }).then(function (s) {
      var AC = window.AudioContext || window.webkitAudioContext; S.stream = s; S.ctx = new AC(); S.an = S.ctx.createAnalyser(); S.an.fftSize = 1024; S.ctx.createMediaStreamSource(s).connect(S.an); return true;
    }).catch(function () { return false; });
  }
  function release() { try { if (S.stream) S.stream.getTracks().forEach(function (t) { t.stop(); }); if (S.ctx) S.ctx.close(); } catch (e) {} S.stream = S.ctx = S.an = null; }
  function mime() { var l = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']; for (var i = 0; i < l.length; i++) if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(l[i])) return l[i]; return ''; }
  function utterance(run) {
    return new Promise(function (resolve) {
      var mt = mime(), mr = new MediaRecorder(S.stream, mt ? { mimeType: mt } : undefined), chunks = [], spoke = false, quiet = 0, started = 0, t0 = performance.now();
      mr.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
      mr.onstop = function () { resolve(spoke && performance.now() - started > 350 ? new Blob(chunks, { type: mr.mimeType || 'audio/webm' }) : null); };
      mr.start();
      (function loop() {
        if (!S.on || run !== S.run || S.speaking || S.state === 'think') { try { mr.state !== 'inactive' && mr.stop(); } catch (e) {} spoke = false; return; }
        var r = rms(), now = performance.now();
        if (r > 0.04) { if (!spoke) started = now; spoke = true; quiet = 0; } else if (spoke && !quiet) quiet = now;
        if ((spoke && quiet && now - quiet > 900) || (spoke && now - started > 12000)) { try { mr.stop(); } catch (e) {} return; }
        if (!spoke && now - t0 > 20000) { try { mr.stop(); } catch (e) {} return; }   // recycle the recorder now and then
        setTimeout(loop, 40);
      })();
    });
  }
  function hear(blob) { return post('/api/voice/transcribe', blob, 'audio', 40000).then(function (j) { return (j.text || '').trim(); }); }

  // ---- one line from you: the Hub decides what it means
  function afterReply() { S.convoUntil = Date.now() + CONVO_MS; S.barged = false; setState('convo'); }
  // A button (APPLY, DISCARD, RESTART) always works, even while Smith is mid-thought; only a second press of the same one is ignored.
  var lineBusy = {};
  function runLine(text) {
    if (lineBusy[text]) return;
    lineBusy[text] = true;
    var done = function () { lineBusy[text] = false; };
    S.convoUntil = Date.now() + CONVO_MS; ask(text).catch(function () { return reply({ say: 'I could not do that just now.' }, text); }).then(done, done);
  }
  function ask(text) {
    setState('think'); say(text, 'you');
    var YES = /^\W*(yes|yeah|yep|sure|okay|ok|go ahead|do it|confirm)\b/i, NO = /^\W*(no|nope|cancel|stop|don'?t|never mind)\b/i;
    if (S.pending) {
      var p = S.pending; S.pending = null;
      if (YES.test(text)) return p.restart ? restartHub() : act(p, text);
      if (NO.test(text)) return reply({ say: 'Okay, cancelled. Nothing was changed.' }, text);
    }
    S.history.push({ role: 'user', text: text });
    return post('/api/voice/chat', { text: text, history: S.history.slice(-9, -1), scene: scene() }, 'json', 60000).then(function (r) {
      S.history.push({ role: 'assistant', text: r.say || '' });
      if (r.ask === 'restart') { S.pending = { restart: true }; return reply(r, text); }
      if (r.action && r.confirm) { S.pending = r; return reply(r, text); }
      if (r.action && !r.url) return act(r, text);
      return reply(r, text);
    });
  }
  function restartHub() { return post('/api/restart', {}, 'json', 8000).catch(function () {}).then(function () { return reply({ say: 'Restarting. I will be back in a few seconds.' }, 'restart'); }); }
  function act(r, text) { return post('/api/voice/act', { id: r.action.id, args: r.action.args }, 'json', 90000).then(function (j) { if (j.action && j.confirm) S.pending = j; return reply(j, text); }); }

  // what to show comes from the answer's own `ui`; the page only guesses when the Hub sent nothing
  function reply(r, asked) {
    var ui = r.ui || {}, sayText = r.say || '';
    say(sayText, 'smith');
    var show;
    if (ui.sleep) show = function () { clearBlocks(); return play(sayText).then(function () { S.convoUntil = 0; setState('wake'); }); };
    else if (ui.clear) show = function () { clearBlocks(); return play(sayText).then(afterReply); };
    else if (ui.open) show = function () { return play(sayText).then(openHome); };
    else if (ui.focus && focusBlock(ui.focus)) show = function () { return play(sayText).then(afterReply); };
    // applying or discarding the doctor's work answers inside its own block (which then offers RESTART), not in a new note that would replace it
    else if ((ui.apply || ui.discard) && S.doctor && S.doctor.isConnected) show = function () { watchDoctor(); return play(sayText).then(afterReply); };
    else {
      var list = ui.blocks && ui.blocks.length ? ui.blocks.slice() : null;
      if (ui.doctor_id) list = [{ id: 'doctor', t: 'THE DOCTOR', type: 'doctor' }];
      else if (ui.help) list = [{ id: 'help', t: 'YOU CAN SAY', type: 'note', text: 'show the dashboard · what is running · how is the PC · how much have I used · maximise the usage chart · clear the dashboard · open Home · something is wrong with the Hub · go to sleep' }];
      else if (!list && r.url) list = [{ id: 'note', t: 'SMITH', type: 'note', text: sayText, link: ['OPEN', r.url] }];
      else if (!list && sayText) list = [{ id: 'note', t: 'SMITH', type: 'note', text: sayText }];
      show = function () { if (list) raise(list); return play(sayText).then(afterReply); };
    }
    return Promise.resolve(show());
  }

  function loop(run) {
    if (!S.on || run !== S.run) return;
    if (S.speaking || S.state === 'think') { setTimeout(function () { loop(run); }, 150); return; }     // no recorder while it is answering
    utterance(run).then(function (blob) {
      if (!S.on || run !== S.run || !blob) return;
      return hear(blob).then(function (text) {
        if (!text) return;
        var w = wakeSplit(text), convo = Date.now() < S.convoUntil, rest = w ? w.rest : text;
        if (!w && !convo && !S.pending) return;                      // no wake word, not in a conversation: ignore, nothing leaves the PC
        if (rest.replace(/[^\w]/g, '').length < 2 && !w) return;
        pulse();
        if (w && rest.replace(/[^\w]/g, '').length < 2) {            // just the name: answer and wait for the request
          say('Yes?', 'smith'); return play('Yes?').then(function () { S.convoUntil = Date.now() + CONVO_MS; setState('convo'); });
        }
        return ask(rest).catch(function () { return reply({ say: 'I could not do that just now.' }, rest); });
      }).catch(function () {});
    }).then(function () { setTimeout(function () { loop(run); }, 50); });
  }

  function stopAll(clearKey) { S.on = false; S.run++; S.pending = null; S.convoUntil = 0; clearBlocks(); Array.prototype.slice.call(lines.children).forEach(function (c) { fadeOut(c); }); release(); if (clearKey !== false) { try { localStorage.setItem(KEY, '0'); } catch (e) {} } setState('off'); }
  function start() {
    if (!secure()) { setLabel('NEEDS HTTPS'); btn.title = 'The browser only allows the microphone on https. Open the Hub through its Tailscale address.'; return; }
    var AC = window.AudioContext || window.webkitAudioContext; if (!S.actx && AC) S.actx = new AC(); if (S.actx && S.actx.state === 'suspended') S.actx.resume();
    open().then(function (ok) {
      if (!ok) { setLabel('MICROPHONE BLOCKED'); return; }
      S.on = true; S.run++; try { localStorage.setItem(KEY, '1'); } catch (e) {} setState('wake'); pulse(); loop(S.run);
    });
  }
  btn.onclick = function () { if (S.on) stopAll(); else start(); };
  // It keeps listening when another window comes in front (opening an app by voice used to switch it off); only leaving the page ends it.
  addEventListener('pagehide', function () { if (S.on) stopAll(); });
  addEventListener('resize', function () { if (blocks.length) clearBlocks(); });
  window.__hubWake = { state: function () { return S.state; }, blocks: function () { return blocks.length; }, say: function (t) { return ask(t); } };
  setState('off');
})();
