// Smith's voice effect: the same text-to-speech audio, layered into a robotic "voice note" before it reaches the speakers.
// Nothing is synthesised here and nothing is sent anywhere: the reply's audio buffer is played through a small Web Audio chain.
//   dry voice          the neural voice itself, so the words stay clear
//   ring layer         the voice multiplied by a low sine (the classic robot timbre), roughened by a coarse quantiser
//   doubled layer      a copy 15 ms late, wobbling a few milliseconds (a second, slightly off voice on top)
//   metal layer        a 6 ms comb with feedback (a hollow, tube-like ring)
//   comms band         110 Hz to 6 kHz, then a compressor so the layers never clip
// The choice is kept in localStorage 'hubVoiceFx': off | light (5 %) | robot (10 %, default) | heavy (35 %) | full (100 %).
(function () {
  if (window.HubVoiceFx) return;
  var KEY = 'hubVoiceFx';
  // The effect is one recipe (FULL) mixed in by an amount, so "10 %" means the wet layers at a tenth of their full level over the clean voice.
  var FULL = { dry: .6, ring: .5, ringHz: 62, bits: 6, chorus: .34, comb: .2, out: .88 };
  function amount(a) { return { amount: a, dry: 1 - (1 - FULL.dry) * a, ring: FULL.ring * a, ringHz: FULL.ringHz, bits: FULL.bits, chorus: FULL.chorus * a, comb: FULL.comb * a, out: 1 - (1 - FULL.out) * a }; }
  var MODES = { off: null, light: amount(.05), robot: amount(.1), heavy: amount(.35), full: amount(1) };
  function mode() { try { var v = localStorage.getItem(KEY); if (v && Object.prototype.hasOwnProperty.call(MODES, v)) return v; } catch (e) {} return 'robot'; }
  function set(m) { if (!Object.prototype.hasOwnProperty.call(MODES, m)) return; try { localStorage.setItem(KEY, m); } catch (e) {} }
  function crusher(ctx, bits) {                      // quantise to 2^bits steps, then round the corners: grit without harsh aliasing
    var n = 2048, c = new Float32Array(n), steps = Math.pow(2, bits);
    for (var i = 0; i < n; i++) { var x = i / (n - 1) * 2 - 1; c[i] = Math.tanh(1.4 * Math.round(x * steps) / steps); }
    var w = ctx.createWaveShaper(); w.curve = c; w.oversample = '2x'; return w;
  }
  function gain(ctx, v) { var g = ctx.createGain(); g.gain.value = v; return g; }
  // Route `node` to `dest` through the effect. `seconds` is how long the reply lasts, so the oscillators can be stopped.
  function connect(ctx, node, dest, seconds, force) {
    var p = MODES[force || mode()];
    if (!p) { node.connect(dest); return null; }
    var t0 = ctx.currentTime, t1 = t0 + (seconds || 30) + .6;
    var input = gain(ctx, 1), mix = gain(ctx, 1);
    node.connect(input);
    input.connect(gain(ctx, p.dry)).connect(mix);
    // ring layer: input x sine(ringHz)
    var hp = ctx.createBiquadFilter(); hp.type = 'highpass'; hp.frequency.value = 280;
    var ring = gain(ctx, 0), osc = ctx.createOscillator(); osc.type = 'sine'; osc.frequency.value = p.ringHz; osc.connect(ring.gain);
    input.connect(hp); hp.connect(ring); ring.connect(crusher(ctx, p.bits)).connect(gain(ctx, p.ring * 1.6)).connect(mix);
    // doubled layer
    var dl = ctx.createDelay(.1); dl.delayTime.value = .015;
    var lfo = ctx.createOscillator(); lfo.type = 'sine'; lfo.frequency.value = 4.6; var depth = gain(ctx, .0035); lfo.connect(depth); depth.connect(dl.delayTime);
    input.connect(dl); dl.connect(gain(ctx, p.chorus)).connect(mix);
    // metal layer: comb with feedback
    var comb = ctx.createDelay(.05); comb.delayTime.value = .0062; var fb = gain(ctx, .5);
    input.connect(comb); comb.connect(fb); fb.connect(comb); comb.connect(gain(ctx, p.comb)).connect(mix);
    // comms band, then level
    var hi = ctx.createBiquadFilter(); hi.type = 'highpass'; hi.frequency.value = 110;
    var lo = ctx.createBiquadFilter(); lo.type = 'lowpass'; lo.frequency.value = 6000;
    var comp = ctx.createDynamicsCompressor(); comp.threshold.value = -20; comp.knee.value = 10; comp.ratio.value = 5; comp.attack.value = .004; comp.release.value = .12;
    mix.connect(hi); hi.connect(lo); lo.connect(comp); comp.connect(gain(ctx, p.out)).connect(dest);
    osc.start(t0); lfo.start(t0); osc.stop(t1); lfo.stop(t1);
    return { mode: force || mode(), ends: t1 };
  }
  window.HubVoiceFx = { connect: connect, mode: mode, set: set, modes: Object.keys(MODES) };
})();
