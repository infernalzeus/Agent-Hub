// Wake word on the landing page, and only there. Off until you switch it on.
// Say "Smith" and the ring answers; after that it is a conversation: follow-ups need no wake word until it has been
// quiet for a while. The answer comes back as blocks that rise out of the ring (a list, a number, a note) and a spoken
// reply, and the ring pulses while it listens and speaks. "Open Home" uses the same ENTER button and cube turn as a tap;
// "go to sleep" folds the blocks back. Audio stays on the PC: sentences are transcribed by the Hub's local Whisper.
(function () {
  var btn = document.getElementById('wake-toggle'), stage = document.getElementById('wake-stage'), enterBtn = document.getElementById('wake-btn');
  if (!btn || !stage) return;
  var WORD = /^\W*(?:(?:hey|hi|okay|ok)\s+)?(smith|smyth|smythe|smit|smid|schmidt)\b[\s,.!?:-]*/i;
  var SLEEP = /\b(go to sleep|goodnight|good night|that'?s all|that is all|sleep now|goodbye|bye)\b/i;
  var HOME = /\b(open (the )?(home|hub)|go (to )?home|enter( the hub)?|take me (in|home))\b/i;
  var KEY = 'agenthub:wake', EASE = 'cubic-bezier(.2,.8,.2,1)', SPRING = 'cubic-bezier(.34,1.45,.64,1)', CONVO_MS = 14000;
  var reduce = matchMedia('(prefers-reduced-motion: reduce)');
  var S = { on: false, stream: null, ctx: null, an: null, state: 'off', speaking: false, run: 0, actx: null, pending: null, history: [], convoUntil: 0, clear: null };
  var BUF = new Uint8Array(1024);

  var st = document.createElement('style');
  st.textContent = [
    '#wake-ring{position:absolute;inset:6%;border-radius:50%;pointer-events:none;opacity:0;border:2px solid rgba(0,230,118,.7);box-shadow:0 0 28px rgba(0,230,118,.35),inset 0 0 28px rgba(0,230,118,.15);transition:opacity .4s}',
    '#wake-ring.on{opacity:.9;animation:wkBreath 2.6s ease-in-out infinite}#wake-ring.hot{animation:wkBreath 1.2s ease-in-out infinite;border-color:#7bffd0}',
    '@keyframes wkBreath{50%{transform:scale(1.035);opacity:.45}}',
    '.wk-wave{position:absolute;inset:6%;border-radius:50%;pointer-events:none;border:2px solid rgba(0,230,118,.8)}',
    '#wake-stage{position:fixed;inset:0;pointer-events:none;z-index:6}',
    '.wb{position:absolute;width:236px;background:rgba(6,10,36,.93);border:1px solid rgba(0,230,118,.3);border-radius:3px;pointer-events:auto;will-change:transform,opacity;color:#d9ffe9;text-align:left}',
    '.wb::before,.wb::after{content:"";position:absolute;width:9px;height:9px;pointer-events:none}.wb::before{left:-2px;top:-2px;border-left:2px solid #00e676;border-top:2px solid #00e676}.wb::after{right:-2px;bottom:-2px;border-right:2px solid #00e676;border-bottom:2px solid #00e676}',
    '.wb.amber{border-color:rgba(224,165,60,.6)}.wb.red{border-color:rgba(255,92,92,.6)}',
    '.wb h4{margin:0;padding:7px 10px 3px;font:700 8.5px Orbitron,monospace;letter-spacing:1.4px;color:#8fcfb2;display:flex;justify-content:space-between}',
    '.wb .li{display:flex;gap:8px;align-items:baseline;padding:4px 10px;border-top:1px solid rgba(255,255,255,.05);font-size:12.5px}.wb .li i{width:6px;height:6px;border-radius:50%;background:#00e676;flex:none}.wb .li i.a{background:#e0a53c}.wb .li i.r{background:#ff5c5c}.wb .li i.o{background:#6fae92}.wb .li span{color:#8fcfb2;font-size:11.5px;overflow-wrap:anywhere}',
    '.wb .num{padding:2px 10px 8px}.wb .num b{display:block;font:900 30px Orbitron,monospace;color:#00e676;line-height:1.1}.wb .num span{color:#8fcfb2;font-size:12px}',
    '.wb .nt{padding:2px 10px 9px;font-size:13px;line-height:1.45}',
    '.wb .row{display:flex;gap:8px;padding:2px 10px 10px}.wb .go{font:700 9.5px Orbitron,monospace;letter-spacing:1.2px;color:#00e676;background:none;border:1px solid #00e676;border-radius:7px;padding:8px 14px;min-height:34px;cursor:pointer}',
    '#wake-lines{position:fixed;left:50%;bottom:max(12px,env(safe-area-inset-bottom));transform:translateX(-50%);width:min(560px,92vw);display:flex;flex-direction:column;gap:5px;align-items:center;pointer-events:none;z-index:7}',
    '.wl{font-size:13.5px;padding:5px 12px;border-radius:99px;border:1px solid rgba(0,230,118,.3);background:rgba(6,10,36,.92);color:#d9ffe9;max-width:100%}.wl.you{border-color:rgba(59,167,255,.5);color:#cfe6ff}'
  ].join('\n');
  document.head.appendChild(st);
  var lines = document.createElement('div'); lines.id = 'wake-lines'; document.body.appendChild(lines);
  var globe = document.querySelector('.globe-wrap'), ring = null;
  if (globe) { ring = document.createElement('div'); ring.id = 'wake-ring'; globe.appendChild(ring); }

  function mark() { return window.dormantGlobe; }
  function pulse() {
    try { var m = mark(); if (m && m.pulse) m.pulse(); } catch (e) {}
    if (!ring || reduce.matches) return;
    var w = document.createElement('div'); w.className = 'wk-wave'; globe.appendChild(w);
    var a = w.animate([{ transform: 'scale(1)', opacity: .9 }, { transform: 'scale(1.28)', opacity: 0 }], { duration: 900, easing: 'ease-out' }); a.onfinish = function () { w.remove(); };
  }
  function setState(s) {
    S.state = s;
    var label = { off: 'WAKE WORD · OFF', wake: 'LISTENING FOR SMITH', convo: 'LISTENING', think: 'THINKING', speak: 'SPEAKING' }[s];
    btn.querySelector('.t').textContent = label; btn.classList.toggle('on', s !== 'off'); btn.setAttribute('aria-pressed', String(s !== 'off'));
    if (ring) { ring.classList.toggle('on', s !== 'off'); ring.classList.toggle('hot', s === 'convo' || s === 'speak' || s === 'think'); }
  }
  function say(text, who) {
    var l = document.createElement('div'); l.className = 'wl ' + who; l.textContent = (who === 'you' ? 'You: ' : 'Smith: ') + text; lines.appendChild(l);
    while (lines.children.length > 3) lines.firstChild.remove();
    if (!reduce.matches) l.animate([{ opacity: 0, transform: 'translateY(10px)' }, { opacity: 1, transform: 'none' }], { duration: 300, easing: EASE });
  }
  function secure() { return !!(window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder); }
  function rms() { if (!S.an) return 0; S.an.getByteTimeDomainData(BUF); var s = 0; for (var i = 0; i < BUF.length; i++) { var v = (BUF[i] - 128) / 128; s += v * v; } return Math.sqrt(s / BUF.length); }
  function post(u, body, kind, ms) {
    var c = new AbortController(), t = setTimeout(function () { c.abort(); }, ms || 30000);
    return fetch(u, { method: 'POST', signal: c.signal, headers: { 'Content-Type': kind === 'audio' ? (body.type || 'audio/webm') : 'application/json' }, body: kind === 'audio' ? body : JSON.stringify(body || {}) })
      .then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return kind === 'speech' ? r.arrayBuffer() : r.json(); }).finally(function () { clearTimeout(t); });
  }
  function ctxNow() { return post.bind(null); }

  // ---- blocks that rise out of the ring
  var blocks = [];
  function center() { var r = (globe || document.body).getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2, R: r.width / 2 }; }
  function slot(i, n) {
    var c = center(), w = 236, vw = innerWidth, left = i % 2 === 0, row = Math.floor(i / 2);
    var x = left ? Math.max(12, c.x - c.R * 1.02 - w - 8) : Math.min(vw - w - 12, c.x + c.R * 1.02 + 8);
    if (vw < 760) { x = Math.max(8, Math.min(vw - w - 8, left ? 8 : vw - w - 8)); }
    var y = Math.max(60, c.y - c.R * .9 + row * 150 + (left ? 0 : 20)); return { x: x, y: y, w: w };
  }
  function mkBlock(b) {
    var e = document.createElement('div'); e.className = 'wb ' + (b.cls || ''); e.dataset.id = b.id || ''; var h = document.createElement('h4'); h.textContent = b.t; if (b.n) { var n = document.createElement('span'); n.textContent = b.n; h.appendChild(n); } e.appendChild(h);
    if (b.type === 'list') b.rows.forEach(function (r) { var d = document.createElement('div'); d.className = 'li'; var i = document.createElement('i'); i.className = r[0] || ''; var bb = document.createElement('b'); bb.textContent = r[1]; d.append(i, bb); if (r[2]) { var s = document.createElement('span'); s.textContent = r[2]; d.appendChild(s); } e.appendChild(d); });
    if (b.type === 'num') { var d = document.createElement('div'); d.className = 'num'; var bb = document.createElement('b'); bb.textContent = b.big; var s = document.createElement('span'); s.textContent = b.cap; d.append(bb, s); e.appendChild(d); }
    if (b.type === 'bars') {
      var bx = document.createElement('div'); bx.style.cssText = 'display:flex;align-items:flex-end;gap:2px;height:70px;padding:6px 10px 2px'; var mx = Math.max.apply(null, b.values.concat([1]));
      b.values.forEach(function (v) { var i = document.createElement('i'); i.style.cssText = 'flex:1;background:linear-gradient(#3ba7ff,rgba(59,167,255,.25));border:1px solid rgba(59,167,255,.6);border-bottom:0;height:' + Math.max(2, Math.round(v / mx * 100)) + '%'; bx.appendChild(i); }); e.appendChild(bx);
      var cp = document.createElement('div'); cp.className = 'nt'; cp.style.fontSize = '11.5px'; cp.style.color = '#8fcfb2'; cp.textContent = b.cap; e.appendChild(cp);
    }
    if (b.type === 'note') { var nt = document.createElement('div'); nt.className = 'nt'; nt.textContent = b.text; e.appendChild(nt); }
    if (b.home) { var row = document.createElement('div'); row.className = 'row'; var g = document.createElement('button'); g.type = 'button'; g.className = 'go'; g.textContent = 'OPEN HOME'; g.onclick = openHome; row.appendChild(g); e.appendChild(row); }
    return e;
  }
  function retract(now) {
    var old = blocks; blocks = []; var c = center();
    old.forEach(function (e, i) { if (reduce.matches || now) return e.remove(); var l = e.getBoundingClientRect(); var a = e.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translate(' + (c.x - l.left - l.width / 2) + 'px,' + (c.y - l.top - l.height / 2) + 'px) scale(.12)' }], { duration: 340, delay: i * 40, easing: 'cubic-bezier(.5,0,.8,.4)', fill: 'forwards' }); a.onfinish = function () { e.remove(); }; });
  }
  function raise(list) {
    retract(false); var c = center();
    list.slice(0, 4).forEach(function (b, i) {
      var e = mkBlock(b), p = slot(i, list.length); e.style.left = p.x + 'px'; e.style.top = p.y + 'px'; stage.appendChild(e); blocks.push(e);
      if (!reduce.matches) { var l = e.getBoundingClientRect(); e.animate([{ opacity: 0, transform: 'translate(' + (c.x - l.left - l.width / 2) + 'px,' + (c.y - l.top - l.height / 2) + 'px) scale(.12)' }, { opacity: 1, transform: 'none' }], { duration: 650, delay: 80 + i * 110, easing: SPRING, fill: 'backwards' }); }
    });
    clearTimeout(S.clear); S.clear = setTimeout(function () { if (S.state === 'wake') retract(false); }, 40000);
  }
  function blocksFor(text, answer) {
    return fetch('/api/home/state', { cache: 'no-store' }).then(function (r) { return r.ok ? r.json() : null; }).catch(function () { return null; }).then(function (d) {
      var t = text.toLowerCase(), out = [];
      if (d && /running|mission|attention|need|proposal|waiting|session|busy|doing/.test(t)) {
        var a = d.attention.slice(0, 3).map(function (x) { return [x.level === 'red' ? 'r' : 'a', x.title, '']; });
        out.push({ t: 'NEEDS YOU', n: String(d.attention.length), type: 'list', cls: d.attention.length ? 'amber' : '', rows: a.length ? a : [['o', 'Nothing needs you right now', '']] });
        out.push({ t: 'RUNS', type: 'num', big: String(d.runs.length), cap: 'missions running' });
        var ss = d.sessions; out.push({ t: 'SESSIONS', type: 'num', big: String(ss.working.length + ss.needs_you.length), cap: ss.needs_you.length + ' need you · ' + ss.working.length + ' working' });
      } else if (d && /health|pc|disk|model|computer|machine|ok\b|fine/.test(t)) {
        var h = d.health; out.push({ t: 'HEALTH', type: 'list', rows: [['', 'Hub v' + h.version, 'up ' + Math.round(h.uptime_s / 60) + ' min'], [h.local_model && h.local_model.listening ? '' : 'o', 'Local model', h.local_model && h.local_model.listening ? 'listening' : 'off'], [h.recent_problems ? 'a' : '', 'Warnings', String(h.recent_problems)]] });
        out.push({ t: 'DISK', type: 'num', big: (h.disk_free_gb.work != null ? Math.round(h.disk_free_gb.work) : '?') + ' GB', cap: 'free where missions work' });
      }
      if (!out.length) out.push({ t: 'SMITH', type: 'note', text: answer, home: /home|hub|app/.test(t) });
      return out;
    });
  }

  function focusBlock(id) {
    var hit = null; blocks.forEach(function (e) { if (e.dataset.id === id) hit = e; });
    if (!hit) return false;
    blocks.forEach(function (e) { if (e === hit) { e.style.zIndex = 5; e.animate([{ transform: 'scale(1)' }, { transform: 'scale(1.7)' }], { duration: reduce.matches ? 1 : 420, easing: EASE, fill: 'forwards' }); } else e.animate([{ opacity: 1 }, { opacity: .1 }], { duration: reduce.matches ? 1 : 300, fill: 'forwards' }); });
    return true;
  }
  function scene() { return blocks.map(function (e) { var h = e.querySelector('h4'); return { id: e.dataset.id, t: h ? h.firstChild.textContent : '' }; }); }

  function openHome() {
    say('Opening Home.', 'smith');
    // the same button, the same cube turn, as a tap on ENTER
    if (enterBtn && !enterBtn.disabled) { stopAll(false); enterBtn.click(); }
  }

  // ---- speaking, with the ring pulsing to the voice
  function play(text) {
    return new Promise(function (resolve) {
      var done = false, tick = null, rhythm = null, guard = null, node = null;
      function fin() { if (done) return; done = true; clearInterval(tick); clearInterval(rhythm); clearInterval(guard); try { if (node) node.stop(); } catch (e) {} S.speaking = false; resolve(); }
      // Talking over the reply: the microphone is listened to while Smith speaks. Its own voice coming back through the speakers is
      // measured for the first 0.6 s and counts as the floor; only a sound well above that floor, held for 0.3 s, cuts the reply off.
      var t0 = performance.now(), floor = 0, hi = 0, lastT = t0;
      guard = setInterval(function () {
        var now = performance.now(), r = rms(); if (now - t0 < 600) { floor = Math.max(floor, r); lastT = now; return; }
        var limit = Math.max(0.12, floor * 2.2 + 0.04); hi = r > limit ? hi + (now - lastT) : 0; lastT = now;
        if (hi > 300 && !done) { S.barged = true; say('(you talked over it)', 'you'); pulse(); fin(); }
      }, 30);
      S.speaking = true; setState('speak'); pulse(); rhythm = setInterval(pulse, 620);
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
      var mt = mime(), mr = new MediaRecorder(S.stream, mt ? { mimeType: mt } : undefined), chunks = [], spoke = false, quiet = 0, started = 0;
      mr.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
      mr.onstop = function () { resolve(spoke && performance.now() - started > 350 ? new Blob(chunks, { type: mr.mimeType || 'audio/webm' }) : null); };
      mr.start();
      (function loop() {
        if (!S.on || run !== S.run || S.speaking || S.state === 'think') { try { mr.state !== 'inactive' && mr.stop(); } catch (e) {} spoke = false; return; }
        var r = rms(), now = performance.now();
        if (r > 0.04) { if (!spoke) started = now; spoke = true; quiet = 0; } else if (spoke && !quiet) quiet = now;
        if ((spoke && quiet && now - quiet > 900) || (spoke && now - started > 12000)) { try { mr.stop(); } catch (e) {} return; }
        if (!spoke && now - (loop.t0 = loop.t0 || now) > 20000) { loop.t0 = 0; try { mr.stop(); } catch (e) {} return; }   // recycle the recorder now and then
        setTimeout(loop, 40);
      })();
    });
  }
  function hear(blob) { return post('/api/voice/transcribe', blob, 'audio', 40000).then(function (j) { return (j.text || '').trim(); }); }

  // ---- what happens after the word
  function afterReply() { S.convoUntil = Date.now() + CONVO_MS; S.barged = false; setState('convo'); }
  function ask(text) {
    setState('think'); say(text, 'you');
    var YES = /^\W*(yes|yeah|yep|sure|okay|ok|go ahead|do it|confirm)\b/i, NO = /^\W*(no|nope|cancel|stop|don'?t|never mind)\b/i;
    if (S.pending) {
      var p = S.pending; S.pending = null;
      if (YES.test(text)) return act(p, text); if (NO.test(text)) return reply('Okay, cancelled. Nothing was changed.', text);
    }
    S.history.push({ role: 'user', text: text });
    return post('/api/voice/chat', { text: text, history: S.history.slice(-9, -1), scene: scene() }, 'json', 60000).then(function (r) {
      S.history.push({ role: 'assistant', text: r.say || '' });
      if (r.action && r.confirm) { S.pending = r; return reply(r.say, text, r.ui); }
      if (r.action && !r.url) return act(r, text);
      return reply(r.say, text, r.ui);
    });
  }
  function act(r, text) { return post('/api/voice/act', { id: r.action.id, args: r.action.args }, 'json', 90000).then(function (j) { if (j.action && j.confirm) S.pending = j; return reply(j.say, text); }); }
  function reply(sayText, asked, ui) {
    say(sayText, 'smith');
    // the answer carries what to show (ui.blocks, ui.focus); the page guesses from the words only when the Hub sent nothing
    if (ui && ui.focus && focusBlock(ui.focus)) return play(sayText).then(afterReply);
    var shown = ui && ui.blocks && ui.blocks.length ? Promise.resolve(ui.blocks) : blocksFor(asked, sayText);
    return shown.then(function (b) { raise(b); return play(sayText); }).then(afterReply);
  }
  function handle(text) {
    if (SLEEP.test(text)) { say('Sleeping.', 'smith'); retract(false); S.convoUntil = 0; return play('Okay.').then(function () { setState('wake'); }); }
    if (HOME.test(text)) { say(text, 'you'); return Promise.resolve(openHome()); }
    return ask(text).catch(function () { return reply('I could not do that just now.', text); });
  }

  function loop(run) {
    if (!S.on || run !== S.run) return;
    utterance(run).then(function (blob) {
      if (!S.on || run !== S.run) return;
      if (!blob) return;
      return hear(blob).then(function (text) {
        if (!text) return;
        var m = WORD.exec(text), convo = Date.now() < S.convoUntil, rest = m ? text.slice(m[0].length).trim() : text;
        if (!m && !convo && !S.pending) return;                       // no wake word, not in a conversation: ignore, nothing leaves the PC
        if (!m && text.replace(/[^\w]/g, '').length < 3) return;
        pulse();
        if (m && rest.replace(/[^\w]/g, '').length < 3) {              // just the name: answer and wait for the request
          retract(true); say('Yes?', 'smith'); return play('Yes?').then(function () { S.convoUntil = Date.now() + CONVO_MS; setState('convo'); });
        }
        return handle(rest);
      }).catch(function () {});
    }).then(function () { setTimeout(function () { loop(run); }, 50); });
  }

  function stopAll(clearKey) { S.on = false; S.run++; S.pending = null; S.convoUntil = 0; retract(true); lines.replaceChildren(); release(); if (clearKey !== false) { try { localStorage.setItem(KEY, '0'); } catch (e) {} } setState('off'); }
  function start() {
    if (!secure()) { btn.querySelector('.t').textContent = 'NEEDS HTTPS'; btn.title = 'The browser only allows the microphone on https. Open the Hub through its Tailscale address.'; return; }
    var AC = window.AudioContext || window.webkitAudioContext; if (!S.actx && AC) S.actx = new AC(); if (S.actx && S.actx.state === 'suspended') S.actx.resume();
    open().then(function (ok) {
      if (!ok) { btn.querySelector('.t').textContent = 'MICROPHONE BLOCKED'; return; }
      S.on = true; S.run++; try { localStorage.setItem(KEY, '1'); } catch (e) {} setState('wake'); pulse(); loop(S.run);
    });
  }
  btn.onclick = function () { if (S.on) stopAll(); else start(); };
  addEventListener('pagehide', function () { if (S.on) stopAll(); });
  document.addEventListener('visibilitychange', function () { if (document.hidden && S.on) stopAll(); });
  addEventListener('resize', function () { if (blocks.length) retract(true); });
  window.__hubWake = { state: function () { return S.state; }, blocks: function () { return blocks.length; }, handle: function (t) { return handle(t); } };
  setState('off');
})();
