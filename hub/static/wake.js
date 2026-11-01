// Wake word on the landing page, and only there: say "Smith" and the core answers.
// It is off until you switch it on (a browser asks for the microphone then, and shows its own indicator).
// The audio never leaves the PC: sound above a quiet threshold is cut into utterances, each is transcribed by the
// Hub's local Whisper, and only an utterance that contains the wake word goes any further. What you ask afterwards
// uses the same endpoints as Talk (/api/voice/chat, /api/voice/act, /api/voice/speak), and the answer is shown as
// panels that rise around the core while the core pulses to the voice.
(function () {
  var btn = document.getElementById('wake-toggle'), stage = document.getElementById('wake-stage');
  if (!btn || !stage) return;
  var WORD = /\b(smith|smyth|smythe|smit|smid|schmidt)\b[\s,.!?:-]*/i;
  var KEY = 'agenthub:wake', EASE = 'cubic-bezier(.2,.8,.2,1)';
  var reduce = matchMedia('(prefers-reduced-motion: reduce)');
  var S = { on: false, stream: null, ctx: null, an: null, busy: false, speaking: false, run: 0, actx: null, pending: null, history: [] };
  var BUF = new Uint8Array(1024);

  function mark() { return window.dormantGlobe; }
  function pulse() { try { var m = mark(); if (m && m.pulse) m.pulse(); } catch (e) {} }
  function say(t) { btn.title = t; }
  function paint() {
    btn.setAttribute('aria-pressed', String(S.on));
    btn.querySelector('.t').textContent = S.on ? (S.busy ? 'SMITH IS ANSWERING' : 'LISTENING FOR SMITH') : 'WAKE WORD · OFF';
    btn.classList.toggle('on', S.on);
  }
  function secure() { return !!(window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder); }
  function rms() { if (!S.an) return 0; S.an.getByteTimeDomainData(BUF); var s = 0; for (var i = 0; i < BUF.length; i++) { var v = (BUF[i] - 128) / 128; s += v * v; } return Math.sqrt(s / BUF.length); }
  function post(u, body, kind, ms) {
    var c = new AbortController(), t = setTimeout(function () { c.abort(); }, ms || 30000);
    return fetch(u, { method: 'POST', signal: c.signal, headers: { 'Content-Type': kind === 'audio' ? (body.type || 'audio/webm') : 'application/json' }, body: kind === 'audio' ? body : JSON.stringify(body || {}) })
      .then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return kind === 'speech' ? r.arrayBuffer() : r.json(); }).finally(function () { clearTimeout(t); });
  }

  // ---- panels around the core: they rise in one after another and leave on their own
  var cards = [];
  function card(kind, text, extra) {
    var c = document.createElement('div'); c.className = 'wk-card ' + kind;
    var t = document.createElement('div'); t.className = 'wk-t'; t.textContent = text; c.appendChild(t);
    if (extra) c.appendChild(extra);
    stage.appendChild(c); cards.push(c);
    if (!reduce.matches) c.animate([{ opacity: 0, transform: 'translateY(18px) scale(.96)' }, { opacity: 1, transform: 'none' }], { duration: 420, easing: EASE, delay: (cards.length - 1) * 70, fill: 'backwards' });
    return c;
  }
  function clearCards(now) {
    var old = cards; cards = [];
    old.forEach(function (c, i) {
      if (reduce.matches || now) return c.remove();
      var a = c.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translateY(-10px) scale(.97)' }], { duration: 260, easing: EASE, delay: i * 40, fill: 'forwards' });
      a.onfinish = function () { c.remove(); };
    });
  }
  var fade = null;
  function later() { clearTimeout(fade); fade = setTimeout(function () { if (!S.pending) clearCards(); }, 14000); }

  // ---- speaking: the core pulses with the voice
  function play(text) {
    return new Promise(function (resolve) {
      var done = false, tick = null;
      function fin() { if (done) return; done = true; clearInterval(tick); S.speaking = false; resolve(); }
      S.speaking = true; var voice = null; try { voice = localStorage.getItem('hubVoiceName'); } catch (e) {}
      post('/api/voice/speak', { text: text, voice: voice || undefined }, 'speech', 20000).then(function (ab) {
        return S.actx.decodeAudioData(ab.slice(0)).then(function (buf) {
          var src = S.actx.createBufferSource(), an = S.actx.createAnalyser(), data = new Uint8Array(512), last = 0;
          an.fftSize = 512; src.buffer = buf; src.connect(an); an.connect(S.actx.destination); src.onended = fin; src.start();
          tick = setInterval(function () {
            an.getByteTimeDomainData(data); var s = 0; for (var i = 0; i < data.length; i++) { var v = (data[i] - 128) / 128; s += v * v; }
            if (Math.sqrt(s / data.length) > 0.06 && performance.now() - last > 420) { last = performance.now(); pulse(); }
          }, 80);
        });
      }).catch(fin);
      setTimeout(fin, 45000);
    });
  }

  // ---- hearing
  function open() {
    if (S.stream && S.stream.active) return Promise.resolve(true);
    return navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }).then(function (st) {
      var AC = window.AudioContext || window.webkitAudioContext; S.stream = st; S.ctx = new AC(); S.an = S.ctx.createAnalyser(); S.an.fftSize = 1024;
      S.ctx.createMediaStreamSource(st).connect(S.an); return true;
    }).catch(function () { return false; });
  }
  function release() { try { if (S.stream) S.stream.getTracks().forEach(function (t) { t.stop(); }); if (S.ctx) S.ctx.close(); } catch (e) {} S.stream = S.ctx = S.an = null; }
  function mime() { var l = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']; for (var i = 0; i < l.length; i++) if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(l[i])) return l[i]; return ''; }
  // resolves with a blob when one utterance ends (0.9 s quiet after speech), or null if nothing was said within maxWait
  function utterance(run, maxWait) {
    return new Promise(function (resolve) {
      var mt = mime(), mr = new MediaRecorder(S.stream, mt ? { mimeType: mt } : undefined), chunks = [], spoke = false, quiet = 0, t0 = performance.now(), started = 0;
      mr.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
      mr.onstop = function () { resolve(spoke && performance.now() - started > 350 ? new Blob(chunks, { type: mr.mimeType || 'audio/webm' }) : null); };
      mr.start();
      (function loop() {
        if (!S.on || run !== S.run || S.speaking) { try { mr.state !== 'inactive' && mr.stop(); } catch (e) {} spoke = false; return; }
        var r = rms(), now = performance.now();
        if (r > 0.04) { if (!spoke) started = now; spoke = true; quiet = 0; } else if (spoke && !quiet) quiet = now;
        if ((spoke && quiet && now - quiet > 900) || (spoke && now - started > 12000) || (!spoke && maxWait && now - t0 > maxWait)) { try { mr.stop(); } catch (e) {} return; }
        setTimeout(loop, 40);
      })();
    });
  }
  function hear(blob) { return post('/api/voice/transcribe', blob, 'audio', 40000).then(function (j) { return (j.text || '').trim(); }); }

  // ---- what happens after the word
  function answer(text) {
    S.busy = true; paint(); clearCards(true); card('you', text);
    var YES = /^(yes|yeah|yep|sure|okay|ok|go ahead|do it|confirm)\b/i, NO = /^(no|nope|cancel|stop|don'?t|never mind)\b/i;
    var next;
    if (S.pending) {
      var p = S.pending; S.pending = null;
      if (YES.test(text)) next = act(p); else if (NO.test(text)) next = Promise.resolve(shown('Okay, cancelled. Nothing was changed.'));
      else next = ask(text);
    } else next = ask(text);
    return next.catch(function () { return shown('I could not do that just now.'); }).then(function () { S.busy = false; paint(); later(); });
  }
  function shown(t, link) {
    var extra = null;
    if (link) { extra = document.createElement('a'); extra.className = 'wk-b'; extra.href = link; extra.textContent = 'OPEN'; }
    card('hub', t, extra); return play(t);
  }
  function ask(text) {
    S.history.push({ role: 'user', text: text });
    return post('/api/voice/chat', { text: text, history: S.history.slice(-9, -1) }, 'json', 60000).then(function (r) {
      S.history.push({ role: 'assistant', text: r.say || '' });
      if (r.action && r.confirm) { S.pending = r; return confirmCard(r); }
      if (r.action && !r.url) return act(r);
      return shown(r.say, r.url);
    });
  }
  function act(r) {
    return post('/api/voice/act', { id: r.action.id, args: r.action.args }, 'json', 90000).then(function (j) {
      if (j.action && j.confirm) { S.pending = j; return confirmCard(j); }
      return shown(j.say, j.url);
    });
  }
  function confirmCard(r) {
    var row = document.createElement('div'); row.className = 'wk-row';
    [['YES', true], ['NO', false]].forEach(function (x) {
      var b = document.createElement('button'); b.type = 'button'; b.className = 'wk-b'; b.textContent = x[0];
      b.onclick = function () { if (!S.pending || S.busy) return; var p = S.pending; S.pending = null; S.busy = true; paint(); clearCards(true); card('you', x[0]);
        (x[1] ? act(p) : Promise.resolve(shown('Okay, cancelled. Nothing was changed.'))).catch(function () { return shown('I could not do that just now.'); }).then(function () { S.busy = false; paint(); later(); }); };
      row.appendChild(b);
    });
    card('hub', r.say, row); return play(r.say);
  }

  function loop(run) {
    if (!S.on || run !== S.run) return;
    utterance(run, 0).then(function (blob) {
      if (!S.on || run !== S.run) return;
      if (!blob) return setTimeout(function () { loop(run); }, 60);
      return hear(blob).then(function (text) {
        var m = WORD.exec(text);
        if (S.pending && text) return answer(text);                         // a yes or no to a question just asked needs no wake word
        if (!m) return;
        pulse(); var rest = text.slice(m.index + m[0].length).trim();
        if (rest.replace(/[^\w]/g, '').length > 2) return answer(rest);
        clearCards(true); card('hub', 'Yes?'); S.busy = true; paint();
        return play('Yes?').then(function () { return utterance(run, 7000); }).then(function (b2) {
          if (!b2) { S.busy = false; paint(); clearCards(); return; }
          return hear(b2).then(function (t2) { S.busy = false; if (t2.replace(/[^\w]/g, '').length > 2) return answer(t2); paint(); clearCards(); });
        });
      }).catch(function () {});
    }).then(function () { setTimeout(function () { loop(run); }, 60); });
  }

  function stop() { S.on = false; S.run++; S.pending = null; clearCards(true); release(); try { localStorage.setItem(KEY, '0'); } catch (e) {} paint(); }
  function start() {
    if (!secure()) { btn.querySelector('.t').textContent = 'NEEDS HTTPS'; say('The browser only allows the microphone on https. Open the Hub through its Tailscale address.'); return; }
    var AC = window.AudioContext || window.webkitAudioContext; if (!S.actx && AC) S.actx = new AC(); if (S.actx && S.actx.state === 'suspended') S.actx.resume();
    open().then(function (ok) {
      if (!ok) { btn.querySelector('.t').textContent = 'MICROPHONE BLOCKED'; return; }
      S.on = true; S.run++; try { localStorage.setItem(KEY, '1'); } catch (e) {} paint(); loop(S.run);
    });
  }
  btn.onclick = function () { if (S.on) stop(); else start(); };
  // Leaving the page, or hiding it, releases the microphone; coming back needs a tap again (the browser requires it).
  function off() { if (S.on) stop(); }
  window.addEventListener('pagehide', off);
  document.addEventListener('visibilitychange', function () { if (document.hidden) off(); });
  paint();
})();
