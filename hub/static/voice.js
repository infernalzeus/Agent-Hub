// The conversation popover: always-on listening until stopped, and you can talk over the reply. Microphone = the device whose browser this is
// (phone or PC); the audio goes to the hub PC for local Whisper (POST /api/voice/transcribe), the text to the assistant (POST /api/voice/chat),
// the reply comes back as speech (POST /api/voice/speak, Microsoft neural voice; the browser's own voice is the fallback).
(function () {
  const $ = (id) => document.getElementById(id);
  const KEY = 'hubVoiceSession';
  const S = { on: false, speaking: false, pending: null, history: [], stream: null, ctx: null, an: null, whisper: null, voice: null, voiceboxProfile: null, voiceboxOnline: false, mode: 'tts', mute: false,
              audio: null, actx: null, stop: null, carry: null, turn: 0, capture: 0, listen: 0, busy: false,
              requests: new Set(), loop: null, compact: location.pathname === '/missions', expanded: false, context: null };
  const BUF = new Uint8Array(1024);
  try { S.voice = localStorage.getItem('hubVoiceName'); S.mode = 'tts'; S.mute = localStorage.getItem('hubVoiceMute') === '1'; } catch (e) {}

  // A deadline covers the response body as well as connection setup. Cancelling a turn ignores late replies.
  async function request(u, b, raw, timeout) {
    const controller = new AbortController(); S.requests.add(controller);
    const timer = setTimeout(() => controller.abort(), timeout || 45000);
    try {
      const r = await fetch(u, { method: 'POST', signal: controller.signal,
        headers: { 'Content-Type': raw === 'audio' ? (b.type || 'audio/webm') : 'application/json' },
        body: raw === 'audio' ? b : JSON.stringify(b || {}) });
      if (!r.ok) throw new Error((await r.text()).slice(0, 140));
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
  function setState(orbState, text) { orb(orbState); $('v-state').textContent = text; }
  const talkBtns = () => document.querySelectorAll('[data-talk]');
  function paintOn() { talkBtns().forEach((b) => b.classList.toggle('on', S.on)); $('v-mic').textContent = S.on ? 'STOP LISTENING' : 'START LISTENING'; $('v-mic').classList.toggle('stop', S.on); $('v-mic').classList.toggle('go', !S.on); }
  function showBtns(confirm) { $('v-yes').hidden = !confirm; $('v-no').hidden = !confirm; }
  function hint(t) { $('v-hint').textContent = t || ''; $('v-hint').hidden = !t; }
  function log(role, text, tag) {
    const d = document.createElement('div'); d.className = 'v-msg ' + role; d.append(document.createTextNode(text)); if (tag) { const b = document.createElement('span'); b.className = 'v-tag'; b.textContent = tag; d.appendChild(b); } $('v-log').appendChild(d); $('v-log').scrollTop = $('v-log').scrollHeight;
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
  // plays the reply; resolves when it ends or when S.stop() is called (talk-over, typing, STOP)
  function play(text) {
    return new Promise(async (resolve) => {
      let done = false, node = null, deadline = null, audioUrl = null;
      const fin = () => { if (!done) { done = true; clearTimeout(deadline); if (audioUrl) URL.revokeObjectURL(audioUrl); S.stop = null; resolve(); } };
      S.stop = () => { try { if (S.audio) S.audio.pause(); } catch (e) {} try { if (node) node.stop(); } catch (e) {} try { speechSynthesis.cancel(); } catch (e) {} fin(); };
      const useVoicebox = S.mode === 'voicebox' && S.voiceboxOnline && S.voiceboxProfile;
      deadline = setTimeout(() => { if (!done && S.stop) S.stop(); }, useVoicebox ? 110000 : 45000);
      try {
        const ab = await request(useVoicebox ? '/api/voice/voicebox/speak' : '/api/voice/speak', useVoicebox ? { text, profile: S.voiceboxProfile } : { text, voice: S.voice || undefined }, 'speech', useVoicebox ? 100000 : 20000);
        if (done) return;
        try {
          if (S.actx) { await S.actx.resume(); const buf = await S.actx.decodeAudioData(ab.slice(0)); if (done) return; node = S.actx.createBufferSource(); node.buffer = buf; node.connect(S.actx.destination); node.onended = fin; node.start(); return; }
        } catch (e0) { node = null; }                                                 // AudioContext refused or could not decode: use the <audio> element
        try {
          if (done) return;
          const a = S.audio || (S.audio = new Audio()), url = URL.createObjectURL(new Blob([ab], { type: 'audio/mpeg' }));
          audioUrl = url; a.onended = fin; a.onerror = fin; a.src = url; await a.play();
        } catch (e1) {
          if (!S.actx) throw e1;                                                     // the element was refused: decode and play through the unlocked AudioContext
          await S.actx.resume(); const buf = await S.actx.decodeAudioData(ab.slice(0)); if (done) return; node = S.actx.createBufferSource(); node.buffer = buf; node.connect(S.actx.destination); node.onended = fin; node.start();
        }
      } catch (e) { if (!done) { await speakBrowser(text); fin(); hint('If you hear nothing on a phone: check it is not on silent, and tap SOUND ON once.'); } }
      finally { if (done) clearTimeout(deadline); }
    });
  }

  // ---- microphone
  async function ensureStream() {
    if (S.stream && S.stream.active) return true;
    try {
      S.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
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
  // resolves when an utterance has ended (~0.9 s of quiet after speech); true if speech was heard
  function untilUtteranceEnds(alreadySpoke, noSpeechMs) {
    return new Promise((resolve) => {
      let spoke = !!alreadySpoke, quiet = 0; const t0 = performance.now(), capture = S.capture, listen = S.listen;
      const tick = () => {
        if (!S.on || capture !== S.capture || listen !== S.listen) return resolve(false);
        const r = rms(), now = performance.now();
        if (r > 0.035) { spoke = true; quiet = 0; } else if (spoke && !quiet) quiet = now;
        if ((spoke && quiet && now - quiet > 900) || (spoke && now - t0 > 25000) || (!spoke && now - t0 > (noSpeechMs || 15000))) return resolve(spoke);
        requestAnimationFrame(tick);
      };
      tick();
    });
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
    if (!text || S.mute) return;
    const turn = S.turn;
    S.speaking = true; setState('composing', 'Speaking…');
    let rec = null, barged = false;
    if (S.on && S.stream) { try { rec = makeRec(); } catch (e) { rec = null; } }       // talk-over is always on
    if (rec) {
      let hi = 0, last = performance.now();
      const watch = () => { if (turn !== S.turn || !S.on || !S.speaking || barged) return; const now = performance.now(); hi = rms() > 0.045 ? hi + (now - last) : 0; last = now; if (hi > 150) { barged = true; if (S.stop) S.stop(); return; } requestAnimationFrame(watch); };
      watch();
    }
    await play(text);
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
    if (!S.whisper) { S.on = false; paintOn(); hint('Local speech recognition is not ready on the hub PC. Type below.'); setState('breathing', 'No local Whisper'); return; }
    hint('');
    while (S.on && listen === S.listen) {
      if (S.busy || S.speaking) { await new Promise((r) => setTimeout(r, 60)); continue; }
      const capture = S.capture;
      let blob = S.carry; S.carry = null;
      if (!blob) { setState('listening', 'Listening…'); try { blob = await recordUtterance(); } catch (e) { blob = null; } }
      if (!S.on || listen !== S.listen) break;
      if (capture !== S.capture) continue;
      if (!blob) continue;
      setState('working', 'Recognising…');
      let text = ''; try { text = await transcribe(blob); } catch (e) { if (capture === S.capture && S.on) { setState('breathing', 'Recognition failed'); hint('Please try again, or type your request.'); await new Promise((r) => setTimeout(r, 1500)); } continue; }
      if (!S.on || listen !== S.listen || capture !== S.capture) continue;
      if (text.replace(/[^\w]/g, '').length < 2) continue;
      hint(''); await handle(text);
    }
    // startLoop owns cleanup, so a quick stop/start cannot leave two recorders running.
  }

  // ---- talking to the assistant
  const YES = /^(yes|yeah|yep|yup|sure|okay|ok|go ahead|do it|confirm|please do|correct)\b/i, NO = /^(no|nope|cancel|stop|don'?t|do not|never mind|leave it)\b/i;
  async function handle(text) {
    cancelTurn(); const turn = S.turn; S.busy = true;
    try { await answer(text, turn); }
    catch (e) { if (turn === S.turn) { log('hub', e.name === 'AbortError' ? 'That took too long. Please try again.' : 'I could not complete that request. Please try again.'); hint(String(e.message || e).slice(0, 140)); } }
    finally { if (turn === S.turn) { S.busy = false; if (S.pending) setState('breathing', 'Waiting for confirmation'); else ready(); } }
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
    const r = await request('/api/voice/chat', { text, history: S.history.slice(-9, -1), mission: ctx.mission || null });
    if (turn !== S.turn) return;
    const serverResult = r.action && !r.confirm && !r.url;          // its own result is the answer: do not also say the model's sentence
    if (!serverResult) log('hub', r.say);
    if (r.action && r.confirm) { S.pending = r; showBtns(true); setState('breathing', 'Waiting for your yes'); await speak(r.say); return; }
    if (serverResult) return execute(r, turn);
    await speak(r.say);
    if (turn !== S.turn || S.carry) return;                       // you talked over the reply: handle what you said first
    if (r.action) await execute(r, turn);
  }
  function navigate(url) {
    if (location.pathname + location.search !== url) { saveSession(url); location.href = url; }
    else { S.compact = true; S.expanded = false; layout(); }
  }
  async function execute(r, turn) {
    if (turn !== S.turn) return;
    if (r.url) { navigate(r.url); return; }
    setState('working', 'Doing it…');
    const j = await request('/api/voice/act', { id: r.action.id, args: r.action.args });
    if (turn !== S.turn) return;
    log('hub', j.say, j.routine && j.routine.tag); await speak(j.say);
    if (turn === S.turn && !S.carry && j.url) navigate(j.url);
  }

  // ---- open / close / wiring
  function open(autoStart) {
    $('voice').hidden = false;
    if (window.ThinkingOrbs) window.ThinkingOrbs.mountAll($('voice'), '#00e676');
    paintOn(); layout();
    if (autoStart && !S.on) { S.on = true; paintOn(); startLoop(); }
  }
  function close() { S.on = false; S.listen++; fresh(); paintOn(); $('voice').hidden = true; }
  function toggle() { unlockAudio(); if (S.on) { S.on = false; S.listen++; cancelTurn(); S.pending = null; showBtns(false); saveSession(); paintOn(); ready(); } else { S.on = true; paintOn(); startLoop(); } }

  async function fillVoices() {
    try {
      const j = await (await fetch('/api/voice/voices')).json(), sel = $('v-voice');
      sel.innerHTML = j.voices.map((v) => `<option value="${v.id}">${v.name}</option>`).join('');
      sel.value = S.voice && j.voices.some((v) => v.id === S.voice) ? S.voice : j.default; S.voice = sel.value;
      sel.onchange = () => { S.voice = sel.value; try { localStorage.setItem('hubVoiceName', S.voice); } catch (e) {} };
    } catch (e) { $('v-voice').hidden = true; }
  }
  const paintToggles = () => { $('v-mute').textContent = S.mute ? 'SOUND OFF' : 'SOUND ON'; };

  document.addEventListener('DOMContentLoaded', () => {
    talkBtns().forEach((b) => { b.onclick = (e) => { e.stopPropagation(); unlockAudio(); $('voice').hidden ? open(true) : close(); }; });
    $('v-close').onclick = close; $('v-mic').onclick = toggle;
    $('v-size').onclick = () => { S.compact = !S.compact; layout(); };
    $('v-history').onclick = () => { S.expanded = !S.expanded; layout(); };
    $('v-new').onclick = fresh;
    $('v-cancel').onclick = () => { cancelTurn(); S.pending = null; showBtns(false); hint('Reply stopped. An action already sent may still finish; check its status before retrying.'); ready(); };
    $('v-mute').onclick = () => { unlockAudio(); S.mute = !S.mute; if (S.mute && S.stop) S.stop(); try { localStorage.setItem('hubVoiceMute', S.mute ? '1' : '0'); } catch (e) {} paintToggles(); };
    paintToggles();
    $('v-yes').onclick = () => { unlockAudio(); if (S.pending) handle('Yes'); };
    $('v-no').onclick = () => { if (S.pending) handle('No'); };
    const send = () => { unlockAudio(); const v = $('v-in').value.trim(); if (v) { $('v-in').value = ''; if (S.stop) S.stop(); handle(v); } };
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
  window.HubVoice = { ask(text) { unlockAudio(); open(false); return handle(String(text || '')); }, open, close,
    contextChanged(id) { if (S.context !== id) { S.context = id; fresh(); } S.compact = true; layout(); } };
})();


