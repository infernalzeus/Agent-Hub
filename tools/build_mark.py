"""Build the Agent Hub mark: the globe shell + the crystal / star-cloud core, as one dependency-free script.

Inputs (kept exactly as Codex wrote them, in docs/assets):
    agent-hub-globe-contained.js   outer globe, built to hold a core inside it
    agent-hub-depth-flip.js        WebGL depth surface used by the star-cloud core
    agent-hub-core-flip-star.js    star-cloud core
    agent-hub-core-flip-crystal.js crystalline core
    agent-hub-facet-flip.js        the click-to-flip transition between the two cores

Output:
    docs/assets/agent-hub-mark.js        readable
    docs/assets/agent-hub-mark.min.js    minified (needs terser 5.51.2 via `npx --no-install terser`)
    hub/static/agent-hub-mark.min.js     copy served by the hub's dormant page

Every change to those inputs is a text substitution below that asserts it matched exactly once, so a
changed upstream file fails the build instead of silently producing something different.
Run:  python tools/build_mark.py
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "docs" / "assets"


def read(name: str) -> str:
    return (ASSETS / name).read_text(encoding="utf-8").replace("\r\n", "\n")


def cap_dpr(text: str) -> str:
    out, n = re.subn(r"(\w+)\.devicePixelRatio\|\|1", r"Math.min(2,\1.devicePixelRatio||1)", text)
    if n != 1:
        sys.exit("patch 'core dpr cap': expected 1 match, found %d" % n)
    return out


def crystal_core() -> str:
    """The crystal core as Codex wrote it, plus two options for phones:
    options.mesh  - facet resolution (24 by default; 12 is about a quarter of the facets)
    options.still - draw only when something changes (a touch, the return to rest, a pulse) instead of
                    redrawing about 15 times a second forever. Measured in WebKit: 264,000 canvas calls a second idle."""
    text = cap_dpr(read("agent-hub-core-flip-crystal.js"))
    text = sub(text, "var mesh=24,", "var mesh=options.mesh||24,", "crystal mesh option")
    # every facet stroked its rim twice inside save/restore, the second time with a canvas shadow blur; on an
    # iPhone the blur runs on the CPU per stroke. Phones (options.still) skip the blur, and no facet strokes an empty rim.
    text = sub(text, "var rim=[i0,i1,i2];for(", "var rim=[i0,i1,i2],rimN=0;for(", "rim count")
    text = sub(text, "if(edgeCounts[Math.min(u,v)*4096+Math.max(u,v)]===1){ctx.moveTo(",
               "if(edgeCounts[Math.min(u,v)*4096+Math.max(u,v)]===1){rimN++;ctx.moveTo(", "rim count++")
    text = sub(text, "ctx.globalAlpha=1;ctx.lineJoin='miter';ctx.miterLimit=3;ctx.strokeStyle='#025c73';ctx.lineWidth=Math.max(1,size/650);ctx.stroke();"
                     "ctx.shadowColor='#20e9ff';ctx.shadowBlur=Math.max(2,size*.008);ctx.strokeStyle='rgba(65,235,255,.8)';ctx.lineWidth=Math.max(.35,size/1500);ctx.stroke();ctx.restore();",
               "if(rimN){ctx.globalAlpha=1;ctx.lineJoin='miter';ctx.miterLimit=3;ctx.strokeStyle='#025c73';ctx.lineWidth=Math.max(1,size/650);ctx.stroke();"
               "if(!options.still){ctx.shadowColor='#20e9ff';ctx.shadowBlur=Math.max(2,size*.008);}ctx.strokeStyle='rgba(65,235,255,.8)';ctx.lineWidth=Math.max(.35,size/1500);ctx.stroke();}ctx.restore();",
               "rim strokes")
    text = sub(text, "draw();if((returning||!options.reducedMotion)&&alive&&!doc.hidden)request();",
               "draw();if((returning||(!options.reducedMotion&&!options.still)||(options.still&&performance.now()-pulseStarted<1300))&&alive&&!doc.hidden)request();",
               "crystal still option")
    return text


def sub(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        sys.exit(f"patch '{label}': expected exactly one match, found {n}")
    return text.replace(old, new)


# ── 1. the globe: link-up dissolve, calmer glow, steering by finger, no scroll capture ───────────────
globe = read("agent-hub-globe-contained.js")

# the shell: switching it off / on is not a fade. Connections pop and link up (or let go) in a random,
# flowing wave that starts from a different point on the sphere every time.
globe = sub(globe, "var variation = new Float32Array(count);",
            "var variation = new Float32Array(count);\n"
            "    var shellOn = options.shell !== false, shellP = shellOn ? 1 : 0, shellOrigin = new Float64Array([0, 0, 1]);\n"
            "    var dNode = new Float32Array(count), edgeLen = null, edgeJit = null;",
            "shell state")
globe = sub(globe, "edgeNext = new Int32Array(edgeA.length);",
            "edgeNext = new Int32Array(edgeA.length);\n"
            "    edgeLen = new Float32Array(edgeA.length).fill(1); edgeJit = new Float32Array(edgeA.length);\n"
            "    for (var jj = 0; jj < edgeA.length; jj++) edgeJit[jj] = ((jj * 2654435761) >>> 0) / 4294967296;",
            "edge arrays")
globe = sub(globe, "      var begun = root.performance.now();\n      try {",
            "      var begun = root.performance.now();\n      var shellEase = math.min(1, shellP * 1.7);\n      try {",
            "ease")
globe = sub(globe, "        ctx.drawImage(background, 0, 0, width, width);",
            "        ctx.globalAlpha = shellEase; ctx.drawImage(background, 0, 0, width, width); ctx.globalAlpha = 1;",
            "background")
globe = sub(globe, "          fade[k] = 1;\n",
            "          fade[k] = 1;\n"
            "          if (shellP < 1) {\n"
            "            var dn = math.acos(math.max(-1, math.min(1, xx * shellOrigin[0] + yy * shellOrigin[1] + zz * shellOrigin[2]))) / PI * .84\n"
            "              + variation[k] * .16;\n"
            "            dNode[k] = dn;\n"
            "            var nl = (shellP * 1.28 - dn) / .28;\n"
            "            fade[k] = nl <= 0 ? 0 : nl >= 1 ? 1 : nl;\n"
            "          }\n",
            "node wave")
globe = sub(globe, "          if (fade[u] < 1 || fade[v] < 1) bin += 16;\n",
            "          if (shellP < 1) {\n"
            "            var ea = dNode[u] <= dNode[v] ? u : v, eb = ea === u ? v : u;\n"
            "            var span = math.max(.2, dNode[eb] - dNode[ea] + .1), begin = dNode[ea] + .04 + edgeJit[k] * .025;\n"
            "            var ll = (shellP * 1.28 - begin) / span;\n"
            "            edgeLen[k] = ll <= 0 ? 0 : ll >= 1 ? 1 : ll;\n"
            "            if (edgeLen[k] === 0) continue;\n"
            "          } else edgeLen[k] = 1;\n",
            "edge wave")
globe = sub(globe, "          if (!asleep && !reduced) {\n            var travel = (clock * .45 + edgePhase[k]) % 3;",
            "          if (!asleep && !reduced && edgeLen[k] === 1) {\n            var travel = (clock * .45 + edgePhase[k]) % 3;",
            "sparks only on settled edges")
globe = sub(globe,
            "            ctx.moveTo(px[edgeA[e]], py[edgeA[e]]); ctx.lineTo(px[edgeB[e]], py[edgeB[e]]);",
            "            var eu = edgeA[e], ev = edgeB[e], el = edgeLen[e];\n"
            "            if (el < 1 && dNode[eu] > dNode[ev]) { var tt = eu; eu = ev; ev = tt; }\n"
            "            ctx.moveTo(px[eu], py[eu]);\n"
            "            ctx.lineTo(px[eu] + (px[ev] - px[eu]) * el, py[eu] + (py[ev] - py[eu]) * el);",
            "partial edges")
# nodes: pop in with a small overshoot instead of fading; calmer glow so the core reads through
globe = sub(globe, "          var star = variation[k];\n          var r = math.max(.48, width / 160) * (.55 + front * .9) * (.65 + star * .9);\n"
                   "          var glowSize = r * (3.3 + brightness[k] * 2);\n"
                   "          ctx.globalAlpha = math.min(1, gain * (.16 + .68 * front + brightness[k]) * (.35 + star * star * 1.2) * fade[k]);",
            "          var star = variation[k];\n          if (fade[k] <= 0) continue;\n"
            "          var pop = fade[k] < 1 ? 1 + 2.70158 * math.pow(fade[k] - 1, 3) + 1.70158 * math.pow(fade[k] - 1, 2) : 1;\n"
            "          var r = math.max(.48, width / 160) * (.55 + front * .9) * (.65 + star * .9) * pop;\n"
            "          var glowSize = r * (2.45 + brightness[k] * 1.5);\n"
            "          ctx.globalAlpha = math.min(1, gain * .7 * (.16 + .68 * front + brightness[k]) * (.35 + star * star * 1.2));",
            "node pop and glow")
globe = sub(globe, "ctx.globalAlpha = math.sin(PI * pulseTime) * .28;",
            "ctx.globalAlpha = math.sin(PI * pulseTime) * .28 * shellEase;", "pulse ring")
globe = sub(globe, "f.globalAlpha=.13;f.strokeStyle=colors[design*32+((depth[u]+depth[v])>>1)];f.beginPath();f.moveTo(px[u],py[u]);f.lineTo(px[v],py[v]);f.stroke();",
            "var el=edgeLen[k];if(el===0)continue;var ea=u,eb=v;if(el<1&&dNode[u]>dNode[v]){ea=v;eb=u;}"
            "f.globalAlpha=.07;f.strokeStyle=colors[design*32+((depth[u]+depth[v])>>1)];f.beginPath();f.moveTo(px[ea],py[ea]);"
            "f.lineTo(px[ea]+(px[eb]-px[ea])*el,py[ea]+(py[eb]-py[ea])*el);f.stroke();",
            "front edges")
globe = sub(globe, "var r=math.max(.45,width/190)*(3.3+brightness[k]*2),tint=variation[k]>.86?Math.min(3,depth[k]):depth[k];f.globalAlpha=.32+brightness[k]*.25;",
            "if(fade[k]<=0)continue;var pop=fade[k]<1?1+2.70158*Math.pow(fade[k]-1,3)+1.70158*Math.pow(fade[k]-1,2):1;"
            "var r=math.max(.45,width/190)*(2.2+brightness[k]*1.3)*pop,tint=variation[k]>.86?Math.min(3,depth[k]):depth[k];f.globalAlpha=.15+brightness[k]*.12;",
            "front nodes")
globe = sub(globe, "if (!alive || reduced || state === 'dormant') return;\n      pulseStart = clock;",
            "if (!alive || reduced || state === 'dormant' || shellP === 0) return;\n      pulseStart = clock;", "pulse needs shell")
globe = sub(globe, "function running() { return alive && visible && !doc.hidden && !reduced; }",
            "function running() { return alive && visible && !doc.hidden && !reduced && (shellOn || shellP > 0); }", "running")
globe = sub(globe, "g.t = now; clock += dt; phase += dt * .026;",
            "g.t = now; clock += dt; phase += dt * .026;\n"
            "      if (shellP !== (shellOn ? 1 : 0)) {\n"
            "        shellP += (shellOn ? 1 : -1) * dt / (shellOn ? 1.5 : 1.1);\n"
            "        if (shellP > 1 || shellP < 0) shellP = shellOn ? 1 : 0;\n"
            "      }", "frame advances shell")
globe = sub(globe, "      getQuaternion:function(){return Array.from(q);},pulse: pulse, setQuality:function(value){quality=Number(value)||1;resize();},",
            "      getQuaternion:function(){return Array.from(q);},pulse: pulse, setQuality:function(value){quality=Number(value)||1;resize();},\n"
            "      setShell: function (on) {\n"
            "        if (!alive || !!on === shellOn) return;\n"
            "        shellOn = !!on;\n"
            "        if (shellP <= 0 || shellP >= 1) {      // a fresh start: the wave begins somewhere new each time\n"
            "          var a = math.random() * TAU, z = math.random() * 2 - 1, sr = math.sqrt(1 - z * z);\n"
            "          shellOrigin[0] = sr * math.cos(a); shellOrigin[1] = sr * math.sin(a); shellOrigin[2] = z;\n"
            "        }\n"
            "        if (reduced) { shellP = shellOn ? 1 : 0; draw(); } else { g.t = 0; wake(); }\n"
            "      },\n"
            "      isShell: function () { return shellOn; },\n"
            "      // a finger moved by (dx, dy) px: same response as a mouse sweeping over the globe\n"
            "      steer: function (dx, dy) {\n"
            "        var distance = math.sqrt(dx * dx + dy * dy);\n"
            "        if (!alive || distance < .05 || options.interactive === false) return;\n"
            "        var now = root.performance.now(), angle = math.min(.22, distance / width * 1.3);\n"
            "        rotate(q, -dy / distance, dx / distance, 0, angle);\n"
            "        var speed = math.min(2.8, angle / math.max(.016, (now - lastMove) / 1000));\n"
            "        velocity[0] = velocity[0] * .35 - dy / distance * speed * .65;\n"
            "        velocity[1] = velocity[1] * .35 + dx / distance * speed * .65; velocity[2] *= .35;\n"
            "        interaction = lastMove = now; if (reduced) { velocity.fill(0); draw(); } wake();\n"
            "      },", "api")
globe = sub(globe, "canvas.setAttribute('aria-label', 'Agent Hub'); canvas.setAttribute('role', 'img');",
            "canvas.setAttribute('aria-label', 'Agent Hub'); canvas.setAttribute('role', 'img');\n"
            "    // a GPU reset takes 2D canvases with it; rebuild the layers rather than stay black\n"
            "    canvas.addEventListener('contextlost', function (e) { if (e.preventDefault) e.preventDefault(); });\n"
            "    canvas.addEventListener('contextrestored', function () { atlas = null; try { glowAtlas(doc); background = null; resize(); } catch (err) {} });",
            "context restore")
globe = sub(globe, "touch-action:pan-y;';",
            "touch-action:' + (options.touchLock ? 'none' : 'pan-y') + ';';", "touch action")

# The glow sprites sat in one row 12,288 px wide (96 x 128 px); the old globe's sheet was 512 px. A source canvas that
# wide falls off Safari's GPU path, so each of ~600 glow draws a frame read from a slow image. Same sprites, 12 x 8 grid.
globe = sub(globe, "atlas = doc.createElement('canvas'); atlas.width = 96 * 128; atlas.height = 128;",
            "atlas = doc.createElement('canvas'); atlas.width = 12 * 128; atlas.height = 8 * 128;", "atlas size")
globe = sub(globe, "      var cx = k * 32 + 16, g = ctx.createRadialGradient(cx, 16, 0, cx, 16, 16);",
            "      var cx = (k % 12) * 32 + 16, cy = Math.floor(k / 12) * 32 + 16, g = ctx.createRadialGradient(cx, cy, 0, cx, cy, 16);", "atlas grid")
globe = sub(globe, "ctx.fillStyle = g; ctx.fillRect(k * 32, 0, 32, 32);",
            "ctx.fillStyle = g; ctx.fillRect((k % 12) * 32, Math.floor(k / 12) * 32, 32, 32);", "atlas fill")
globe = sub(globe, "  function tick(now) {", "  function ax(i) { return (i % 12) * 128; }\n  function ay(i) { return Math.floor(i / 12) * 128; }\n  function tick(now) {", "atlas coords")
globe = sub(globe, "ctx.drawImage(atlas, (design*32+tint)*128, 0, 128, 128,", "ctx.drawImage(atlas, ax(design*32+tint), ay(design*32+tint), 128, 128,", "atlas draw")
globe = sub(globe, "ctx.drawImage(atlas,(design*32+tint)*128+56,56,16,16,", "ctx.drawImage(atlas,ax(design*32+tint)+56,ay(design*32+tint)+56,16,16,", "atlas cyan")
globe = sub(globe, "f.drawImage(atlas,(design*32+tint)*128,0,128,128,", "f.drawImage(atlas,ax(design*32+tint),ay(design*32+tint),128,128,", "atlas front")

# A phone does not need a 3x canvas for a glowing mark, and iOS kills pages that hold too much canvas memory.
globe = sub(globe, "(root.devicePixelRatio || 1)*quality", "math.min(2, root.devicePixelRatio || 1)*quality", "globe dpr cap")
# a drawing error used to destroy the globe silently and leave the PNG; keep the reason so it can be shown
n_catch = globe.count("catch (error) { destroy(); }")
if n_catch != 2:
    sys.exit("patch 'draw errors': expected 2 handlers, found %d" % n_catch)
globe = globe.replace("catch (error) { destroy(); }",
                      "catch (error) { root.__markError = 'globe: ' + (error && (error.stack || error.message) || error); destroy(); }")

# Selected cyan/green palette: 32 full-resolution sprites, 1024 x 512 instead of 1536 x 1024.
globe = sub(globe, "atlas.width = 12 * 128; atlas.height = 8 * 128;", "atlas.width = 8 * 128; atlas.height = 4 * 128;", "selected atlas bounds")
globe = sub(globe, "k < 96; k++", "k < 32; k++", "selected atlas palette")
globe = globe.replace("(k % 12)", "(k % 8)").replace("Math.floor(k / 12)", "Math.floor(k / 8)")
globe = globe.replace("colors[k]);", "colors[k+64]);")
globe = globe.replace("(i % 12) * 128", "(i % 32 % 8) * 128").replace("Math.floor(i / 12) * 128", "Math.floor((i % 32) / 8) * 128")

# Phone glows are drawn smaller than 64px; use a native-size cached sheet, retaining 128px for desktop.
globe = globe.replace("function glowAtlas(doc) {", "var atlasStep=root.matchMedia&&root.matchMedia('(pointer: coarse)').matches?64:128;\n  function glowAtlas(doc) {")
globe = globe.replace("atlas.width = 8 * 128; atlas.height = 4 * 128;", "atlas.width = 8 * atlasStep; atlas.height = 4 * atlasStep;")
globe = globe.replace("ctx.scale(4,4)", "ctx.scale(atlasStep/32,atlasStep/32)")
globe = globe.replace("(i % 32 % 8) * 128", "(i % 32 % 8) * atlasStep").replace("Math.floor((i % 32) / 8) * 128", "Math.floor((i % 32) / 8) * atlasStep")
globe = globe.replace("ay(design*32+tint), 128, 128", "ay(design*32+tint), atlasStep, atlasStep")
globe = globe.replace("ay(design*32+tint),128,128", "ay(design*32+tint),atlasStep,atlasStep")
globe = globe.replace("ax(design*32+tint)+56,ay(design*32+tint)+56,16,16", "ax(design*32+tint)+atlasStep*.4375,ay(design*32+tint)+atlasStep*.4375,atlasStep/8,atlasStep/8")

# Equal direction-independent timing; elapsed wall time avoids stretching when iOS drops frames.
globe = sub(globe, "var dNode = new Float32Array(count)", "var shellFrom=shellP,shellBegan=0;\n    var dNode = new Float32Array(count)", "shell timing state")
globe = sub(globe, "        shellP += (shellOn ? 1 : -1) * dt / (shellOn ? 1.5 : 1.1);\n        if (shellP > 1 || shellP < 0) shellP = shellOn ? 1 : 0;", "        var target=shellOn?1:0,progress=math.min(1,(now-shellBegan)/(1200*math.max(.05,math.abs(target-shellFrom))));\n        var eased=progress*progress*(3-2*progress);shellP=shellFrom+(target-shellFrom)*eased;\n        if(progress>=1)shellP=target;", "equal shell timing")
globe = sub(globe, "        shellOn = !!on;", "        shellFrom=shellP;shellBegan=root.performance.now();shellOn = !!on;", "shell timing start")
globe = sub(globe, "      isShell: function () { return shellOn; },", "      isShell: function () { return shellOn; },getShellProgress:function(){return shellP;},", "shell progress api")

# Dormant describes the Hub service, not a stopped decorative grid.
globe = globe.replace("if (!alive || reduced || state === 'dormant' || shellP === 0) return;", "if (!alive || reduced || shellP === 0) return;")
globe = globe.replace("state === 'live' && clock - lastPulse >= 6", "clock - lastPulse >= 6")
globe = globe.replace("!asleep && !reduced", "!reduced")

# ── 2. the flip transition: bound to one host instead of a page element ──────────────────────────────
flip = read("agent-hub-facet-flip.js")
start = flip.index("var host=document.getElementById('demo-1')")
body = flip[start:flip.rindex("})();")]
body = sub(body, "var host=document.getElementById('demo-1'),active=false,", "var active=false,", "flip host")
body = sub(body, "window.stopFacetFlip=function(){", "var stopFacetFlip=function(){", "flip stop")
body = body.replace("window.stopFacetFlip();", "stopFacetFlip();")
body = sub(body, "if(active||!window.CoreFlipControls)return;", "if(active)return;", "flip guard")
# The "before" picture must be exactly what is on screen. Re-rendering the core first redraws it without its
# current glints, so for a frame the old core appeared in a different light before the flip began.
body = sub(body, "function snapshot(core){core.renderNow();", "function snapshot(core){", "flip snapshot is the shown frame")
body = sub(body, "host.addEventListener('click',function(event){", "var onClick=function(event){", "flip click open")
tail = "\n});"
if not body.rstrip().endswith(tail):
    sys.exit("patch 'flip click close': handler end not where expected")
body = body.rstrip()[: -len(tail)] + "\n};\nhost.addEventListener('click',onClick);\n"
flip_fn = ("function installFlip(host,CoreFlipControls){\n" + body +
           "return {stop:stopFacetFlip,off:function(){stopFacetFlip();host.removeEventListener('click',onClick);}};\n}\n")

# ── 3. the one public entry point ────────────────────────────────────────────────────────────────────
glue = r"""
(function (root) {
  'use strict';
  /* AgentHubMark.mount(host, options) -> controller
   *   mode        'star' (default) | 'crystal'      which core sits inside the globe; a click flips it
   *   shell       true | false                      the globe structure around the core
   *   state       'live' | 'dormant'
   *   touchLock   true: a finger never scrolls the page from here (dormant page); drags turn core and globe
   *   size, reducedMotion, axis ('vertical'|'horizontal'|'free'|'depth'), face (parallax depth), coast (s)
   * Falls back, in order: star core -> crystal core -> globe alone -> the <img> already inside host. */
  function mount(host, options) {
    options = options || {};
    var doc = host.ownerDocument, mode = options.mode === 'star' ? 'star' : 'crystal';
    var state = options.state === 'dormant' ? 'dormant' : 'live';
    var reduced = options.reducedMotion === undefined
      ? !!(root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches) : !!options.reducedMotion;
    var shell = options.shell !== false, axis = options.axis || 'vertical', face = options.face || .25, coast = options.coast || 2;
    var globe = null, core = null, flip = null, alive = true,phoneCores={},warmTimer=0,sizeObserver=null;
    var control = {
      get: function () { return { core: core, globe: globe, mode: mode }; },
      'switch': function (next) { mode = next; build(true); return core; }
    };
    function syncCoreSizes(){
      if(!alive)return;
      var cores=lite?Object.values(phoneCores):[core];
      cores.forEach(function(item){if(item){item.resize();item.renderNow();}});
    }
    function build(keepGlobe) {
      if (flip) flip.stop();
      if(core){if(lite&&core.setActive){core.setActive(false);core.getCanvas().style.visibility="hidden";}else core.destroy();core=null;}
      var size = Number(options.size) || host.clientWidth || 220;
      if (!keepGlobe && globe) { globe.destroy(); globe = null; }
      if (!globe && root.AgentHubGlobeStarCloud) {
        try {
          globe = root.AgentHubGlobeStarCloud.mount(host, { size: size, design: 2, state: state, reducedMotion: reduced,
            resistance: coast, containCore: true, hoverOnly: true, shell: shell, touchLock: !!options.touchLock });
        } catch (error) { root.__markError = 'globe mount: ' + (error && error.message || error); globe = null; }
      }
      var factory = mode === 'star' ? root.StarCloudCore : root.AgentHubCrystalOptimized;
      // phones: draw only on change, with a lighter facet mesh (see crystal_core in build_mark.py)
      var coreOptions = lite ? { contained: !!globe, reducedMotion: reduced, coastOnRelease: true,brightness:.78 } : { contained: !!globe, reducedMotion: reduced };
      try { core = lite&&phoneCores[mode] ? phoneCores[mode] : (factory ? factory.mount(host, coreOptions) : null);if(core&&lite&&core.setActive){phoneCores[mode]=core;core.getCanvas().style.visibility="";core.setActive(true);} }
      catch (error) { root.__markError = 'core mount (' + mode + '): ' + (error && error.message || error); core = null; }
      if (!core && root.CrystallineCore) {       // no WebGL: the crystal core is plain 2D canvas
        mode = 'crystal';
        try { core = root.CrystallineCore.mount(host, coreOptions); }
        catch (error) { root.__markError = 'core mount (crystal): ' + (error && error.message || error); core = null; }
      }
      if (core) {
        core.setMode(axis); core.setResistance(coast);
        if (core.setParallax) core.setParallax(face);
        var cv = core.getCanvas && core.getCanvas();
        if (cv && mode === 'star') cv.addEventListener('webglcontextlost', function (e) {
          e.preventDefault(); root.__markError = 'WebGL context lost: switched to the crystal core';
          setTimeout(function () { if (alive) { mode = 'crystal'; build(true); } }, 0);
        }, { once: true });
      }
    }
    // A finger on the page: lock scrolling here and let the same drag also steer the globe.
    var touch = null;
    function touchMove(event) {
      if (event.pointerType !== 'touch' || !globe || lite) return;
      if (touch && touch.id === event.pointerId) globe.steer(event.clientX - touch.x, event.clientY - touch.y);
      touch = { id: event.pointerId, x: event.clientX, y: event.clientY };
    }
    function touchEnd() { touch = null; }
    if (options.touchLock) {
      host.style.touchAction = 'none';
      host.addEventListener('pointermove', touchMove, true);
      host.addEventListener('pointerup', touchEnd, true); host.addEventListener('pointercancel', touchEnd, true);
    }
    // The facet flip repaints roughly two thousand clipped triangles every frame. A desktop GPU does that without
    // noticing; a phone is killed by it the moment the sphere is tapped. On a touch screen a tap pulses the globe
    // instead and the core stays as it is. (options.lite: true / false overrides.)
    var lite = options.lite !== undefined ? !!options.lite
      : !!(root.matchMedia && (root.matchMedia('(pointer: coarse)').matches || root.matchMedia('(hover: none)').matches));
    var phoneFlip=null;
    function stopPhoneFlip(){if(phoneFlip)phoneFlip.stop();phoneFlip=null;}
    function liteClick(event){
      if(phoneFlip||!core)return;
      syncCoreSizes();
      var pose=core.getQuaternion(),motion=core.getMotion(),points=core.getGeometry().points,mesh=core.getRenderMesh(),old=core.getCanvas(),copy=doc.createElement('canvas');
      copy.width=old.width;copy.height=old.height;copy.getContext('2d').drawImage(old,0,0);
      mode=mode==='star'?'crystal':'star';build(true);if(!core)return;
      core.setPose(pose);core.setMotion(motion);core.renderNow();if(globe)globe.pulse();
      if(reduced)return;
      try{phoneFlip=root.AgentHubFacetGPU.start(host,points,mesh,copy,core,event,!!globe,function(){phoneFlip=null;});}
      catch(error){stopPhoneFlip();if(core)core.getCanvas().style.visibility='';root.__markError='phone facet transition: '+error.message;}
    }
    if(lite)host.addEventListener('click',liteClick);
    flip = lite ? {stop:stopPhoneFlip,off:function(){stopPhoneFlip();host.removeEventListener('click',liteClick);}} : installFlip(host, control);
    // A black page on an iPhone is its GPU process being killed, and the star core's WebGL (antialiased,
    // preserved buffer, a 2048 px texture held in memory) is the one thing here that loads that process.
    var noGL = options.webgl === false;
    if (noGL && mode === 'star') mode = 'crystal';
    build(false);
    if(lite&&mode==='crystal')warmTimer=setTimeout(function(){warmTimer=0;if(!alive||phoneCores.star||mode!=='crystal')return;try{var warm=root.StarCloudCore.mount(host,{contained:!!globe,reducedMotion:reduced,coastOnRelease:true,brightness:.78});if(warm){warm.setParallax(face);warm.renderNow();warm.setActive(false);warm.getCanvas().style.visibility='hidden';phoneCores.star=warm;}}catch(error){/* First-use fallback remains available. */}},100);
    root.addEventListener('resize',syncCoreSizes);
    if(root.ResizeObserver){sizeObserver=new root.ResizeObserver(syncCoreSizes);sizeObserver.observe(host);}
    if (!globe && !core) { flip.off(); return null; }
    return {
      get core() { return core; }, get globe() { return globe; }, get stats() { return globe ? globe.stats : { frameMs: 0, frames: 0 }; },
      getMode: function () { return mode; },
      setMode: function (next) {
        if (noGL && next === 'star') return;
        if (next !== mode && (next === 'star' || next === 'crystal')) { mode = next; build(true); }
      },
      setShell: function (on) { shell = !!on; if (globe) globe.setShell(shell); },
      isShell: function () { return shell; },
      setState: function (next) { state = next === 'dormant' ? 'dormant' : 'live'; if (globe) globe.setState(state); },
      pulse: function () { if (globe) globe.pulse(); },
      reset: function () { if (core) core.reset(); },
      resize: syncCoreSizes,
      destroy: function () {
        if (!alive) return; alive = false;
        if(warmTimer)clearTimeout(warmTimer);if(sizeObserver)sizeObserver.disconnect();root.removeEventListener("resize",syncCoreSizes);flip.off();if(lite){Object.keys(phoneCores).forEach(function(key){phoneCores[key].destroy();});if(core&&!Object.values(phoneCores).includes(core))core.destroy();}else if(core)core.destroy();if(globe)globe.destroy();core=globe=null;
        host.removeEventListener('pointermove', touchMove, true);
        host.removeEventListener('pointerup', touchEnd, true); host.removeEventListener('pointercancel', touchEnd, true);
      }
    };
  }
  /* A turquoise ring that crosses `container` from the point (x, y), in client coordinates. */
  function ripple(container, x, y) {
    try { rippleNow(container, x, y); } catch (error) { root.__markError = 'ripple: ' + (error && error.message || error); }
  }
  function rippleNow(container, x, y) {
    if (!container || !container.getBoundingClientRect || !container.animate && !(container.ownerDocument.createElement('div').animate)) return;
    if (root.matchMedia && root.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    var r = container.getBoundingClientRect(), doc = container.ownerDocument;
    var fixed = container === doc.body || container === doc.documentElement;
    var ox = fixed ? x : x - r.left, oy = fixed ? y : y - r.top;
    var w = fixed ? root.innerWidth : r.width, h = fixed ? root.innerHeight : r.height;
    var reach = Math.max(Math.hypot(ox, oy), Math.hypot(w - ox, oy), Math.hypot(ox, h - oy), Math.hypot(w - ox, h - oy));
    // A thin line: the box itself grows (width/height), so the 1 px border stays 1 px at any size.
    var ring = doc.createElement('div'), d = Math.ceil(reach * 2.1);
    ring.style.cssText = 'position:' + (fixed ? 'fixed' : 'absolute') + ';left:' + ox + 'px;top:' + oy + 'px;width:' + d + 'px;height:' + d + 'px;'
      + 'box-sizing:border-box;transform:translate(-50%,-50%);border-radius:50%;pointer-events:none;z-index:50;'
      + 'border:1px solid rgba(64,224,208,.9);box-shadow:0 0 5px rgba(64,224,208,.35)';
    if (!fixed && root.getComputedStyle(container).position === 'static') container.style.position = 'relative';
    (fixed ? doc.body : container).appendChild(ring);
    var run = ring.animate([{ transform:'translate(-50%,-50%) scale(.001)',opacity:0 },{ offset:.12,transform:'translate(-50%,-50%) scale(.12)',opacity:.85 },{ transform:'translate(-50%,-50%) scale(1)',opacity:0 }],
      { duration: 1200, easing: 'cubic-bezier(.4,0,.6,1)' });
    run.onfinish = function () { if (ring.parentNode) ring.parentNode.removeChild(ring); };
  }

  /* A tap on `surface` that lands on neither a control nor the mark itself switches the shell and sends a ripple.
   *   options.ignore     extra selector for things that keep their own behaviour
   *   options.rippleIn   element the ripple is drawn in (default: surface)
   *   options.onToggle   called with the new state after each switch                                     */
  function tapToToggle(surface, mark, host, options) {
    options = options || {};
    var skip = 'a,button,input,select,textarea,label,[data-keep]' + (options.ignore ? ',' + options.ignore : '');
    var down = null;
    function inside(el, x, y) {          // the mark is a circle: the corners of its box still count as outside
      var b = el.getBoundingClientRect(), c = b.width / 2;
      return Math.hypot(x - (b.left + c), y - (b.top + b.height / 2)) <= c;
    }
    function onDown(e) {
      if (e.pointerType === 'mouse' && e.button !== 0) return;
      down = e.target.closest && e.target.closest(skip) ? null : { id: e.pointerId, x: e.clientX, y: e.clientY, t: Date.now() };
      if (down && inside(host, e.clientX, e.clientY)) down = null;
    }
    function onUp(e) {
      try { tapUp(e); } catch (error) { down = null; root.__markError = 'tap: ' + (error && error.message || error); }
    }
    function tapUp(e) {
      if (!down || e.pointerId !== down.id) return;
      var moved = Math.hypot(e.clientX - down.x, e.clientY - down.y), took = Date.now() - down.t; down = null;
      if (moved > 10 || took > 700) return;            // a drag or a long press is not a tap
      if (options.onTap) options.onTap(e);
      var on = !mark.isShell(); mark.setShell(on);
      ripple(options.rippleIn || surface, e.clientX, e.clientY);
      if (options.onToggle) options.onToggle(on);
    }
    function onCancel() { down = null; }
    surface.addEventListener('pointerdown', onDown); surface.addEventListener('pointerup', onUp);
    surface.addEventListener('pointercancel', onCancel);
    return function () {
      surface.removeEventListener('pointerdown', onDown); surface.removeEventListener('pointerup', onUp);
      surface.removeEventListener('pointercancel', onCancel);
    };
  }

  root.AgentHubMark = { mount: mount, ripple: ripple, tapToToggle: tapToToggle };
})(typeof window !== 'undefined' ? window : globalThis);
"""

# installFlip must be visible to the glue; define it as a plain function in the shared scope.
bundle = (
    "/* Agent Hub mark. Generated by tools/build_mark.py from the files in docs/assets; do not edit by hand. */\n"
    + flip_fn + "\n"
    + ";" + globe + "\n"
    + ";" + read("agent-hub-depth-flip.js") + "\n"
    + ";" + cap_dpr(read("agent-hub-core-star-optimized.js")) + "\n;window.StarCloudCore = window.AgentHubStarOptimized;\n"
    + ";" + crystal_core() + "\n;window.CrystallineCore = window.AgentHubCoreLab;\n"
    + ";" + read("agent-hub-crystal-gpu.js") + "\n"
    + ";" + cap_dpr(read("agent-hub-core-crystal-optimized.js")) + "\n"
    + ";" + read("agent-hub-facet-gpu.js") + "\n"
    + glue
)
(ASSETS / "agent-hub-mark.js").write_text(bundle, encoding="utf-8", newline="\n")

# ── 4. minify and place ──────────────────────────────────────────────────────────────────────────────
npx = shutil.which("npx.cmd") or shutil.which("npx")
if not npx:
    sys.exit("npx not found; readable bundle written only")
# Pinned: another Terser version minifies differently, so a rebuild would no longer match the committed bundle.
TERSER_VERSION = "5.51.2"
found = subprocess.run([npx, "--no-install", "terser", "--version"], capture_output=True, text=True, cwd=str(ASSETS))
if found.returncode != 0 or found.stdout.split()[-1:] != [TERSER_VERSION]:
    sys.exit(f"terser {TERSER_VERSION} is required (found: {found.stdout.strip() or 'none'}). "
             f"Install it with: npm install -g terser@{TERSER_VERSION}. The readable bundle was written; nothing else changed.")
cmd = [npx, "--no-install", "terser", str(ASSETS / "agent-hub-mark.js"), "-c", "passes=2,drop_console=true", "-m",
       "--define", "module=false", "-o", str(ASSETS / "agent-hub-mark.min.js")]
subprocess.run(cmd, check=True, cwd=str(ASSETS))
shutil.copy(ASSETS / "agent-hub-mark.min.js", ROOT / "hub" / "static" / "agent-hub-mark.min.js")
print("readable", (ASSETS / "agent-hub-mark.js").stat().st_size, "bytes; minified",
      (ASSETS / "agent-hub-mark.min.js").stat().st_size, "bytes")
