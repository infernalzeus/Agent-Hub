// Smith's voice effect: the same text-to-speech audio, layered into a robotic "voice note" before it reaches the speakers.
// Nothing is synthesised here and nothing is sent anywhere: the reply's audio buffer is played through a small Web Audio chain.
//   dry voice          the neural voice itself, so the words stay clear
//   ring layer         the voice multiplied by a low sine (the classic robot timbre), roughened by a coarse quantiser
//   doubled layer      a copy 15 ms late, wobbling a few milliseconds (a second, slightly off voice on top)
//   metal layer        a 6 ms comb with feedback (a hollow, tube-like ring)
//   comms band         110 Hz to 6 kHz, then a compressor so the layers never clip
// Two choices, kept in localStorage: 'hubVoiceFx' = how much (off | p5 | p10 | p15 | p20 default | p25 | p35 | p50 | p75 | p100)
// and 'hubVoiceFxStyle' = which layers (blend default | ring | double | metal | radio). Older saved names (light, robot, heavy, full) still work.
(function () {
  if (window.HubVoiceFx) return;
  var KEY = 'hubVoiceFx', SKEY = 'hubVoiceFxStyle';
  // The effect is one recipe (FULL) mixed in by an amount, so "20 %" means the wet layers at a fifth of their full level over the clean voice.
  var FULL = { dry: .6, ring: .5, ringHz: 62, bits: 6, chorus: .34, comb: .2, out: .88 };
  // What each style keeps of the three wet layers, and the band the voice is squeezed into afterwards.
  var STYLES = {
    blend:  { ring: 1,   chorus: 1,   comb: 1,   hi: 110, lo: 6000 },      // all three layers: the default robot
    ring:   { ring: 1.4, chorus: 0,   comb: 0,   hi: 110, lo: 6000 },      // only the sine ring: buzzy, classic
    double: { ring: 0,   chorus: 2,   comb: 0,   hi: 110, lo: 6000 },      // only the wobbling second voice: a synthetic choir
    metal:  { ring: 0,   chorus: 0,   comb: 3,   hi: 110, lo: 6000 },      // only the hollow comb: a voice in a pipe
    radio:  { ring: .5,  chorus: .5,  comb: .5,  hi: 320, lo: 3400 }       // a little of each, through a narrow comms-radio band
  };
  var LEGACY = { light: 'p5', robot: 'p10', heavy: 'p35', full: 'p100' };
  function amount(a, st) {
    var w = STYLES[st] || STYLES.blend;
    return { amount: a, dry: 1 - (1 - FULL.dry) * a, ring: FULL.ring * a * w.ring, ringHz: FULL.ringHz, bits: FULL.bits, chorus: FULL.chorus * a * w.chorus, comb: FULL.comb * a * w.comb, out: 1 - (1 - FULL.out) * a, hi: w.hi, lo: w.lo };
  }
  var LEVELS = { off: null, p5: .05, p10: .1, p15: .15, p20: .2, p25: .25, p35: .35, p50: .5, p75: .75, p100: 1 };
  var DEFAULT = 'p20';
  function has(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }
  function mode() { try { var v = localStorage.getItem(KEY); v = LEGACY[v] || v; if (v && has(LEVELS, v)) return v; } catch (e) {} return DEFAULT; }
  function style() { try { var v = localStorage.getItem(SKEY); if (v && has(STYLES, v)) return v; } catch (e) {} return 'blend'; }
  function set(m) { m = LEGACY[m] || m; if (!has(LEVELS, m)) return; try { localStorage.setItem(KEY, m); } catch (e) {} }
  function setStyle(s) { if (!has(STYLES, s)) return; try { localStorage.setItem(SKEY, s); } catch (e) {} }
  function crusher(ctx, bits) {                      // quantise to 2^bits steps, then round the corners: grit without harsh aliasing
    var n = 2048, c = new Float32Array(n), steps = Math.pow(2, bits);
    for (var i = 0; i < n; i++) { var x = i / (n - 1) * 2 - 1; c[i] = Math.tanh(1.4 * Math.round(x * steps) / steps); }
    var w = ctx.createWaveShaper(); w.curve = c; w.oversample = '2x'; return w;
  }
  function gain(ctx, v) { var g = ctx.createGain(); g.gain.value = v; return g; }
  // Route `node` to `dest` through the effect. `seconds` is how long the reply lasts, so the oscillators can be stopped.
  function connect(ctx, node, dest, seconds, force, forceStyle) {
    var m = LEGACY[force] || force || mode(), lv = LEVELS[m], st = forceStyle || style();
    if (lv == null) { node.connect(dest); return null; }
    var p = amount(lv, st);
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
    var hi = ctx.createBiquadFilter(); hi.type = 'highpass'; hi.frequency.value = p.hi;
    var lo = ctx.createBiquadFilter(); lo.type = 'lowpass'; lo.frequency.value = p.lo;
    var comp = ctx.createDynamicsCompressor(); comp.threshold.value = -20; comp.knee.value = 10; comp.ratio.value = 5; comp.attack.value = .004; comp.release.value = .12;
    mix.connect(hi); hi.connect(lo); lo.connect(comp); comp.connect(gain(ctx, p.out)).connect(dest);
    osc.start(t0); lfo.start(t0); osc.stop(t1); lfo.stop(t1);
    return { mode: m, style: st, ends: t1 };
  }
  window.HubVoiceFx = { connect: connect, mode: mode, set: set, style: style, setStyle: setStyle, modes: Object.keys(LEVELS), styles: Object.keys(STYLES) };
})();
