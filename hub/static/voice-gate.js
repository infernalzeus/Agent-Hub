// Speech gate for the Talk panel: has the person started, and have they stopped?
//
// A fixed level (0.035) cannot tell a quiet voice from a quiet room, or a loud voice from a fan: in a noisy room it never saw "quiet" and
// waited the full 25 s, in a hushed one it missed soft speech. This keeps a running estimate of the room's own level and asks for a voice
// that is clearly above it, the way voice assistants do. It only decides when a recording ends; whether the SENTENCE is finished is still
// the job of the turn model and the wording check in voice.js, which can only make the hub wait longer.
//
//   floor    the room: rises slowly (a fan spinning up), falls quickly (a door closing); never learns from speech
//   trigger  max(MIN, floor x OVER): above this for START_MS means a voice, not a click or a knock
//   release  trigger x RELEASE once speaking: a dip inside a word does not end it (hysteresis)
//   quiet    below release for QUIET_MS ends the recording
(function (root) {
  const D = { over: 2.6, min: 0.02, release: 0.6, startMs: 110, quietMs: 1400, up: 0.0008, down: 0.02, floor0: 0.012 };
  const FRAME_MS = 1000 / 60;      // the two rates are per 60 Hz frame; scaled by the real gap so a 165 Hz screen learns at the same speed

  function make(opts, spokeAlready) {
    const o = Object.assign({}, D);
    for (const k in opts || {}) if (Number.isFinite(opts[k])) o[k] = opts[k];          // a missing or NaN setting keeps its default
    let floor = o.floor0, spoke = !!spokeAlready, loudSince = 0, quietSince = 0, last = 0;
    return {
      step(level, now) {
        const dt = last ? Math.min(250, now - last) : FRAME_MS;
        last = now;
        const trigger = Math.max(o.min, floor * o.over);
        const bar = spoke ? trigger * o.release : trigger;
        if (level > bar) {
          if (!loudSince) loudSince = now;
          if (!spoke && now - loudSince >= o.startMs) spoke = true;
          if (spoke) quietSince = 0;
        } else {
          loudSince = 0;
          if (spoke && !quietSince) quietSince = now;
        }
        if (level <= trigger) floor += (level - floor) * Math.min(1, (level > floor ? o.up : o.down) * (dt / FRAME_MS));
        return { spoke, ended: !!(spoke && quietSince && now - quietSince > o.quietMs), floor, trigger };
      },
      floor() { return floor; },
    };
  }

  // One short line said when a slow action has not answered yet, so a ten-second task does not read as a crash. Chosen by what was asked,
  // never the same line twice running; nothing is said for quick actions (the caller waits before asking for one).
  const LINES = [
    [/^(media|open_page|open_mission|status|mcp_status|list_)/, null],
    [/^(ytdl_download)/, ['Queueing it.', 'Adding it to the downloads.']],
    [/^(desktop_task|pc_|open_address|ingest_installed)/, ['On it.', 'Working on it.', 'Give me a moment.']],
    [/^(start_mission|new_ask|run_plan|apply|ingest_app)/, ['Starting that.', 'On it.']],
  ];
  const FALLBACK = ['Working on it.', 'One moment.', 'On it.'];
  const lastBy = new Map();
  function workingLine(actionId) {
    let pool = FALLBACK;
    for (const [rx, lines] of LINES) if (rx.test(String(actionId || ''))) { if (!lines) return ''; pool = lines; break; }
    const key = pool[0], prev = lastBy.get(key);
    let i = Math.floor(Math.random() * pool.length);
    if (pool.length > 1 && i === prev) i = (i + 1) % pool.length;
    lastBy.set(key, i);
    return pool[i];
  }

  // A reply is spoken sentence by sentence: the first piece is synthesised alone and starts playing while the rest are still being made, so
  // a three-sentence answer starts after about the time of its first sentence (measured: 1.6 s) instead of the whole answer (6.3 s).
  function sentences(text) {
    const parts = String(text || '').replace(/\s+/g, ' ').trim().match(/[^.!?]+(?:[.!?]+["')\]]*|$)/g) || [];
    const out = []; let cur = '';
    for (const raw of parts) {
      const p = raw.trim(); if (!p) continue;
      if (!out.length && cur.length >= 24 && /[.!?]["')\]]*$/.test(cur)) { out.push(cur); cur = ''; }          // the first piece is one whole sentence of some length
      if (cur && (cur + ' ' + p).length > 170 && out.length) { out.push(cur); cur = p; } else cur = cur ? cur + ' ' + p : p;
    }
    if (cur) out.push(cur);
    return out;
  }

  root.HubVoiceGate = { make, workingLine, sentences, defaults: D };
  if (typeof module !== 'undefined' && module.exports) module.exports = root.HubVoiceGate;
})(typeof window !== 'undefined' ? window : globalThis);
