/* Agent Hub globe — Canvas 2D, no dependencies. Readable distribution.
 * One visible canvas per instance; shared glow atlas and cached static layers.
 * All geometry, buckets and scratch vectors are allocated at mount/resize.
 */
(function (root) {
  'use strict';
  var instances = [], raf = 0, atlas = null;
  var math = Math, PI = math.PI, TAU = PI * 2;
  var colors = [], i;
  for (i = 0; i < 16; i++) {
    var t = i / 15, stops = [[33,62,192],[46,110,243],[59,167,255],[25,230,166],[0,230,118]];
    var ramp=t<.5?t*6:3+(t-.5)*2; var at=math.min(3,math.floor(ramp)),mix=ramp-at;
    var red = math.round(stops[at][0] * (1-mix) + stops[at+1][0] * mix);
    var green = math.round(stops[at][1] * (1-mix) + stops[at+1][1] * mix);
    var blue = math.round(stops[at][2] * (1-mix) + stops[at+1][2] * mix);
    colors[i] = 'rgb(' + red + ',' + green + ',' + blue + ')';
    colors[i + 16] = 'rgb(' + math.round(78 + 20 * (1 - t)) + ',' +
      math.round(128 + 35 * t) + ',' + math.round(168 - 40 * t) + ')';
  }

  // Pre-multiply by a world-space rotation, then normalise. No gimbal lock.
  function rotate(q, x, y, z, angle) {
    var s = math.sin(angle / 2), w = math.cos(angle / 2);
    x *= s; y *= s; z *= s;
    var a = q[0], b = q[1], c = q[2], d = q[3];
    q[0] = w * a + x * d + y * c - z * b;
    q[1] = w * b - x * c + y * d + z * a;
    q[2] = w * c + x * b - y * a + z * d;
    q[3] = w * d - x * a - y * b - z * c;
    var n = math.sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3]);
    for (var k = 0; k < 4; k++) q[k] /= n;
  }
  function matrix(q, m) {
    var x = q[0], y = q[1], z = q[2], w = q[3];
    m[0] = 1 - 2 * (y * y + z * z); m[1] = 2 * (x * y - z * w); m[2] = 2 * (x * z + y * w);
    m[3] = 2 * (x * y + z * w); m[4] = 1 - 2 * (x * x + z * z); m[5] = 2 * (y * z - x * w);
    m[6] = 2 * (x * z - y * w); m[7] = 2 * (y * z + x * w); m[8] = 1 - 2 * (x * x + y * y);
    return m;
  }
  function random(seed) {
    return function () {
      seed |= 0; seed = seed + 0x6d2b79f5 | 0;
      var a = math.imul(seed ^ seed >>> 15, 1 | seed);
      a = a + math.imul(a ^ a >>> 7, 61 | a) ^ a;
      return ((a ^ a >>> 14) >>> 0) / 4294967296;
    };
  }
  function glowAtlas(doc) {
    if (atlas) return atlas;
    atlas = doc.createElement('canvas'); atlas.width = 32 * 32; atlas.height = 32;
    var ctx = atlas.getContext('2d');
    if (!ctx) throw new Error('Canvas');
    for (var k = 0; k < 32; k++) {
      var cx = k * 32 + 16, g = ctx.createRadialGradient(cx, 16, 0, cx, 16, 16);
      g.addColorStop(0, k < 16 ? '#d2ffe5' : '#a4bbb0'); g.addColorStop(.12, colors[k]);
      g.addColorStop(.28, colors[k]); g.addColorStop(1, 'transparent');
      ctx.fillStyle = g; ctx.fillRect(k * 32, 0, 32, 32);
    }
    return atlas;
  }
  function tick(now) {
    raf = 0;
    var active = false, interval = instances.length > 1 ? 1000 / 30 : 0;
    for (var k = 0; k < instances.length; k++) {
      var g = instances[k];
      if (!g.running()) continue;
      active = true;
      if (now - g.t + .2 >= interval) g.frame(now);
    }
    if (active) raf = root.requestAnimationFrame(tick);
  }
  function wake() { if (!raf && instances.length) raf = root.requestAnimationFrame(tick); }

  function mount(element, options) {
    options = options || {};
    if (!element || !element.ownerDocument) throw new TypeError('element required');
    var doc = element.ownerDocument, canvas = doc.createElement('canvas'), ctx;
    var prior = { position: element.style.position, width: element.style.width, height: element.style.height };
    var fallbacks = element.querySelectorAll('img'), hidden = [], imageVisibility = [];
    for (i = 0; i < fallbacks.length; i++) {
      hidden[i] = fallbacks[i].hidden; imageVisibility[i] = fallbacks[i].style.visibility;
    }
    try { ctx = canvas.getContext('2d'); if (!ctx) return null; glowAtlas(doc); }
    catch (err) { return null; }
    var state = options.state === 'dormant' ? 'dormant' : 'live';
    var query = root.matchMedia ? root.matchMedia('(prefers-reduced-motion: reduce)') : null;
    var reduced = options.reducedMotion === undefined ? !!(query && query.matches) : !!options.reducedMotion;
    var size = math.max(72, math.min(320, Number(options.size) || 138));
    var width = size, dpr = 1, radius, centre, background, letter, ring;
    var alive = true, visible = true, hovering = false, pointer = -1, dragging = false;
    var pressX = 0, pressY = 0, lastMove = 0, interaction = -Infinity, suppressClick = false;
    var rect, hoverX = 0, hoverY = 0, haveHover = false;
    var q = new Float64Array([0, 0, 0, 1]), m = new Float64Array(9);
    var prev = new Float64Array(3), next = new Float64Array(3);
    var axis = new Float64Array([math.sin(23 * PI / 180), math.cos(23 * PI / 180), 0]);
    var velocity = new Float64Array(3), phase = 0, clock = 0, pulseStart = -10, lastPulse = 0;
    var coast = math.max(.6, math.min(10, Number(options.resistance) || 4));
    var design = math.max(0, math.min(2, Number(options.design) || 0));
    var count = 576, xyz = new Float64Array(count * 3);
    var px = new Float32Array(count), py = new Float32Array(count), pz = new Float32Array(count);
    var fade = new Float32Array(count), brightness = new Float32Array(count);
    var variation = new Float32Array(count);
    var depth = new Uint8Array(count), rng = random(0x41a6e17);
    var edgeA = [], edgeB = [], used = Object.create(null);
    var aNodes = new Float64Array(60 * 2), aLinks, aStrength = new Float32Array(60);
    var strokes = [-.43, .48, 0, -.54, 0, -.54, .43, .48, -.245, .045, .245, .045];
    var edgeNext, edgePhase, edgeTravel, sparkNext;
    var heads = new Int32Array(32), sparkHeads = new Int32Array(32);
    var pulseEvent = new root.Event('pulse', { bubbles: true });
    var stats = { frameMs: 0, frames: 0 };
    rotate(q, 0, 1, 0, -.28); rotate(q, 1, 0, 0, .19);

    // 420 outer nodes, 96 and 60 interior nodes. Deterministic jitter.
    var start = 0, counts = [420, 96, 60], radii = [1, .82, .64];
    for (var layer = 0; layer < 3; layer++) {
      for (i = 0; i < counts[layer]; i++) {
        var y = 1 - 2 * (i + .5) / counts[layer], phi = i * PI * (3 - math.sqrt(5));
        y = math.max(-.999, math.min(.999, y + (rng() - .5) * .025));
        phi += (rng() - .5) * .13;
        var rr = radii[layer], rr2 = math.sqrt(1 - y * y), at = start + i;
        xyz[at * 3] = math.cos(phi) * rr2 * rr; xyz[at * 3 + 1] = y * rr;
        xyz[at * 3 + 2] = math.sin(phi) * rr2 * rr;
        variation[at] = rng();
      }
      start += counts[layer];
    }
    // Three nearest neighbours (two on alternate nodes); unordered pairs cached.
    for (i = 0; i < count; i++) {
      var best = [Infinity, Infinity, Infinity], neighbours = [-1, -1, -1];
      for (var j = 0; j < count; j++) {
        if (i === j) continue;
        var dx = xyz[i * 3] - xyz[j * 3], dy = xyz[i * 3 + 1] - xyz[j * 3 + 1];
        var dz = xyz[i * 3 + 2] - xyz[j * 3 + 2], distance = dx * dx + dy * dy + dz * dz;
        for (var n = 0; n < 3; n++) if (distance < best[n]) {
          for (var h = 2; h > n; h--) { best[h] = best[h - 1]; neighbours[h] = neighbours[h - 1]; }
          best[n] = distance; neighbours[n] = j; break;
        }
      }
      for (n = 0; n < 2 + (i % 2); n++) {
        var lo = math.min(i, neighbours[n]), hi = math.max(i, neighbours[n]), pairKey = lo * count + hi;
        if (!used[pairKey]) { used[pairKey] = true; edgeA.push(lo); edgeB.push(hi); }
      }
    }
    edgeA = new Uint16Array(edgeA); edgeB = new Uint16Array(edgeB);
    edgeNext = new Int32Array(edgeA.length);
    edgePhase = new Float32Array(edgeA.length); edgeTravel = new Float32Array(edgeA.length);
    sparkNext = new Int32Array(edgeA.length);
    // Cache graph-distance delays. Packets follow connected edges outward
    // from each component's root, instead of flickering unrelated segments.
    var adjacent = new Int32Array(count), neighboursTo = new Uint16Array(edgeA.length * 2);
    var neighboursNext = new Int32Array(edgeA.length * 2), graphDistance = new Int16Array(count);
    var queue = new Uint16Array(count);
    adjacent.fill(-1); graphDistance.fill(-1);
    for (i = 0; i < edgeA.length; i++) {
      var ai = edgeA[i], bi = edgeB[i];
      neighboursTo[i * 2] = bi; neighboursNext[i * 2] = adjacent[ai]; adjacent[ai] = i * 2;
      neighboursTo[i * 2 + 1] = ai; neighboursNext[i * 2 + 1] = adjacent[bi]; adjacent[bi] = i * 2 + 1;
    }
    for (i = 0; i < count; i++) {
      if (graphDistance[i] !== -1) continue;
      graphDistance[i] = 0; queue[0] = i;
      var read = 0, write = 1;
      while (read < write) {
        var current = queue[read++];
        for (var entry = adjacent[current]; entry !== -1; entry = neighboursNext[entry]) {
          var destination = neighboursTo[entry];
          if (graphDistance[destination] === -1) {
            graphDistance[destination] = graphDistance[current] + 1; queue[write++] = destination;
          }
        }
      }
    }
    for (i = 0; i < edgeA.length; i++) {
      if (graphDistance[edgeA[i]] > graphDistance[edgeB[i]]) {
        var swap = edgeA[i]; edgeA[i] = edgeB[i]; edgeB[i] = swap;
      }
      edgePhase[i] = (3 - (graphDistance[edgeA[i]] * .19) % 3) % 3;
    }
    // Three proposed fixed-A star arrangements, all seeded and font-free.
    var nodeAt = 0, letterPairs = [], letterUsed = Object.create(null);
    for (i=0;i<3;i++) {
      var steps = i<2 ? 24 : 12;
      var vx = strokes[i*4+2]-strokes[i*4], vy = strokes[i*4+3]-strokes[i*4+1];
      var length = math.sqrt(vx*vx+vy*vy), nx=-vy/length, ny=vx/length;
      for(j=0;j<steps;j++) {
        t=math.max(0,math.min(1,j/(steps-1)+(rng()-.5)*.035));
        var spread = design===0 ? .075 : design===1 ? .085 : .026;
        var offset = (rng()-.5)*spread;
        if(design===0 && j%9===4)offset*=1.8;
        aNodes[nodeAt*2]=strokes[i*4]+vx*t+nx*offset;
        aNodes[nodeAt*2+1]=strokes[i*4+1]+vy*t+ny*offset;
        aStrength[nodeAt]=design===2 ? (j%5===0 || j===steps-1 ? 1 : .16) : .18+.82*math.pow(rng(),1.5);
        if(j===0||j===steps-1)aStrength[nodeAt]=1;
        nodeAt++;
      }
    }
    for(i=0;i<60;i++) {
      var nearest=[-1,-1,-1], best=[Infinity,Infinity,Infinity];
      for(j=0;j<60;j++)if(i!==j){
        var dx=aNodes[i*2]-aNodes[j*2],dy=aNodes[i*2+1]-aNodes[j*2+1],dd=dx*dx+dy*dy;
        for(var n=0;n<3;n++)if(dd<best[n]){
          for(var h=2;h>n;h--){best[h]=best[h-1];nearest[h]=nearest[h-1];}
          best[n]=dd;nearest[n]=j;break;
        }
      }
      for(n=0;n<(design===2?2:3);n++){
        var low=math.min(i,nearest[n]),high=math.max(i,nearest[n]),pair=low*60+high;
        if(!letterUsed[pair]){letterUsed[pair]=1;letterPairs.push(low,high);}
      }
    }
    aLinks=new Uint8Array(letterPairs);

    function letterDistance(x, y) {
      var bestDistance = Infinity;
      for (var k = 0; k < 3; k++) {
        var ax = strokes[k * 4], ay = strokes[k * 4 + 1];
        var bx = strokes[k * 4 + 2] - ax, by = strokes[k * 4 + 3] - ay;
        var u = math.max(0, math.min(1, ((x - ax) * bx + (y - ay) * by) / (bx * bx + by * by)));
        var ex = x - ax - u * bx, ey = y - ay - u * by;
        bestDistance = math.min(bestDistance, ex * ex + ey * ey);
      }
      return bestDistance;
    }
    function staticLayers() {
      background = doc.createElement('canvas'); letter = doc.createElement('canvas');
      background.width = letter.width = canvas.width; background.height = letter.height = canvas.height;
      var c = background.getContext('2d'), a = letter.getContext('2d');
      if (!c || !a) throw new Error('Canvas');
      c.scale(dpr, dpr); a.scale(dpr, dpr);
      var g = c.createRadialGradient(centre - radius * .28, centre - radius * .28, 0, centre, centre, radius);
      g.addColorStop(0, 'rgba(13,16,80,.45)'); g.addColorStop(.7, 'rgba(7,10,37,.78)');
      g.addColorStop(1, 'rgba(7,10,37,.93)');
      c.fillStyle = g; c.beginPath(); c.arc(centre, centre, radius, 0, TAU); c.fill();
      g = a.createRadialGradient(centre, centre, radius * .12, centre, centre, radius * .66);
      g.addColorStop(0, 'rgba(0,230,118,.10)'); g.addColorStop(.48, 'rgba(0,230,118,.065)');
      g.addColorStop(1, 'transparent'); a.fillStyle = g; a.fillRect(0, 0, width, width);
      a.lineWidth = math.max(.4, width / 360); a.strokeStyle = design===2 ? 'rgba(151,255,200,.60)' : 'rgba(0,230,118,.60)';
      a.beginPath();
      for (var k = 0; k < aLinks.length; k += 2) {
        var u = aLinks[k] * 2, v = aLinks[k + 1] * 2;
        a.moveTo(centre + aNodes[u] * radius, centre + aNodes[u + 1] * radius);
        a.lineTo(centre + aNodes[v] * radius, centre + aNodes[v + 1] * radius);
      }
      a.stroke();
      for (k = 0; k < 60; k++) {
        var x = centre + aNodes[k * 2] * radius, y = centre + aNodes[k * 2 + 1] * radius;
        var strength=aStrength[k], dot=math.max(.32,width/240)*(.45+strength*.9), glow=dot*(design===1?9:6);
        a.globalAlpha = design===1 ? .65 : .42; a.drawImage(atlas, 15 * 32, 0, 32, 32, x - glow, y - glow, glow * 2, glow * 2);
        a.globalAlpha = .24+strength*.76; a.fillStyle = strength>.78 ? '#d7ffe6' : '#00e676'; a.beginPath(); a.arc(x, y, dot, 0, TAU); a.fill();
      }
      ring = c.createRadialGradient(centre, centre, radius * .84, centre, centre, radius * 1.035);
      ring.addColorStop(0, 'transparent'); ring.addColorStop(.86, 'rgba(59,167,255,.11)');
      ring.addColorStop(.91, 'rgba(0,230,118,.20)'); ring.addColorStop(1, 'transparent');
      c.fillStyle = ring; c.beginPath(); c.arc(centre, centre, radius * 1.035, 0, TAU); c.fill();
    }
    function draw() {
      if (!alive) return;
      var begun = root.performance.now();
      try {
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, width, width);
        ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = 1;
        ctx.save(); ctx.beginPath(); ctx.arc(centre, centre, width / 2, 0, TAU); ctx.clip();
        ctx.drawImage(background, 0, 0, width, width);
        matrix(q, m); heads.fill(-1); sparkHeads.fill(-1);
        var asleep = state === 'dormant', gain = asleep ? .38 : 1;
        var pulseTime = (clock - pulseStart) / 1.25;
        var pulseAngle = pulseTime * PI / 2;
        for (var k = 0; k < count; k++) {
          var x = xyz[k * 3], y = xyz[k * 3 + 1], z = xyz[k * 3 + 2];
          var xx = m[0] * x + m[1] * y + m[2] * z;
          var yy = m[3] * x + m[4] * y + m[5] * z;
          var zz = m[6] * x + m[7] * y + m[8] * z;
          px[k] = centre + xx * radius; py[k] = centre + yy * radius; pz[k] = zz;
          depth[k] = math.min(15, math.max(0, math.floor((zz + 1) * 7.5)));
          fade[k] = zz > 0 && letterDistance(xx, yy) < .007 ? .35 : 1;
          var boost = 0;
          if (!asleep && !reduced && pulseTime >= 0 && pulseTime < 1 && k < 420 && zz > 0) {
            var band = math.acos(math.min(1, zz)) - pulseAngle;
            boost = math.exp(-band * band / .008) * math.sin(PI * pulseTime) * .9;
          }
          if (!asleep && !reduced) {
            var shimmer = math.max(0, math.sin(clock * 1.7 + k * 2.39996323));
            boost += shimmer * shimmer * shimmer * shimmer * .38 * variation[k];
          }
          brightness[k] = boost;
        }
        for (k = 0; k < edgeA.length; k++) {
          var u = edgeA[k], v = edgeB[k], bin = (depth[u] + depth[v]) >> 1;
          if (fade[u] < 1 || fade[v] < 1) bin += 16;
          edgeNext[k] = heads[bin]; heads[bin] = k;
          if (!asleep && !reduced) {
            var travel = (clock * .45 + edgePhase[k]) % 3;
            if (travel < 1) {
              edgeTravel[k] = travel; sparkNext[k] = sparkHeads[bin]; sparkHeads[bin] = k;
            }
          }
        }
        ctx.globalCompositeOperation = 'lighter'; ctx.lineWidth = math.max(.45, width / 330);
        for (k = 0; k < 32; k++) {
          var color = k % 16;
          ctx.strokeStyle = colors[asleep ? color + 16 : color];
          ctx.globalAlpha = gain * (.045 + color / 15 * .29) * (k < 16 ? 1 : .35);
          ctx.beginPath();
          for (var e = heads[k]; e !== -1; e = edgeNext[e]) {
            ctx.moveTo(px[edgeA[e]], py[edgeA[e]]); ctx.lineTo(px[edgeB[e]], py[edgeB[e]]);
          }
          ctx.stroke();
        }
        if (!asleep && !reduced) {
          ctx.lineWidth = math.max(.65, width / 235);
          for (k = 0; k < 32; k++) {
            color = k % 16; ctx.strokeStyle = colors[color];
            ctx.globalAlpha = (.09 + color / 15 * .48) * (k < 16 ? 1 : .35);
            ctx.beginPath();
            for (e = sparkHeads[k]; e !== -1; e = sparkNext[e]) {
              u = edgeA[e]; v = edgeB[e];
              var from = math.max(0, edgeTravel[e] - .19), to = math.min(1, edgeTravel[e] + .06);
              ctx.moveTo(px[u] + (px[v] - px[u]) * from, py[u] + (py[v] - py[u]) * from);
              ctx.lineTo(px[u] + (px[v] - px[u]) * to, py[u] + (py[v] - py[u]) * to);
            }
            ctx.stroke();
          }
        }
        for (k = 0; k < count; k++) {
          color = depth[k]; var front = (pz[k] + 1) / 2;
          var star = variation[k];
          var r = math.max(.48, width / 160) * (.55 + front * .9) * (.65 + star * .9);
          var glowSize = r * (3.3 + brightness[k] * 2);
          ctx.globalAlpha = math.min(1, gain * (.16 + .68 * front + brightness[k]) * (.35 + star * star * 1.2) * fade[k]);
          var tint = star > .72 ? math.min(math.floor((star-.72)*22),color) : color;
          ctx.drawImage(atlas, (asleep ? tint + 16 : tint) * 32, 0, 32, 32,
            px[k] - glowSize, py[k] - glowSize, glowSize * 2, glowSize * 2);
        }
        if (!asleep && !reduced && pulseTime > 0 && pulseTime < 1) {
          ctx.globalAlpha = math.sin(PI * pulseTime) * .28;
          ctx.strokeStyle = '#9bffca'; ctx.lineWidth = math.max(.65, width / 200);
          ctx.beginPath(); ctx.arc(centre, centre, radius * math.sin(pulseAngle), 0, TAU); ctx.stroke();
        }
        ctx.globalAlpha = asleep ? .58 : 1;
        ctx.drawImage(letter, 0, 0, width, width);
        ctx.restore();
        stats.frameMs = root.performance.now() - begun; stats.frames++;
      } catch (error) { destroy(); }
    }
    function resize() {
      if (!alive) return;
      var newWidth = element.getBoundingClientRect().width || size, newDpr = math.min(2, root.devicePixelRatio || 1);
      if (background && newWidth === width && newDpr === dpr) return;
      width = newWidth; dpr = newDpr; centre = width / 2; radius = width * .465;
      canvas.width = math.round(width * dpr); canvas.height = canvas.width;
      try { staticLayers(); draw(); } catch (error) { destroy(); }
    }
    function pulse() {
      if (!alive || reduced || state === 'dormant') return;
      pulseStart = clock; lastPulse = clock; element.dispatchEvent(pulseEvent); wake();
    }
    function running() { return alive && visible && !doc.hidden && !reduced; }
    function frame(now) {
      var dt = g.t ? math.min(.05, (now - g.t) / 1000) : 0;
      g.t = now; clock += dt; phase += dt * .026;
      var speed=math.sqrt(velocity[0]*velocity[0]+velocity[1]*velocity[1]+velocity[2]*velocity[2]);
      if(!dragging && (!hovering || now-lastMove>80)) {
        if(speed>.002) {
          rotate(q,velocity[0]/speed,velocity[1]/speed,velocity[2]/speed,math.max(.10,speed)*dt*(state==='dormant'?.4:1));
          // Bearing resistance removes excess speed, preserving the spin axis.
          var factor=(.10+math.max(0,speed-.10)*math.exp(-dt/coast))/speed;
          velocity[0]*=factor;velocity[1]*=factor;velocity[2]*=factor;
        } else {
          var cs=math.cos(phase),sn=math.sin(phase);
          rotate(q,axis[0]*cs+axis[2]*sn,axis[1],axis[2]*cs-axis[0]*sn,dt*.10*(state==='dormant'?.4:1));
        }
      }
      if (state === 'live' && clock - lastPulse >= 6) pulse();
      draw();
    }
    function ball(x, y, out) {
      var bx = (x - rect.left - rect.width / 2) / (rect.width / 2);
      var by = (y - rect.top - rect.height / 2) / (rect.height / 2), rr = bx * bx + by * by;
      if (rr > 1) { var scale = 1 / math.sqrt(rr); bx *= scale; by *= scale; }
      out[0] = bx; out[1] = by; out[2] = math.sqrt(math.max(0, 1 - rr));
    }
    function draggable() { return options.interactive !== false && width >= 120; }
    function down(event) {
      if (!draggable() || pointer !== -1 || (event.button !== undefined && event.button !== 0)) return;
      pointer = event.pointerId; dragging = false; pressX = event.clientX; pressY = event.clientY;
      suppressClick = false;
      interaction = lastMove = root.performance.now(); velocity.fill(0);
      rect = canvas.getBoundingClientRect(); ball(pressX, pressY, prev);
    }
    function move(event) {
      if (event.pointerId !== pointer || pointer === -1) return;
      var dx = event.clientX - pressX, dy = event.clientY - pressY;
      if (!dragging) {
        if (dx * dx + dy * dy <= 36) return;
        // Vertical-first touch gestures belong to page scrolling. Once a
        // horizontal gesture starts, the trackball can be turned on any axis.
        if (event.pointerType === 'touch' && math.abs(dy) > math.abs(dx)) { finish(event); return; }
        dragging = true; suppressClick = true;
        try { canvas.setPointerCapture(pointer); } catch (error) { /* old browser */ }
        canvas.style.cursor = 'grabbing';
      }
      if (event.cancelable) event.preventDefault();
      ball(event.clientX, event.clientY, next);
      var x = prev[1] * next[2] - prev[2] * next[1], y = prev[2] * next[0] - prev[0] * next[2];
      var z = prev[0] * next[1] - prev[1] * next[0], length = math.sqrt(x * x + y * y + z * z);
      var dot = math.max(-1, math.min(1, prev[0] * next[0] + prev[1] * next[1] + prev[2] * next[2]));
      var now = root.performance.now(), dt = math.max(.008, (now - lastMove) / 1000);
      var angle = math.atan2(length, dot);
      if (length < .000001 && dot < -.99) {
        // A single event can cross the entire diameter: choose a stable axis
        // perpendicular to the old point for this otherwise ambiguous turn.
        x = -prev[1]; y = prev[0]; z = 0;
        length = math.sqrt(x * x + y * y);
        if (length < .000001) { x = 0; y = -prev[2]; z = prev[1]; length = math.sqrt(y * y + z * z); }
      }
      if (length > .000001) {
        x /= length; y /= length; z /= length;
        rotate(q, x, y, z, angle);
        var speed = math.min(3, angle / dt); velocity[0] = x * speed; velocity[1] = y * speed; velocity[2] = z * speed;
      }
      prev.set(next); interaction = lastMove = now; if (reduced) { velocity.fill(0); draw(); }
      wake();
    }
    function finish(event) {
      if (event.pointerId !== pointer) return;
      if (root.performance.now() - lastMove > 100) velocity.fill(0);
      if (event.type === 'pointercancel' || reduced) velocity.fill(0);
      try { if (canvas.hasPointerCapture(pointer)) canvas.releasePointerCapture(pointer); } catch (error) { /* optional */ }
      pointer = -1; dragging = false; interaction = hovering ? root.performance.now() : -Infinity;
      canvas.style.cursor = draggable() ? 'grab' : ''; haveHover = false; wake();
    }
    function enter(event) {
      if (event.pointerType === 'touch') return;
      hovering = true; hoverX = event.clientX; hoverY = event.clientY; haveHover = true; lastMove=root.performance.now();
    }
    function hoverMove(event) {
      if (event.pointerType === 'touch' || pointer !== -1 || !draggable()) return;
      if (haveHover) {
        var dx = event.clientX - hoverX, dy = event.clientY - hoverY;
        var distance = math.sqrt(dx * dx + dy * dy);
        if (distance > .05) {
          var now=root.performance.now(), angle=math.min(.22,distance/width*1.3);
          rotate(q,-dy/distance,dx/distance,0,angle);
          var speed=math.min(2.8,angle/math.max(.016,(now-lastMove)/1000));
          velocity[0]=velocity[0]*.35-dy/distance*speed*.65;
          velocity[1]=velocity[1]*.35+dx/distance*speed*.65;velocity[2]*=.35;
          interaction=lastMove=now;if(reduced){velocity.fill(0);draw();}wake();
        }
      }
      hoverX = event.clientX; hoverY = event.clientY; haveHover = true;
    }
    function leave() {
      hovering = false; haveHover = false;
      if (pointer === -1) interaction = -Infinity;
      wake();
    }
    function click(event) {
      if (suppressClick) { event.preventDefault(); event.stopPropagation(); suppressClick = false; }
      else if (options.interactive !== false) pulse();
    }
    function key(event) {
      if (options.interactive === false) return;
      var x = 0, y = 0;
      if (event.key === 'ArrowLeft') y = -1; else if (event.key === 'ArrowRight') y = 1;
      else if (event.key === 'ArrowUp') x = -1; else if (event.key === 'ArrowDown') x = 1; else return;
      event.preventDefault(); rotate(q, x, y, 0, 10 * PI / 180); velocity.fill(0);
      interaction = root.performance.now(); draw(); wake();
    }
    function visibility() { g.t = 0; if (running()) wake(); }
    function motion(event) { reduced = event.matches; velocity.fill(0); pulseStart = -10; draw(); visibility(); }
    function destroy() {
      if (!alive) return; alive = false;
      var at = instances.indexOf(g); if (at >= 0) instances.splice(at, 1);
      if (!instances.length && raf) { root.cancelAnimationFrame(raf); raf = 0; }
      if (observer) observer.disconnect(); if (resizer) resizer.disconnect();
      doc.removeEventListener('visibilitychange', visibility); root.removeEventListener('resize', resize);
      root.removeEventListener('pointermove', move); root.removeEventListener('pointerup', finish);
      root.removeEventListener('pointercancel', finish);
      canvas.removeEventListener('pointerdown', down); canvas.removeEventListener('pointerenter', enter);
      canvas.removeEventListener('pointermove', hoverMove); canvas.removeEventListener('pointerleave', leave);
      canvas.removeEventListener('click', click, true); canvas.removeEventListener('keydown', key);
      if (query && options.reducedMotion === undefined) {
        if (query.removeEventListener) query.removeEventListener('change', motion); else if (query.removeListener) query.removeListener(motion);
      }
      if (canvas.parentNode) canvas.parentNode.removeChild(canvas);
      for (var k = 0; k < fallbacks.length; k++) {
        fallbacks[k].hidden = hidden[k]; fallbacks[k].style.visibility = imageVisibility[k];
      }
      element.style.position = prior.position; element.style.width = prior.width; element.style.height = prior.height;
    }
    var observer = null, resizer = null;
    // t is the scheduler's last frame timestamp (milliseconds).
    var g = { t: 0, running: running, frame: frame, stats: stats,
      setState: function (value) { state = value === 'dormant' ? 'dormant' : 'live'; pulseStart = -10; lastPulse = clock; draw(); wake(); },
      pulse: pulse,
      setResistance: function(seconds){coast=math.max(.6,math.min(10,Number(seconds)||4));},
      setAxis: function (value) {
        if (!alive || !value || value.length !== 3) return;
        var length = math.sqrt(value[0] * value[0] + value[1] * value[1] + value[2] * value[2]);
        if (!isFinite(length) || length === 0) return;
        axis[0] = value[0] / length; axis[1] = value[1] / length; axis[2] = value[2] / length; velocity.fill(0);
      }, destroy: destroy };
    canvas.setAttribute('aria-label', 'Agent Hub'); canvas.setAttribute('role', 'img');
    canvas.tabIndex = options.interactive !== false ? 0 : -1;
    canvas.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;border-radius:50%;touch-action:pan-y;';
    canvas.style.cursor = options.interactive !== false && size >= 120 ? 'grab' : '';
    if (root.getComputedStyle(element).position === 'static') element.style.position = 'relative';
    if (!element.getBoundingClientRect().width) { element.style.width = size + 'px'; element.style.height = size + 'px'; }
    element.appendChild(canvas); instances.push(g); resize();
    if (!alive) return null;
    // Do not hide the raster until a complete frame has succeeded.
    for (i = 0; i < fallbacks.length; i++) { fallbacks[i].hidden = true; fallbacks[i].style.visibility = 'hidden'; }
    canvas.addEventListener('pointerdown', down); canvas.addEventListener('pointerenter', enter);
    canvas.addEventListener('pointermove', hoverMove); canvas.addEventListener('pointerleave', leave);
    canvas.addEventListener('click', click, true); canvas.addEventListener('keydown', key);
    root.addEventListener('pointermove', move, { passive: false }); root.addEventListener('pointerup', finish);
    root.addEventListener('pointercancel', finish); doc.addEventListener('visibilitychange', visibility);
    root.addEventListener('resize', resize);
    if (root.IntersectionObserver) {
      observer = new root.IntersectionObserver(function (entries) { visible = entries[0].isIntersecting; visibility(); });
      observer.observe(element);
    }
    if (root.ResizeObserver) { resizer = new root.ResizeObserver(resize); resizer.observe(element); }
    if (query && options.reducedMotion === undefined) {
      if (query.addEventListener) query.addEventListener('change', motion); else if (query.addListener) query.addListener(motion);
    }
    wake(); return g;
  }
  root.AgentHubGlobeIdeas = { mount: mount };
  // Node-only exports use the very same rotation implementation as the globe.
  if (typeof module !== 'undefined' && module.exports) module.exports = { rotate: rotate, matrix: matrix };
})(typeof window !== 'undefined' ? window : globalThis);

