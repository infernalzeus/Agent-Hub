// The conversation popover: always-on listening until stopped, and you can talk over the reply. Microphone = the device whose browser this is
// (phone or PC); the audio goes to the hub PC for local Whisper (POST /api/voice/transcribe), the text to the assistant (POST /api/voice/chat),
// the reply comes back as speech (POST /api/voice/speak, Microsoft neural voice; the browser's own voice is the fallback).
(function () {
  const $ = (id) => document.getElementById(id);
  const KEY = 'hubVoiceSession';
  const AGENT_IDS = __AGENT_NAMES__;                                                    // id -> [name, designation], from the one place that holds them; Viktor is the name, Orchestrator his designation (the id stays 'orchestrator')
  const WHO = Object.fromEntries(Object.entries(AGENT_IDS).map(([k, v]) => [k, v[0]])), ROLE = Object.fromEntries(Object.entries(AGENT_IDS).map(([k, v]) => [k, v[1]]));
  const S = { who: 'smith', mission: null, on: false, speaking: false, pending: null, history: [], stream: null, ctx: null, an: null, whisper: null, voice: null, mute: false,
              audio: null, actx: null, stop: null, carry: null, turn: 0, capture: 0, listen: 0, busy: false,
              requests: new Set(), loop: null, compact: location.pathname === '/missions', expanded: false, context: null };
  const BUF = new Uint8Array(1024);
  // Whisper hears "Smith" as other names ("Kenya" was seen); the list is the net, the rule below catches the rest: within two letters of "smith".
  const NAMES = ['smith', 'smyth', 'smythe', 'smit', 'smid', 'smif', 'smiff', 'schmidt', 'smeeth', 'smeth', 'kenya', 'kenia', 'semis', 'mith', 'smitt', 'sneth', 'zmith'], CONVO_MS = 20000;
  S.convoUntil = 0;
  function lev(a, b) { const m = a.length, n = b.length, d = []; for (let i = 0; i <= m; i++) d[i] = [i]; for (let j = 1; j <= n; j++) d[0][j] = j;
    for (let i = 1; i <= m; i++) for (let j = 1; j <= n; j++) d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1)); return d[m][n]; }
  function wakeSplit(text) {
    const m = /^\W*(?:(?:hey|hi|okay|ok|yo)\W+)?([A-Za-z]{2,10})\b[\s,.!?:-]*/.exec(text); if (!m) return null;
    const w = m[1].toLowerCase();
    if (NAMES.indexOf(w) >= 0 || (w.length >= 4 && lev(w, 'smith') <= 1) || (w.length >= 5 && lev(w, 'smith') <= 2 && w.charAt(0) === 's')) return { rest: text.slice(m[0].length).trim() };
    return null;
  }
  try { S.voice = localStorage.getItem('hubVoiceName'); S.mute = localStorage.getItem('hubVoiceMute') === '1'; } catch (e) {}

  // A deadline covers the response body as well as connection setup. Cancelling a turn ignores late replies.
  async function request(u, b, raw, timeout, info) {
    const controller = new AbortController(); S.requests.add(controller);
    const timer = setTimeout(() => controller.abort(), timeout || 45000);
    try {
      const r = await fetch(u, { method: 'POST', signal: controller.signal,
        headers: { 'Content-Type': raw === 'audio' ? (b.type || 'audio/webm') : 'application/json' },
        body: raw === 'audio' ? b : JSON.stringify(b || {}) });
      if (!r.ok) throw new Error((await r.text()).slice(0, 140));
      if (info) info.h = { used: r.headers.get('X-Voice-Used') || '', fb: r.headers.get('X-Voice-Fallback') || '', cached: r.headers.get('X-Voice-Cached') || '' };
      return raw === 'speech' ? await r.arrayBuffer() : await r.json();
    } finally { clearTimeout(timer); S.requests.delete(controller); }
  }
  function saveSession(url) {
    try {
      if (url) sessionStorage.setItem(KEY, JSON.stringify({ on: S.on, history: S.history.slice(-2), target: url, until: Date.now() + 30000 }));
      else sessionStorage.removeItem(KEY);
    } catch (e) {}
  }
  function cancelTurn() {
    S.turn++; S.capture++; S.busy = false; S.carry = null;
    S.requests.forEach((c) => c.abort()); S.requests.clear();
    if (S.stop) S.stop(); S.speaking = false;
  }
  function ready() { setState(S.on ? 'listening' : 'breathing', S.on ? 'Listening…' : 'Ready'); }
  function layout() {
    $('voice').classList.toggle('compact', S.compact); $('voice').classList.toggle('expanded', S.expanded);
    $('v-size').textContent = S.compact ? 'EXPAND' : 'MINIMISE';
    $('v-history').textContent = S.expanded ? 'LATEST' : 'HISTORY';
    $('v-history').hidden = S.history.length <= 2;
    Array.from($('v-log').children).forEach((d, i, all) => { d.hidden = !S.expanded && i < all.length - 2; });
    $('v-log').scrollTop = $('v-log').scrollHeight;
  }
  function fresh() {
    cancelTurn(); S.pending = null; S.history = []; S.expanded = false; $('v-log').replaceChildren();
    showBtns(false); hint(''); saveSession(); layout(); ready();
  }
  function orb(state) { const c = document.querySelector('#voice canvas'); if (c && c._orb) c._orb.set(state); }
  function setState(orbState, text) {
    orb(orbState); $('v-state').textContent = text;
    talkBtns().forEach((b) => { b.classList.toggle('speaking', /Speaking|Thinking|Recognising|Doing|Working/.test(text)); });
    const stg = $('v-stage'); if (stg) stg.classList.toggle('speaking', /Speaking|Thinking|Recognising|Doing|Working/.test(text));
    const st = $('v-stop'); if (st) st.hidden = !(S.busy || S.speaking || /Thinking|Recognising|Doing|Speaking|Working/.test(text));
  }
  const talkBtns = () => document.querySelectorAll('[data-talk]');
  function paintOn() { talkBtns().forEach((b) => b.classList.toggle('on', S.on)); const stg = $('v-stage'); if (stg) stg.classList.toggle('on', S.on); $('v-mic').textContent = S.on ? 'STOP LISTENING' : 'START LISTENING'; $('v-mic').classList.toggle('stop', S.on); $('v-mic').classList.toggle('go', !S.on); }
  function hubSmithHeard() { talkBtns().forEach((b) => { b.classList.remove('heard'); void b.offsetWidth; b.classList.add('heard'); setTimeout(() => b.classList.remove('heard'), 2500); }); }
  function showBtns(confirm) { $('v-yes').hidden = !confirm; $('v-no').hidden = !confirm; }
  // everything said or noticed goes to the one LOG at the bottom of the dashboard (kept per tab in sessionStorage, so the landing page and every page share it)
  function hubLog(kind, text, err) {
    text = String(text || '').replace(/\s+/g, ' ').trim().slice(0, 400); if (!text) return;
    try {
      if (window.__hubLogAdd) { window.__hubLogAdd(kind, text, err); return; }
      const k = 'agenthub:log', a = JSON.parse(sessionStorage.getItem(k) || '[]');
      if (!(a[0] && a[0].t === text && a[0].kind === kind)) a.unshift({ at: Date.now(), kind, t: text, err: !!err });
      sessionStorage.setItem(k, JSON.stringify(a.slice(0, 80)));
    } catch (e) {}
  }
  // With the chat window closed (a plain click on TALK no longer opens it) a short note under the button says what happened: listening, stopped, or why not.
  let BUBBLE = null, BUBBLE_T = 0;
  function bubble(text, ms) {
    if (!$('voice').hidden) return;
    const btn = Array.prototype.find.call(talkBtns(), (b) => b.getBoundingClientRect().width > 0); if (!btn) return;
    if (!BUBBLE) { BUBBLE = document.createElement('div'); BUBBLE.className = 'v-bubble'; BUBBLE.setAttribute('role', 'status'); BUBBLE.onclick = () => { BUBBLE.hidden = true; open(false); }; document.body.appendChild(BUBBLE); }
    BUBBLE.textContent = text; BUBBLE.hidden = false;
    const r = btn.getBoundingClientRect(); BUBBLE.style.left = Math.max(8, Math.min(r.left, innerWidth - 336)) + 'px'; BUBBLE.style.top = (r.bottom + 8) + 'px';
    clearTimeout(BUBBLE_T); BUBBLE_T = setTimeout(() => { if (BUBBLE) BUBBLE.hidden = true; }, ms || 7000);
  }
  function hint(t) { $('v-hint').textContent = t || ''; $('v-hint').hidden = !t; if (t) { hubLog('hub', t); bubble(t, 9000); } }
  function log(role, text, tag) {
    const d = document.createElement('div'); d.className = 'v-msg ' + role; d.append(document.createTextNode(text)); if (tag) { const b = document.createElement('span'); b.className = 'v-tag'; b.textContent = tag; d.appendChild(b); } $('v-log').appendChild(d); $('v-log').scrollTop = $('v-log').scrollHeight;
    hubLog('chat', (role === 'you' ? 'You: ' : (WHO[S.who] || 'Smith') + ': ') + text);
    if (role === 'hub') bubble(text, Math.min(16000, 4500 + text.length * 60));
    if (role === 'you' || role === 'hub') { S.history.push({ role: role === 'you' ? 'user' : 'assistant', text }); if (S.history.length > 20) S.history.shift(); }
    layout();
  }
  const secureMic = () => !!(window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);

  // ---- sound. Phones only allow audio that was started by a tap, so the first tap unlocks one <audio> element and one AudioContext that every reply reuses.
  const SILENT = 'data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=';
  function unlockAudio() {
    try {
      if (!S.audio) { S.audio = new Audio(); S.audio.setAttribute('playsinline', ''); S.audio.src = SILENT; S.audio.play().catch(() => {}); }
      if (!S.actx) { const AC = window.AudioContext || window.webkitAudioContext; if (AC) S.actx = new AC(); }
      if (S.actx && S.actx.state === 'suspended') S.actx.resume().catch(() => {});
    } catch (e) {}
  }
  function pickBrowserVoice() {
    const vs = (window.speechSynthesis && speechSynthesis.getVoices()) || [];
    const score = (v) => (/natural|online/i.test(v.name) ? 40 : 0) + (/en-AU/i.test(v.lang) ? 22 : /en-GB/i.test(v.lang) ? 20 : /^en/i.test(v.lang) ? 8 : 0);
    return vs.slice().sort((a, b) => score(b) - score(a))[0] || null;
  }
  function speakBrowser(text) {
    return new Promise((res) => {
      try { const u = new SpeechSynthesisUtterance(text), v = pickBrowserVoice(); if (v) u.voice = v; u.rate = 0.98; u.onend = res; u.onerror = res; speechSynthesis.cancel(); speechSynthesis.speak(u); } catch (e) { res(); }
    });
  }
  // Smith's voice goes through the layered robotic effect (voice-fx.js) on its way to the speakers; 'clean' skips it.
  const route = (node, buf, o) => { const fx = o && o.fx !== undefined ? o.fx : S.fxNow, fxs = o && o.fxs !== undefined ? o.fxs : S.fxsNow; if (window.HubVoiceFx) HubVoiceFx.connect(S.actx, node, S.actx.destination, buf.duration, fx, fxs); else node.connect(S.actx.destination); };       // S.fxNow / S.fxsNow: this speaker's own robotic layer (unset for Smith: the one he already uses)
  // Shaped delivery. Microsoft's service gives one flat reading per request and rejects SSML, so character comes from how the line is cut: phrases at the commas, dashes and full stops, a slightly different
  // rate and pitch for each (a question lifts, a statement falls and slows), a word between *stars* leaned on (slower, lower, with a breath either side) and the pauses made here, between the pieces.
  // Where a sentence naturally parts: before a joining word, and in the middle of anything longer than five words.
  function breakWords(t) {
    const w = t.trim().split(/\s+/), out = []; let cur = [];
    const JOIN = /^(than|but|and|because|until|when|while|that|which|if|or|so|as|before|after|though|yet)$/i;
    const SV = /^(i|we|you|he|she|it|they)$/i, AUX = /^(am|are|is|was|were|will|have|had|can|could|would|shall|do|did)$/i;
    if (w.length >= 5 && SV.test(w[0]) && AUX.test(w[1])) { out.push(w[0] + ' ' + w[1]); w.splice(0, 2); }            // "I am | ..."
    w.forEach((x, i) => { if (cur.length >= 1 && JOIN.test(x)) { out.push(cur.join(' ')); cur = []; } cur.push(x); });
    if (cur.length) out.push(cur.join(' '));
    return out.flatMap((c) => { const k = c.split(' '); return k.length > 5 ? [k.slice(0, Math.ceil(k.length / 2)).join(' '), k.slice(Math.ceil(k.length / 2)).join(' ')] : [c]; });
  }
  function shape(text, d) {
    const sc = d.pauses || 1, pace = d.pace || 0, out = [];
    const GAP = { ',': 150, ';': 240, ':': 240, '\u2014': 320, '\u2026': 540, '.': 400, '?': 340, '!': 340 };
    const t = String(text).replace(/\.{3}/g, '\u2026').replace(/\s+--?\s+/g, ' \u2014 ');
    const re = /[^,;:.!?\u2026\u2014]+[,;:.!?\u2026\u2014]*/g; let m;
    while ((m = re.exec(t))) {
      const raw = m[0].trim(); if (!raw) continue;
      const end = raw.slice(-1), core = raw.replace(/[,;:.!?\u2026\u2014]+$/, ''), stop = /[.!?\u2026]/.test(end);
      let rate = pace, pitch = 0;
      if (end === '?') pitch = 5; else if (end === '.') { rate -= 4; pitch = -4; } else if (end === '\u2026') { rate -= 8; pitch = -5; }
      let bits = core.split(/(\*[^*]+\*)/).filter(Boolean);
      if (sc >= 1.5) bits = bits.flatMap((b) => (b.length > 2 && b[0] === '*') ? [b] : breakWords(b));     // LONG and DRAMATIC pauses also fall inside a sentence, at its natural joints
      bits.forEach((b, i) => {
        const hot = b.length > 2 && b[0] === '*', txt = (hot ? b.slice(1, -1) : b).trim(); if (!txt) return;
        const last = i === bits.length - 1;
        if (hot && out.length && !out[out.length - 1].gap) out[out.length - 1].gap = Math.round(110 * sc);
        out.push({ text: txt + (last && stop ? end : ''), rate: hot ? rate - 22 : rate, pitch: hot ? pitch - 6 : pitch, gap: hot ? Math.round(90 * sc) : (sc >= 1.5 && !last ? Math.round(240 * sc) : 0) });
      });
      if (out.length) out[out.length - 1].gap = Math.round((GAP[end] || 120) * sc);
    }
    return out.length ? out : [{ text: String(text), rate: 0, pitch: 0, gap: 0 }];
  }
  // Plays the reply a sentence at a time: the first sentence is made alone and starts playing while the next ones (up to three in flight) are being made,
  // so an answer starts after about the time of its first sentence, not of the whole answer. Resolves when it ends or when S.stop() is called
  // (talk-over, typing, STOP, or an answer arriving while a "working on it" line is still being said).
  function play(text, o) {                                                              // o (the VOICE TEST panel): {voice, agent, fx, fxs, info, fail} speak with those instead of the current speaker's
    return new Promise(async (resolve) => {
      let done = false, node = null, deadline = null, audioUrl = null, endPiece = null;
      const fin = () => { if (!done) { done = true; clearTimeout(deadline); if (audioUrl) URL.revokeObjectURL(audioUrl); S.stop = null; resolve(); } };
      S.stop = () => { try { if (S.audio) S.audio.pause(); } catch (e) {} try { if (node) node.stop(); } catch (e) {} try { speechSynthesis.cancel(); } catch (e) {} if (endPiece) endPiece(); fin(); };
      deadline = setTimeout(() => { if (!done && S.stop) S.stop(); }, 60000);
      const rec = (S.av && S.av[(o && o.agent) || S.who]) || {}, del = (o && o.delivery) || rec.delivery || {};
      const parts = del.on ? shape(text, del) : ((window.HubVoiceGate && HubVoiceGate.sentences(text)) || [String(text)]).map((t) => ({ text: t, rate: 0, pitch: 0, gap: 0 }));
      if (!parts.length) { fin(); return; }
      const get = (pc) => { const t0 = performance.now(), inf = {}; const r = request('/api/voice/speak', { text: pc.text, rate: pc.rate || undefined, pitch: pc.pitch || undefined, voice: (o && o.voice) || S.voice || undefined, agent: (o && o.agent) || S.who || undefined }, 'speech', 30000, inf).then((ab) => { if (o && o.info) o.info({ ms: Math.round(performance.now() - t0), h: inf.h || {}, bytes: ab.byteLength }); return ab; }); r.catch(() => {}); return r; };
      if (o && o.plan) o.plan(parts.length);
      const got = parts.map((t, i) => (i < 3 ? get(t) : null));
      // one piece of audio, to its end (or to a stop)
      async function piece(ab) {
        await new Promise(async (end) => {
          endPiece = end;
          try {
            if (S.actx) {
              try { await S.actx.resume(); const buf = await S.actx.decodeAudioData(ab.slice(0)); if (done) return end(); node = S.actx.createBufferSource(); node.buffer = buf; route(node, buf, o); node.onended = end; node.start(); return; }
              catch (e0) { node = null; }                                             // AudioContext refused or could not decode: use the <audio> element
            }
            const a = S.audio || (S.audio = new Audio()), url = URL.createObjectURL(new Blob([ab], { type: 'audio/mpeg' }));
            if (audioUrl) URL.revokeObjectURL(audioUrl);
            audioUrl = url; a.onended = end; a.onerror = end; a.src = url; await a.play();
          } catch (e1) {
            if (!S.actx) return end();
            try { await S.actx.resume(); const buf = await S.actx.decodeAudioData(ab.slice(0)); if (done) return end(); node = S.actx.createBufferSource(); node.buffer = buf; route(node, buf, o); node.onended = end; node.start(); } catch (e2) { end(); }
          }
        });
        endPiece = null;
      }
      let at = 0;
      try {
        for (; at < parts.length && !done; at++) {
          if (!got[at]) got[at] = get(parts[at]);
          if (at + 3 < parts.length && !got[at + 3]) got[at + 3] = get(parts[at + 3]);
          const ab = await got[at];
          if (done) return;
          await piece(ab);
          if (parts[at].gap && !done) await new Promise((r) => { const tm = setTimeout(() => { endPiece = null; r(); }, parts[at].gap); endPiece = () => { clearTimeout(tm); r(); }; });
        }
        fin();
      } catch (e) { if (!done) { if (o && o.fail) { o.fail(e); fin(); return; } hint('Smith\'s voice (edge-tts) did not answer' + (e && e.message ? ': ' + String(e.message).slice(0, 90) : '') + '. This is the browser voice for now.'); await speakBrowser(parts.slice(at).map((x) => x.text).join(' ')); fin(); } }
    });
  }

  // Words the hub itself just said, heard back through the speakers. Drops any sentence of the transcript
  // that is mostly the hub's last reply, so only what the person said is left.
  function dropEcho(text, said) {
    if (!said) return text;
    const stem = (w) => w.toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 4);
    const sw = new Set(said.split(/\s+/).map(stem).filter(Boolean));
    const keep = String(text).split(/(?<=[.!?])\s+/).filter((sent) => {
      const ws = sent.split(/\s+/).map(stem).filter(Boolean);
      if (!ws.length) return false;
      const inside = ws.filter((w) => sw.has(w)).length;
      return !(ws.length >= 2 && inside / ws.length >= 0.7);
    });
    return keep.join(' ').trim();
  }
  window.HubVoiceEcho = { drop: dropEcho };

  // ---- microphone
  async function ensureStream() {
    if (S.stream && S.stream.active) return true;
    try {
      const listen = S.listen, stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
      if (!S.on || listen !== S.listen) { stream.getTracks().forEach(t => t.stop()); return false; }
      S.stream = stream;
      const AC = window.AudioContext || window.webkitAudioContext; S.ctx = new AC(); S.an = S.ctx.createAnalyser(); S.an.fftSize = 1024; S.ctx.createMediaStreamSource(S.stream).connect(S.an);
      return true;
    } catch (e) { return false; }
  }
  function releaseStream() { try { if (S.stream) S.stream.getTracks().forEach((t) => t.stop()); if (S.ctx) S.ctx.close(); } catch (e) {} S.stream = S.ctx = S.an = null; }
  function mimeType() { for (const m of ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4']) { if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(m)) return m; } return ''; }
  function rms() { if (!S.an) return 0; S.an.getByteTimeDomainData(BUF); let s = 0; for (const b of BUF) { const v = (b - 128) / 128; s += v * v; } return Math.sqrt(s / BUF.length); }
  function makeRec() {
    const mt = mimeType(), mr = new MediaRecorder(S.stream, mt ? { mimeType: mt } : undefined), chunks = [];
    mr.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
    const done = new Promise((res) => { mr.onstop = res; }); mr.start();
    return { stop() { try { if (mr.state !== 'inactive') mr.stop(); } catch (e) {} return done; }, blob() { return new Blob(chunks, { type: mr.mimeType || 'audio/webm' }); } };
  }
  // resolves when an utterance has ended (1.4 s below the room's own level after a voice); true if speech was heard.
  // The level a voice must clear comes from voice-gate.js, learned from the room and kept between recordings.
  function untilUtteranceEnds(alreadySpoke, noSpeechMs) {
    return new Promise((resolve) => {
      const G = window.HubVoiceGate, gate = G ? G.make({ floor0: S.floor || G.defaults.floor0 }, alreadySpoke) : null;
      let spoke = !!alreadySpoke, quiet = 0; const t0 = performance.now(), capture = S.capture, listen = S.listen;
      const finish = (v) => { if (gate) S.floor = gate.floor(); resolve(v); };
      const tick = () => {
        if (!S.on || capture !== S.capture || listen !== S.listen) return finish(false);
        const r = rms(), now = performance.now();
        let ended = false;
        if (gate) { const g = gate.step(r, now); spoke = g.spoke; ended = g.ended; }
        else { if (r > 0.035) { spoke = true; quiet = 0; } else if (spoke && !quiet) quiet = now; ended = spoke && quiet && now - quiet > 1400; }
        if (ended || (spoke && now - t0 > 25000) || (!spoke && now - t0 > (noSpeechMs || 15000))) return finish(spoke);
        requestAnimationFrame(tick);
      };
      tick();
    });
  }
  // A sentence that stops on "and", "then", "open", a comma or "uh" is a pause, not an ending.
  // Wait a little longer for the rest and join it, up to three times, before anything is sent.
  const UNFINISHED = /(?:\b(?:and|then|so|but|or|to|the|a|an|my|of|in|on|with|for|play|open|launch|start|um+|uh+|er+|like|please)|[,…-])[\s.]*$/i;
  // The turn models (Silero VAD + Smart Turn) say whether this is speech and whether it is finished.
  // They can only make the hub wait longer or drop noise; the sentence-ending check above still applies.
  async function judgeTurn(blob, turn, reset) {
    try {
      const r = await fetch('/api/voice/turn', { method: 'POST', headers: { 'Content-Type': blob.type || 'audio/webm', 'X-Turn': turn, 'X-Reset': reset ? '1' : '0' }, body: blob });
      return r.ok ? await r.json() : null;
    } catch (e) { return null; }
  }
  async function transcribeWhole(blob, capture, listen) {
    const turn = 't' + Date.now().toString(36);
    const j0 = await judgeTurn(blob, turn, true);
    if (j0 && j0.model && j0.speech !== null && j0.speech < 0.08) return '';       // room noise, not speech
    let text = await transcribe(blob), j = j0;
    const unfinished = () => UNFINISHED.test(text) || (j && j.model && j.complete === false);
    for (let i = 0; i < 3 && unfinished() && S.on && listen === S.listen && capture === S.capture; i++) {
      setState('listening', 'Listening\u2026');
      const rec = makeRec(); const spoke = await untilUtteranceEnds(false, 3500); await rec.stop();
      if (!spoke) break;
      setState('working', 'Recognising\u2026');
      const seg = rec.blob();
      const [more, jn] = await Promise.all([transcribe(seg), judgeTurn(seg, turn, false)]);
      if (!more) break;
      j = jn;
      text = (text.replace(/[,\u2026\s-]+$/, '') + ' ' + more).trim();
    }
    return text;
  }
  async function recordUtterance() {
    const rec = makeRec(); orb('listening');
    const spoke = await untilUtteranceEnds(false); await rec.stop();
    return spoke ? rec.blob() : null;
  }
  async function transcribe(blob) {
    return ((await request('/api/voice/transcribe', blob, 'audio')).text || '').trim();
  }

  // ---- speaking, with talk-over: the mic keeps recording while the reply plays; if you start talking, the reply stops and what you say is used
  async function speak(text) {
    if (!text) return;
    if (S.mute) { hint('Sound is off, so that reply was not spoken. Tap SOUND OFF to turn it back on.'); return; }
    const turn = S.turn, spokeAt = performance.now();
    S.speaking = true; setState('composing', 'Speaking…');
    let rec = null, barged = false;
    // No listening while speaking: through speakers the microphone only hears the hub's own voice, which
    // came back as the person's next request. STOP, typing and YES / NO interrupt instead.
    S.lastSaid = text;
    if (rec) {
      let hi = 0, last = performance.now();
      const watch = () => { if (turn !== S.turn || !S.on || !S.speaking || barged) return; const now = performance.now(); const q = !!S.pending; hi = rms() > (q ? 0.04 : 0.07) ? hi + (now - last) : 0; last = now; if (hi > (q ? 160 : 350)) { barged = true; if (S.stop) S.stop(); return; } requestAnimationFrame(watch); };
      watch();
    }
    await play(text);
    S.lastSpokenEnd = Date.now();
    if (barged && performance.now() - spokeAt < 1500) hint('That reply was cut off almost at once: the mic heard noise and took it for you talking. If it keeps happening, use headphones or lower the volume.');
    if (turn !== S.turn) { if (rec) await rec.stop(); return; }
    S.speaking = false;
    if (rec) {
      if (barged) { setState('listening', 'Listening…'); const heard = await untilUtteranceEnds(true, 15000); await rec.stop(); if (heard && turn === S.turn && S.on) S.carry = rec.blob(); }
      else await rec.stop();
    }
  }

  function startLoop() {
    if (S.loop) return;
    const listen = S.listen;
    S.loop = loop(listen).catch((e) => { if (listen === S.listen) { S.on = false; hint('Listening stopped. Please try START LISTENING again.'); } })
      .finally(() => { releaseStream(); S.loop = null; if (S.on) startLoop(); else { ready(); paintOn(); } });
  }
  async function loop(listen) {
    setState('breathing', 'Starting…');
    if (!secureMic()) {
      S.on = false; paintOn(); setState('breathing', 'No microphone here');
      let url = ''; try { url = (await (await fetch('/api/phone-https')).json()).url || ''; } catch (e) {}
      hint("This page is on plain http, so the browser won't allow the microphone here. " + (url ? 'Open the hub at ' + url + ' instead, or use' : 'Use') + " your keyboard's mic key to dictate into the box below."); return;
    }
    if (!(await ensureStream())) { S.on = false; paintOn(); hint('The microphone is blocked for this site. Allow it in the browser, or type below.'); setState('breathing', 'Microphone blocked'); return; }
    if (S.whisper === null) { try { S.whisper = (await (await fetch('/api/voice/status')).json()).whisper; } catch (e) { S.whisper = false; } }
    if (!S.whisper) { releaseStream(); S.on = false; paintOn(); hint('Local speech recognition is not ready on the hub PC. Type below.'); setState('breathing', 'No local Whisper'); return; }
    hint('');
    while (S.on && listen === S.listen) {
      if (S.speaking) { await new Promise((r) => setTimeout(r, 60)); continue; }          // not while the hub is talking (it would hear itself); while it is working it keeps listening
      const capture = S.capture;
      let blob = S.carry; S.carry = null;
      if (!blob) { setState('listening', 'Listening…'); try { blob = await recordUtterance(); } catch (e) { blob = null; } }
      if (!S.on || listen !== S.listen) break;
      if (capture !== S.capture) continue;
      if (!blob) continue;
      setState('working', 'Recognising…');
      let text = ''; try { text = await transcribeWhole(blob, capture, listen); } catch (e) { if (capture === S.capture && S.on) { setState('breathing', 'Recognition failed'); hint('Please try again, or type your request.'); await new Promise((r) => setTimeout(r, 1500)); } continue; }
      if (!S.on || listen !== S.listen || capture !== S.capture) continue;
      if (Date.now() - (S.lastSpokenEnd || 0) < 4000) text = dropEcho(text, S.lastSaid);
      if (text.replace(/[^\w]/g, '').length < 2) continue;
      // Listening all the time, answering only to his name: no name and no conversation going on, and it is not an answer to a question he asked, means it was not for him.
      const w = wakeSplit(text), inTalk = Date.now() < S.convoUntil;
      if (!w && !inTalk && !S.pending) continue;
      if (w) { text = w.rest; hubSmithHeard(); if (text.replace(/[^\w]/g, '').length < 2) { log('you', 'Smith'); S.convoUntil = Date.now() + CONVO_MS; speak('Yes?'); continue; } }
      S.convoUntil = Date.now() + CONVO_MS;
      hint(''); handle(text);                                  // not awaited: the next thing you say is heard while this one is still being worked on
    }
    // startLoop owns cleanup, so a quick stop/start cannot leave two recorders running.
  }

  // ---- talking to the assistant
  const YES = /^(yes|yeah|yep|yup|sure|okay|ok|go ahead|do it|confirm|please do|correct)\b/i, NO = /^(no|nope|cancel|stop|don'?t|do not|never mind|leave it)\b/i;
  // 'stop' and its kin always cut in. While a task on the PC is running, any other new request waits its turn instead of cutting the task off.
  const STOP = /^(?:ok(?:ay)?[,. ]*)?(?:please[, ]+)?(?:stop|cancel|abort|never ?mind|forget it|that'?s enough|enough|hold on|wait)\b[\s.!]*(?:that|it|this|now|please)?[\s.!]*$/i;
  function stopNow() { cancelTurn(); S.pending = null; S.queued = null; S.acting = false; showBtns(false); fetch('/api/voice/cancel', { method: 'POST' }).catch(() => {}); log('hub', 'Stopped.'); ready(); }
  async function handle(text) {
    if (S.busy && STOP.test(String(text).trim())) { log('you', text); stopNow(); return; }
    if (S.busy && S.acting) { S.queued = text; log('you', text); log('hub', 'Noted. I will do that as soon as this is finished; say stop to cancel this one.'); return; }
    cancelTurn(); const turn = S.turn; S.busy = true;
    try { await answer(text, turn); }
    catch (e) { if (turn === S.turn) { log('hub', e.name === 'AbortError' ? 'That took too long. Please try again.' : 'I could not complete that request. Please try again.'); hint(String(e.message || e).slice(0, 140)); } }
    finally { if (turn === S.turn) { S.convoUntil = Date.now() + CONVO_MS; S.busy = false; S.acting = false; if (S.pending) setState('breathing', 'Waiting for confirmation'); else ready(); const q = S.queued; if (q && !S.pending) { S.queued = null; setTimeout(() => handle(q), 0); } } }
  }
  async function answer(text, turn) {
    log('you', text);
    if (S.pending) {
      const p = S.pending;
      if (YES.test(text)) { S.pending = null; showBtns(false); return execute(p, turn); }
      if (NO.test(text)) { S.pending = null; showBtns(false); log('hub', 'Okay, cancelled. Nothing was changed.'); return speak('Okay, cancelled.'); }
      S.pending = null; showBtns(false);                    // a new topic must not leave an old action waiting for a later yes
    }
    setState('solving', 'Thinking…');
    const ctx = (window.__voiceCtx && window.__voiceCtx()) || {};
    const board = window.__hubBoard && window.__hubBoard.scene();            // on the dashboard Talk sees its blocks and may move them
    const r = await request('/api/voice/chat', { text, history: S.history.slice(-9, -1), mission: ctx.mission || S.mission || null, scene: board || undefined, speaker: S.who });
    if (turn !== S.turn) return;
    if (r.transition) log('hub', r.transition.line);                                                         // the one who is leaving says so, under their own name, before the change
    if (r.speaker && r.speaker !== S.who && window.__hubTalkWho) window.__hubTalkWho(r.speaker, true);          // you named another agent: the conversation is theirs from here
    if (r.mission) S.mission = r.mission;
    const serverResult = r.action && !r.confirm && !r.url;          // its own result is the answer: do not also say the model's sentence
    if (!serverResult) log('hub', r.say);
    if (r.ui && board && window.__hubBoard.applyUi(r.ui)) { S.compact = true; S.expanded = false; layout(); }   // a panel asked for, tidy, fit, a mouse scheme: done on the board itself
    if (r.action && r.confirm) { S.pending = r; showBtns(true); setState('breathing', 'Waiting for your yes'); await speak(r.say); return; }
    if (serverResult) return execute(r, turn);
    await speak((r.transition ? r.transition.line + ' ' : '') + r.say);
    if (turn !== S.turn || S.carry) return;                       // you talked over the reply: handle what you said first
    if (r.action) await execute(r, turn);
  }
  function navigate(url) {
    if (window.__hubBoard && window.__hubBoard.open(url)) { S.compact = true; S.expanded = false; layout(); return; }   // on the dashboard a Hub page opens as a block on it, not as the old standalone page
    if (location.pathname + location.search !== url) { saveSession(url); location.href = url; }
    else { S.compact = true; S.expanded = false; layout(); }
  }
  async function execute(r, turn) {
    if (turn !== S.turn) return;
    if (r.url) { navigate(r.url); return; }
    setState('working', 'Doing it…');
    // A slow action says one short line after 3 s, so a long task does not read as a crash; quick ones stay silent, and the answer is never held up by it.
    const line = window.HubVoiceGate ? window.HubVoiceGate.workingLine(r.action.id) : '';
    let said = null; const nudge = line && !S.mute ? setTimeout(() => { if (turn === S.turn) said = speak(line); }, 3000) : null;
    let j; S.acting = true; try { j = await request('/api/voice/act', { id: r.action.id, args: r.action.args }, null, 180000); } finally { S.acting = false; if (nudge) clearTimeout(nudge); }
    if (said) { if (S.stop) S.stop(); await said; }        // the answer never waits for the working line: a line still being made or said is dropped
    if (turn !== S.turn) return;
    if (j.handoff) { S.mission = j.mission || S.mission; if (window.__hubTalkWho) window.__hubTalkWho(j.handoff, true); }      // Smith started a mission: the Orchestrator takes over the conversation
    log('hub', j.say, j.routine && j.routine.tag); if (j.detail) log('hub', j.detail); recPaint();
    // The question's YES / NO appear before the sentence is spoken, not after: a long
    // spoken answer used to leave the person with a question and nothing to press.
    if (j.action && j.confirm) { S.pending = j; showBtns(true); setState('breathing', 'Waiting for your yes'); }
    await speak(j.say);
    if (turn !== S.turn) return;
    // An action is allowed to come back with a question. Opening an app can only
    // do half of "open Apple Music and play the ADHD playlist", and the right
    // answer to the other half is to ask - which is impossible if a result can
    // only ever be a statement. Reuses the same pending machinery as a confirm.
    if (j.action && j.confirm) { S.pending = j; showBtns(true); setState('breathing', 'Waiting for your yes'); return; }
    if (!S.carry && j.url) navigate(j.url);
  }

  // ---- recording, shown where you already are
  // The hub used to answer "record it, then press STOP and SAVE on this page"
  // and navigate to Setup tools, where those controls are inside one section of
  // a long page. So the strip lives in this panel instead, and the reply no
  // longer moves you anywhere.
  let RECPOLL = null;
  async function recPaint() {
    let st = null;
    try { st = await (await fetch('/api/pc/record')).json(); } catch (e) { st = null; }
    const box = $('v-rec');
    if (!st || !st.available || (!st.running && !st.exists)) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    const n = (st.steps || []).length;
    $('v-rec-state').textContent = st.running
      ? `RECORDING — ${n} step${n === 1 ? '' : 's'}`
      : (n ? `STOPPED — ${n} step${n === 1 ? '' : 's'}, name it and save`
             : 'STOPPED — nothing was captured. Discard it and try again.');
    $('v-rec-stop').hidden = !st.running;
    $('v-rec-save').hidden = !!st.running || !n;
    $('v-rec-name').hidden = !!st.running || !n;
    S.recSteps = n;
  }
  async function recSend(path, body) {
    try {
      const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                   body: JSON.stringify(body || {}) });
      if (!r.ok) { hint(await r.text()); return null; }
      return await r.json();
    } catch (e) { hint(String(e.message || e)); return null; }
  }

  // ---- open / close / wiring
  function open(autoStart) {
    $('voice').hidden = false; if (BUBBLE) BUBBLE.hidden = true;
    if (window.ThinkingOrbs) window.ThinkingOrbs.mountAll($('voice'), '#00e676');
    paintOn(); layout(); recPaint();
    if (!RECPOLL) RECPOLL = setInterval(recPaint, 1500);
    if (autoStart && !S.on) { S.on = true; paintOn(); startLoop(); }
  }
  function close() { if (S.busy || S.acting || S.speaking || S.pending) stopNow(); S.on = false; S.listen++; releaseStream(); fresh(); paintOn(); $('voice').hidden = true; if (RECPOLL) { clearInterval(RECPOLL); RECPOLL = null; } }
  function toggle() { unlockAudio(); if (S.on) { S.on = false; S.listen++; cancelTurn(); S.pending = null; showBtns(false); saveSession(); paintOn(); ready(); } else { S.on = true; paintOn(); startLoop(); } }

  function applyAgentVoice(w) {                                                          // the speaker you are talking to: its saved voice and robotic layer become what replies use
    if (!S.voices) return;
    const r = (S.av && S.av[w]) || {}; let v = r.voice;
    if (w === 'smith' && !v) { try { v = localStorage.getItem('hubVoiceName'); } catch (e) {} }
    if (!v || !S.voices.some((x) => x.id === v)) v = S.defVoice;
    S.voice = v; S.fxNow = r.fx || undefined; S.fxsNow = r.fxs || undefined;
  }
  // VOICE TEST panel: pick an agent, a voice and a robotic layer, type any text, SPEAK it; only SET AS DEFAULT saves it (for that agent alone).
  const L = { who: 'smith', voice: null, fx: 'off', fxs: 'blend', rec: {} };
  const labSt = (t, bad) => { const e = $('v-lab-st'); if (e) { e.textContent = t || ''; e.classList.toggle('bad', !!bad); } };
  function labLoad(w) {                                                                  // show this agent's saved voice in the three boxes
    L.who = w; const r = (S.av && S.av[w]) || {};
    L.voice = r.voice && S.voices.some((x) => x.id === r.voice) ? r.voice : S.defVoice;
    L.fx = r.fx || (window.HubVoiceFx ? HubVoiceFx.mode() : 'off'); L.fxs = r.fxs || (window.HubVoiceFx ? HubVoiceFx.style() : 'blend');
    $('v-voice').value = L.voice; $('v-fx').value = L.fx; $('v-fxs').value = L.fxs;
    document.querySelectorAll('#v-lab-who [data-lab]').forEach((b) => { b.classList.toggle('on', b.dataset.lab === w); b.setAttribute('aria-pressed', String(b.dataset.lab === w)); });
    const rec = L.rec[w]; $('v-lab-note').textContent = rec ? rec.note : '';
    const t = $('v-lab-text'); if (t) t.value = r.line || '';                                 // the line typed for this agent stays with this agent
    const dl = r.delivery || {}; $('v-del-on').checked = !!dl.on; $('v-del-pace').value = String(dl.pace || 0); $('v-del-pauses').value = String(dl.pauses || 1);
    $('v-lab-save').textContent = 'SET AS ' + (WHO[w] || 'SMITH').toUpperCase() + "'S VOICE"; labSt('');
  }
  const pulseSet = (on) => { const st = $('v-stage'); if (st) st.classList.toggle('speaking', on); talkBtns().forEach((b) => b.classList.toggle('speaking', on)); };
  const labDelivery = () => ({ on: $('v-del-on').checked, pace: Number($('v-del-pace').value), pauses: Number($('v-del-pauses').value) });
  let lineT = 0;
  function labSaveLine() {                                                                   // typing is saved for the agent shown, a moment after you stop
    clearTimeout(lineT); const w = L.who, line = $('v-lab-text').value;
    lineT = setTimeout(() => { fetch('/api/voice/agent-voice', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ agent: w, line }) }).then((r) => r.json()).then((j) => { if (j.agents) { S.av = j.agents; } }).catch(() => {}); }, 500);
  }
  async function labSpeak() {
    unlockAudio(); const text = ($('v-lab-text').value || '').trim(); if (!text) { labSt('Type something to hear.', true); return; }
    if (S.stop) S.stop(); const t0 = performance.now(); let info = null, failed = null, phrases = 0; pulseSet(true);
    const btn = $('v-test'); btn.disabled = true; btn.textContent = 'MAKING…';
    const tick = setInterval(() => { if (!info) labSt('Making the audio… ' + ((performance.now() - t0) / 1000).toFixed(0) + ' s'); }, 500); labSt('Making the audio…');
    await play(text, { voice: $('v-voice').value, agent: L.who, delivery: labDelivery(), fx: $('v-fx').value, fxs: $('v-fxs').value, fail: (e) => { failed = e; }, plan: (n) => { phrases = n; }, info: (i) => { if (info) return; info = i;
      const nm = ((S.voices.find((x) => x.id === $('v-voice').value) || {}).name || '').split(' · ')[0];
      labSt(i.h.fb ? 'That voice did not answer, so ' + i.h.used + ' spoke instead.' : (i.h.cached ? 'Played from memory. ' : 'Made in ' + (i.ms / 1000).toFixed(1) + ' s. ') + (phrases > 1 ? phrases + ' phrases, first one shown. ' : '') + nm + (i.h.used ? ' (' + i.h.used + ')' : ''), !!i.h.fb); } });
    clearInterval(tick); btn.disabled = false; btn.textContent = 'SPEAK'; pulseSet(false);
    if (failed) labSt('No audio: ' + String((failed && failed.message) || failed).slice(0, 120), true);
  }
  async function labSave(reset) {
    try {
      const body = reset ? { agent: L.who, reset: true } : { agent: L.who, voice: $('v-voice').value, fx: $('v-fx').value, fxs: $('v-fxs').value, delivery: labDelivery(), line: $('v-lab-text').value };
      const r = await fetch('/api/voice/agent-voice', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      if (!r.ok) { labSt('Not saved: ' + (await r.text()).slice(0, 100), true); return; }
      S.av = (await r.json()).agents || S.av;
      if (L.who === 'smith' && window.HubVoiceFx) { const a = S.av.smith || {}; if (a.fx) HubVoiceFx.set(a.fx); if (a.fxs) HubVoiceFx.setStyle(a.fxs); try { localStorage.setItem('hubVoiceName', a.voice); } catch (e) {} }
      applyAgentVoice(S.who || 'smith'); const w = L.who; labLoad(w); labSt(reset ? (WHO[w] + ' is back to the built-in voice.') : (WHO[w] + ' will speak with this voice from now on.'));
    } catch (e) { labSt('Not saved: ' + String(e.message || e), true); }
  }
  function labRecommended() { const r = L.rec[L.who]; if (!r) return; $('v-voice').value = r.voice; $('v-fx').value = r.fx; $('v-fxs').value = r.fxs; labSt('Recommended filled in. SPEAK to hear it, SET AS DEFAULT to keep it.'); }
  async function fillVoices() {
    try {
      const j = await (await fetch('/api/voice/voices')).json(), sel = $('v-voice');
      const cat = j.catalog || [], opt = (id, t) => `<option value="${id}">${t}</option>`;
      const by = {}; cat.forEach((v) => { (by[v.lang] = by[v.lang] || []).push(v); });
      const langs = Object.keys(by).sort((x, y) => (/^English/.test(y) ? 1 : 0) - (/^English/.test(x) ? 1 : 0) || x.localeCompare(y));
      const kok = j.kokoro || [];
      sel.innerHTML = (kok.length ? '<optgroup label="On this PC (Kokoro: no internet, about a second a sentence)">' + kok.map((v) => opt(v.id, v.name)).join('') + '</optgroup>' : '') + '<optgroup label="Tuned for the characters">' + j.voices.map((v) => opt(v.id, v.name)).join('') + '</optgroup>' +
        langs.map((l) => '<optgroup label="' + (/^English/.test(l) ? l : l + ' (reads English with an accent)') + '">' + by[l].map((v) => opt(v.id, v.n + ' \u00b7 ' + v.g)).join('') + '</optgroup>').join('');
      j.voices = j.voices.concat(kok, cat.map((v) => ({ id: v.id, name: v.n })));
      if (Object.values(j.agents || {}).some((a) => String(a.voice || '').startsWith('k:'))) fetch('/api/voice/warm', { method: 'POST' }).catch(() => {});
      S.voices = j.voices; S.av = j.agents || {}; S.defVoice = j.default; L.rec = j.recommended || {};
      const fx = $('v-fx'), fxs = $('v-fxs');
      if (!(fx && window.HubVoiceFx)) { if (fx) fx.hidden = true; if (fxs) fxs.hidden = true; }
      applyAgentVoice(S.who || 'smith'); labLoad(L.who);
    } catch (e) { const b = $('v-labbtn'); if (b) b.hidden = true; }
  }
  const paintToggles = () => { $('v-mute').textContent = S.mute ? 'SOUND OFF' : 'SOUND ON'; };

  document.addEventListener('DOMContentLoaded', () => {
    // TALK: a plain click turns listening on or off without putting a window up; Alt-click, the wheel button or a right click opens or closes the chat window.
    const talkTarget = (e) => (e.target && e.target.closest ? e.target.closest('[data-talk]') : null);
    const chatToggle = () => { unlockAudio(); $('voice').hidden ? open(false) : close(); };
    // Touch has no Alt/middle click: hold TALK to type, without starting capture.
    let talkHold=0,talkPress=null,heldTalk=null,skipTalkUntil=0;
    const clearTalkHold=()=>{clearTimeout(talkHold);talkHold=0;talkPress=null;};
    document.addEventListener('pointerdown',e=>{const b=talkTarget(e);if(e.pointerType!=='touch'||!b)return;clearTalkHold();talkPress={x:e.clientX,y:e.clientY};talkHold=setTimeout(()=>{heldTalk=b;skipTalkUntil=Date.now()+1200;chatToggle();},550);},true);
    document.addEventListener('pointermove',e=>{if(talkPress&&Math.hypot(e.clientX-talkPress.x,e.clientY-talkPress.y)>8)clearTalkHold();},true);
    ['pointerup','pointercancel'].forEach(t=>document.addEventListener(t,clearTalkHold,true));
    addEventListener('pagehide',clearTalkHold);
    document.addEventListener('click', (e) => { if (!talkTarget(e)) return;if(talkTarget(e)===heldTalk&&Date.now()<skipTalkUntil){e.preventDefault();e.stopImmediatePropagation();return;} e.preventDefault(); e.stopPropagation(); if (e.altKey) chatToggle(); else { unlockAudio(); toggle(); hubLog('hub', S.on ? 'Listening on' : 'Listening off'); bubble(S.on ? 'Listening. Speak now. Click TALK again to stop; Alt-click opens the chat.' : 'Stopped listening.', S.on ? 4500 : 2200); } }, true);
    document.addEventListener('auxclick', (e) => { if (!talkTarget(e) || e.button !== 1) return; e.preventDefault(); e.stopPropagation(); chatToggle(); }, true);
    document.addEventListener('mousedown', (e) => { if (talkTarget(e) && e.button === 1) e.preventDefault(); }, true);
    document.addEventListener('contextmenu', (e) => { if (!talkTarget(e)) return; e.preventDefault(); e.stopPropagation(); if(talkTarget(e)===heldTalk&&Date.now()<skipTalkUntil)return;chatToggle(); }, true);
    talkBtns().forEach((b) => { b.title = 'Talk to the Hub\nAlt-click or touch and hold to open chat'; });
    $('v-close').onclick = close; $('v-mic').onclick = toggle;
    $('v-size').onclick = () => { S.compact = !S.compact; layout(); };
    $('v-history').onclick = () => { S.expanded = !S.expanded; layout(); };
    // WHO: the four core agents. Smith is the front door; a mission he starts hands the conversation to the Orchestrator; you can also pick anyone or name them in a sentence.
    // The pictures: Smith's old art on the Talk button, his new outline in the Talk window, the others as they are. A second, glowing copy of each lies over it and only its opacity moves.
    const ICON = (w) => w === 'smith' ? '/smith-icon.png' : '/static/agent-icons/' + w + '.png';
    const LIT = (w) => w === 'smith' ? '/static/agent-icons/lit/smith-classic.png' : '/static/agent-icons/lit/' + w + '.png';
    function paintButton(img, w) {
      img.src = ICON(w); let lit = img.parentNode.querySelector('img.lit');
      if (!lit) { lit = document.createElement('img'); lit.className = 'lit'; lit.alt = ''; lit.draggable = false; img.parentNode.appendChild(lit); }
      lit.src = LIT(w);
    }
    function paintStage(w) {
      const f = $('v-face'), l = $('v-face-lit'); if (!f) return;
      f.src = w === 'smith' ? '/static/agent-icons/smith-line.png' : ICON(w); f.alt = WHO[w];
      if (l) l.src = w === 'smith' ? '/static/agent-icons/lit/smith-line.png' : LIT(w);
    }
    function setWho(w, quiet) {
      if (!WHO[w]) w = 'smith'; S.who = w; try { sessionStorage.setItem('hubTalkWho', w); } catch (e) {}
      document.querySelectorAll('#v-who [data-who]').forEach((b) => { b.classList.toggle('on', b.dataset.who === w); b.setAttribute('aria-pressed', String(b.dataset.who === w)); });
      $('v-in').placeholder = w === 'smith' ? 'Type, or dictate with your keyboard' : 'Talking to ' + WHO[w] + '. Type, or dictate with your keyboard';
      const face = $('v-face'), nm = $('v-name'), role = $('v-role'), stage = $('v-stage');
      if (face && nm && stage && nm.textContent !== WHO[w].toUpperCase()) {                  // the picture and name change with a short cross-fade: the new speaker arrives, the old one leaves
        stage.classList.add('swap');
        setTimeout(() => { paintStage(w); face.alt = WHO[w]; nm.textContent = WHO[w].toUpperCase(); role.textContent = ROLE[w]; stage.dataset.who = w; stage.classList.remove('swap'); }, 220);
      } else if (face && nm && stage && !face.getAttribute('src')) { paintStage(w); nm.textContent = WHO[w].toUpperCase(); role.textContent = ROLE[w]; stage.dataset.who = w; }
      document.querySelectorAll('.talk-btn img').forEach((i) => {                          // the Talk button on the board wears the face of whoever you are talking to; Smith's own is put back for Smith
        paintButton(i, w);                                                                // the whole bust, as it always was; a glowing copy fades over it
      });
      applyAgentVoice(w);
      if (!quiet && $('v-lab').hidden) { try { $('v-in').focus({ preventScroll: true }); } catch (e) {} }
    }
    // PRESET of the speaker: chosen here or on the Agency page, saved at once.
    let PRE = null;
    async function paintPreset() {
      const sel = $('v-preset'); if (!sel) return;
      try { if (!PRE) PRE = await (await fetch('/api/agents/presets', { cache: 'no-store' })).json(); } catch (e) { return; }
      const cur = (PRE.choices || {})[S.who] || '';
      sel.replaceChildren(...[['', 'Own settings'], ...Object.entries(PRE.presets).map(([k, v]) => [k, k[0].toUpperCase() + k.slice(1) + ' - ' + v.about]), ['tally', 'Let the tally choose']].map(([v, t]) => { const o = document.createElement('option'); o.value = v; o.textContent = t; o.selected = v === cur; return o; }));
      sel.onchange = async () => { try { await fetch('/api/agents/' + S.who + '/preset', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ preset: sel.value }) }); PRE.choices[S.who] = sel.value; } catch (e) {} };
    }
    window.__hubTalkWho = (w, q) => { setWho(w, q); paintPreset(); };
    document.querySelectorAll('#v-who [data-who]').forEach((b) => { b.onclick = () => window.__hubTalkWho(b.dataset.who); });
    document.querySelectorAll('#v-who [data-who]').forEach((b) => { b.onclick = () => setWho(b.dataset.who); });
    try { setWho(sessionStorage.getItem('hubTalkWho') || 'smith', true); } catch (e) { setWho('smith', true); }
    paintPreset();
    $('v-new').onclick = fresh;
    $('v-stop').onclick = stopNow;
    $('v-cancel').onclick = () => { cancelTurn(); S.pending = null; showBtns(false); hint('Reply stopped. An action already sent may still finish; check its status before retrying.'); ready(); };
    $('v-mute').onclick = () => { unlockAudio(); S.mute = !S.mute; if (S.mute && S.stop) S.stop(); try { localStorage.setItem('hubVoiceMute', S.mute ? '1' : '0'); } catch (e) {} paintToggles(); };
    paintToggles();
    $('v-rec-stop').onclick = async () => {
      const st = await recSend('/api/pc/record/stop');
      if (st && st.named && (st.steps || []).length) {
        const got = await recSend('/api/pc/record/save', {});
        if (got) log('hub', `Saved "${got.title}". Say "call it ..." to rename.`);
      }
      recPaint();
    };
    $('v-rec-drop').onclick = async () => {
      if (S.recSteps > 0 && !confirm('Throw away this recording and its ' + S.recSteps + ' steps?')) return;
      await recSend('/api/pc/record/discard'); recPaint();
    };
    $('v-rec-save').onclick = async () => {
      const name = $('v-rec-name').value.trim();
      if (!name) { hint('Give the routine a name first.'); $('v-rec-name').focus(); return; }
      const got = await recSend('/api/pc/record/save', { intent: name, title: name });
      if (got) { log('hub', `Saved "${name}". It is listed ready to be wired in as a button.`); $('v-rec-name').value = ''; }
      recPaint();
    };
    $('v-yes').onclick = () => { unlockAudio(); if (S.pending) handle('Yes'); };
    $('v-no').onclick = () => { if (S.pending) handle('No'); };
    const send = () => { unlockAudio(); const v = $('v-in').value.trim(); if (v) { $('v-in').value = ''; if (S.stop) S.stop(); handle(v); } };
    // TEST VOICE: say what is typed in the box (or a sample line) with the voice and robotic layer chosen above for the agent you are talking to; nothing is sent to anyone
    $('v-test').onclick = labSpeak; $('v-lab-save').onclick = () => labSave(false); $('v-lab-reset').onclick = () => labSave(true); $('v-lab-rec').onclick = labRecommended;
    $('v-lab-text').oninput = labSaveLine;
    $('v-lab-text').onkeydown = (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); labSpeak(); } };
    document.querySelectorAll('#v-lab-who [data-lab]').forEach((b) => { b.onclick = () => { if (S.voices) labLoad(b.dataset.lab); }; });
    $('v-labbtn').onclick = () => { const l = $('v-lab'); l.hidden = !l.hidden; $('v-labbtn').setAttribute('aria-expanded', String(!l.hidden)); $('v-labbtn').classList.toggle('on', !l.hidden); if (!l.hidden && S.voices) labLoad(L.who); };
    $('v-go').onclick = send; $('v-in').onkeydown = (e) => { if (e.key === 'Enter') send(); };
    fillVoices();
    try {
      const s = JSON.parse(sessionStorage.getItem(KEY) || 'null'); saveSession();
      if (s && s.target === location.pathname + location.search && s.until > Date.now()) {
        S.history = (s.history || []).slice(-2); S.history.forEach((h) => { const d = document.createElement('div'); d.className = 'v-msg ' + (h.role === 'user' ? 'you' : 'hub'); d.textContent = h.text; $('v-log').appendChild(d); });
        S.compact = true; open(!!s.on);
      }
    } catch (e) {}
    layout();
  });

  // the Missions input bar (and anything else) can hand a typed question to the same conversation
  window.HubVoice = { stopAll() { stopNow(); }, openChat() { open(false); }, toggleListening() { unlockAudio(); toggle(); }, listening() { return !!S.on; }, state() { return { busy: S.busy, acting: S.acting, queued: S.queued || null, speaking: S.speaking }; }, ask(text) { unlockAudio(); open(false); return handle(String(text || '')); }, open, close,
    contextChanged(id) { if (S.context !== id) { S.context = id; fresh(); } S.compact = true; layout(); } };
})();


