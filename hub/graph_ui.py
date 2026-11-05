"""Project status graph page (Phase 4).

One node per PROJECT (never per file) — see hub/agent_knowledge/status.py for
the state model and hub/features/graph.py for the API it reads. Clicking a
node opens a git-desktop-style detail panel (changed-file list + diff view)
in place; it never explodes the graph into extra file nodes.
"""
from __future__ import annotations

from pathlib import Path as _PhonePath

from aiohttp import web
from .embed import embedded

routes = web.RouteTableDef()

_GRAPH_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#080c28">
<title>AGENT HUB — Project Graph</title>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600&family=Orbitron:wght@400;700;900&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --accent:#00e676;--text:rgba(0,230,118,0.90);--text-muted:rgba(0,230,118,0.52);
  --red:#e2544a;--green:#00e676;--blue:#5b9bf5;--amber:#f5c842;--cyan:#00e8ff;
  --grey:#7c8797;--orange:#ef9f27;
  --panel:rgba(11,14,26,.92);--border:#2a2e44;
}
html{height:100%;min-height:100dvh;background:#000}
html,body{min-height:100%;min-height:100dvh;font-family:'Outfit',system-ui,sans-serif;color:var(--text);overflow:hidden}
body{background:#000}

/* Header keeps the Hub's own blue/purple gradient — the graph body below it
   is plain black, so the graph is boxed to ITS OWN area (top:56px on the
   SVG below) and never renders up through/behind this bar. */
header{position:fixed;top:0;left:0;right:0;z-index:20;height:calc(56px + env(safe-area-inset-top));display:flex;align-items:center;gap:14px;
  padding:env(safe-area-inset-top) 20px 0;border-bottom:1px solid rgba(0,230,118,.14);
  background:linear-gradient(150deg,#080c28 0%,#0d1050 45%,#18095c 100%)}
.brand{font-family:'Orbitron',monospace;font-size:16px;font-weight:900;color:var(--accent);letter-spacing:3px}
.back-link{margin-left:auto;font-family:'Orbitron',monospace;font-size:11px;letter-spacing:1.5px;
  color:var(--text-muted);text-decoration:none;padding:11px 16px;min-height:40px;display:inline-flex;align-items:center;
  border:1px solid rgba(0,230,118,.28);border-radius:8px;transition:color .15s,border-color .15s;
  -webkit-tap-highlight-color:transparent;flex-shrink:0}
.back-link:hover{color:var(--accent);border-color:var(--accent)}
#panel-chat .chat-btn{min-height:40px}

svg#graph{position:fixed;top:calc(56px + env(safe-area-inset-top));left:0;right:0;bottom:0;width:100%;height:calc(100% - 56px - env(safe-area-inset-top));
  cursor:grab;background:#000}
svg#graph:active{cursor:grabbing}
.ngrp{cursor:pointer}
.ngrp .n-dot{transition:transform .15s;transform-box:fill-box;transform-origin:center}
.ngrp:hover .n-dot{transform:scale(1.37)}
svg#graph{touch-action:none}
#copies-toggle{display:block;margin-top:10px;width:100%;min-height:34px;background:transparent;color:var(--text-muted);border:1px dashed rgba(176,124,214,.55);border-radius:6px;font:700 9px 'Orbitron',monospace;letter-spacing:1px;cursor:pointer}
#copies-toggle:hover{color:var(--accent);border-color:var(--accent)}
.ngrp text{font-family:'Outfit',sans-serif;font-weight:500;pointer-events:none;text-anchor:middle}
.cgrp text{font-family:'Orbitron',monospace;font-size:10px;letter-spacing:1.5px;pointer-events:none;text-anchor:middle;fill:var(--cyan);fill-opacity:.75}
.edge{fill:none}
#tt{position:fixed;z-index:40;display:none;background:var(--panel);border:1px solid var(--border);
  border-radius:6px;padding:6px 10px;font-size:11.5px;pointer-events:none;white-space:nowrap}

#legend{position:fixed;top:70px;right:20px;z-index:20;background:var(--panel);border:1px solid var(--border);
  border-radius:10px;padding:14px 16px;width:206px;font-size:12px}
#legend .title{font-family:'Orbitron',monospace;font-size:10px;letter-spacing:1.5px;color:var(--text-muted);margin-bottom:10px}
#legend .row{display:flex;align-items:center;gap:10px;margin:7px 0}
#legend .dot{width:12px;height:12px;border-radius:50%;flex-shrink:0}
#legend .ring{box-shadow:0 0 0 2.5px var(--r) inset}

#panel{position:fixed;top:0;right:0;bottom:0;width:420px;max-width:92vw;z-index:30;
  background:var(--panel);border-left:1px solid var(--border);
  transform:translateX(100%);transition:transform .22s ease;overflow-y:auto;padding:24px 22px}
#panel.open{transform:translateX(0)}
#panel .close{position:absolute;top:18px;right:18px;background:transparent;border:none;color:var(--text-muted);
  font-size:20px;cursor:pointer;line-height:1}
#panel .close:hover{color:var(--accent)}
#panel h2{font-family:'Orbitron',monospace;font-size:15px;letter-spacing:1px;margin-bottom:6px;padding-right:30px}
#panel .state-badge{display:inline-block;font-family:'Orbitron',monospace;font-size:10px;letter-spacing:1px;
  padding:3px 10px;border-radius:999px;margin-bottom:18px}
#panel .path{font-size:11px;color:var(--text-muted);word-break:break-all;margin-bottom:18px}
#panel .file-row{display:flex;align-items:center;gap:10px;padding:9px 10px;border-radius:6px;cursor:pointer;
  font-size:12.5px;transition:background .12s}
#panel .file-row:hover{background:rgba(0,230,118,.08)}
#panel .file-row.active{background:rgba(0,230,118,.14)}
#panel .badge{font-family:'Orbitron',monospace;font-size:9px;width:16px;height:16px;border-radius:4px;
  display:flex;align-items:center;justify-content:center;flex-shrink:0}
#panel .badge.A{background:rgba(99,153,34,.25);color:#c0dd97}
#panel .badge.M{background:rgba(55,138,221,.25);color:#85b7eb}
#panel .badge.D{background:rgba(226,75,74,.25);color:#f09595}
#panel .empty{color:var(--text-muted);font-size:12.5px;padding:12px 0}
#panel-connections{font-size:11.5px;color:var(--text-muted);margin-bottom:14px;line-height:1.6}
#panel-connections .conn-title{font-family:'Orbitron',monospace;font-size:9.5px;letter-spacing:1px;
  color:var(--text-muted);margin-bottom:4px}
#panel-connections a.conn-link{color:#5dcaa5;text-decoration:none;cursor:pointer}
#panel-connections a.conn-link:hover{text-decoration:underline}
#panel-connections a.conn-link.related{color:#b87bff}
#panel-skills{font-size:11.5px;color:var(--text-muted);margin-bottom:16px;line-height:1.7}
#panel-skills .sk-title{font-family:'Orbitron',monospace;font-size:9.5px;letter-spacing:1px;color:var(--text-muted);margin-bottom:7px}
#panel-skills .sk-tag{display:inline-block;background:rgba(0,232,255,.12);border:1px solid rgba(0,232,255,.30);color:#8fe6f2;border-radius:4px;padding:2px 7px;margin:2px 4px 2px 0;font-size:10.5px;cursor:default}
#panel-skills .sk-tag.wiki{background:rgba(184,123,255,.12);border-color:rgba(184,123,255,.32);color:#c8a8ff}
#panel-skills .sk-tag.vend{background:rgba(245,200,66,.12);border-color:rgba(245,200,66,.32);color:#f0d68a}
#panel-skills .sk-muted{opacity:.85}
#panel-chat{margin-bottom:16px}
#panel-chat .chat-row{display:flex;align-items:center;justify-content:space-between;gap:10px;
  padding:9px 10px;border-radius:6px;font-size:12.5px;background:rgba(0,230,118,.05);margin-bottom:6px}
#panel-chat .chat-btn{font-family:'Orbitron',monospace;font-size:9px;letter-spacing:.5px;padding:5px 10px;
  border-radius:6px;background:rgba(0,230,118,.14);color:var(--accent);border:1px solid rgba(0,230,118,.35);
  cursor:pointer;flex-shrink:0}
#panel-chat .chat-btn:hover{background:rgba(0,230,118,.24)}
#panel-chat .chat-btn.new{width:100%;padding:10px;margin-top:2px}
#panel .file-row{justify-content:space-between}
#panel .file-left{display:flex;align-items:center;gap:10px;overflow:hidden}
#panel .file-left span:last-child{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.push-btn{font-family:'Orbitron',monospace;font-size:9px;letter-spacing:.5px;padding:4px 9px;border-radius:6px;
  background:rgba(0,230,118,.12);color:var(--accent);border:1px solid rgba(0,230,118,.3);cursor:pointer;flex-shrink:0}
.push-btn:hover{background:rgba(0,230,118,.22)}
.push-btn:disabled{opacity:.35;cursor:default}
.push-btn.conflict{background:rgba(239,159,39,.15);color:var(--orange);border-color:rgba(239,159,39,.4)}
#push-all{width:100%;margin-top:16px;font-family:'Orbitron',monospace;font-size:11px;letter-spacing:1px;
  padding:11px;border-radius:8px;background:rgba(0,230,118,.14);color:var(--accent);
  border:1px solid rgba(0,230,118,.35);cursor:pointer}
#push-all:hover{background:rgba(0,230,118,.24)}
#push-status{font-size:11.5px;color:var(--text-muted);margin-top:10px;white-space:pre-wrap}
.del-note{font-size:11px;color:var(--text-muted);padding:6px 10px;font-style:italic}
#diff-view{margin-top:16px;background:#05060f;border:1px solid var(--border);border-radius:8px;padding:12px;
  font-family:'Courier New',monospace;font-size:11.5px;white-space:pre-wrap;word-break:break-all;max-height:38vh;overflow-y:auto;display:none}
#diff-view.show{display:block}
.diff-add{color:#97c459}
.diff-del{color:#f09595}
#loading{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;
  font-family:'Orbitron',monospace;font-size:12px;letter-spacing:2px;color:var(--text-muted)}
@media (max-width:520px){header{gap:8px;padding-left:12px;padding-right:12px}.brand{font-size:11px;letter-spacing:1.5px}.back-link{padding:9px 11px;font-size:10px;min-height:36px}}
</style>
<link rel="stylesheet" href="/theme.css">
</head>
<body>
<header>
  <div class="brand">PROJECT GRAPH</div>
  <a class="back-link" href="/">&larr; HUB</a>
</header>

<div id="loading">LOADING GRAPH&hellip;</div>
<svg id="graph"></svg>
<div id="tt"></div>

<div id="legend">
  <div class="title">STATUS</div>
  <div class="row"><span class="dot" style="background:var(--red)"></span>read-only</div>
  <div class="row"><span class="dot" style="background:var(--blue)"></span>available (no chat yet)</div>
  <div class="row"><span class="dot" style="background:var(--amber)"></span>has diff (WIP)</div>
  <div class="row"><span class="dot" style="background:var(--green)"></span>in sync (clean)</div>
  <div class="row"><span class="dot ring" style="background:var(--amber);--r:var(--green)"></span>ready to push</div>
  <div class="row"><span class="dot ring" style="background:var(--amber);--r:var(--orange)"></span>needs update</div>
  <div class="row"><span class="dot" style="background:#b07cd6"></span>orphan worktree (source gone)</div>
  <div class="row"><span class="dot" style="background:var(--grey)"></span>read-only / local cluster</div>
  <div class="row" style="margin-top:4px"><span style="width:16px;height:0;border-top:1.5px dotted #ffffff;flex-shrink:0"></span>documented in wiki</div>
  <div class="row"><span style="width:16px;height:0;border-top:1.5px solid #6a3fd1;flex-shrink:0"></span>related project (wiki link)</div>
  <button type="button" id="copies-toggle" hidden></button>
</div>

<div id="panel">
  <button class="close" id="panel-close" aria-label="Close">&times;</button>
  <h2 id="panel-title"></h2>
  <div id="panel-badge"></div>
  <div class="path" id="panel-path"></div>
  <div id="panel-connections"></div>
  <div id="panel-skills"></div>
  <div id="panel-chat"></div>
  <div id="panel-files"></div>
  <div id="diff-view"></div>
  <button id="push-all" style="display:none">Push all reviewed changes</button>
  <div id="push-status"></div>
</div>

<script>
// Color meaning (confirmed 2026-08-15): blue = available/potential (no chat
// opened yet for this project) — NOT "has changes". amber/gold = has a diff,
// matching agent-core's own convention where gold marks active tool/LLM work.
// green = in sync/clean (a chat exists and there's nothing pending). red =
// read-only (a node OpenCode can only ever chat against read-only, never
// modify — so it never gets a diff, never gets a ring; that's not a special
// case, it falls out of the state model on its own). Rings (ready-to-push /
// needs-update) sit on amber nodes only.
// Grey is reserved for the READ-ONLY / LOCAL CLUSTER-HUB circles only — the
// category descriptor, not the member nodes themselves.
const COLORS = {red:'#e2544a', blue:'#5b9bf5', amber:'#f5c842', green:'#00e676', unknown:'#888780', orphan:'#b07cd6'};
const RING_COLORS = {green:'#97c459', orange:'#ef9f27'};   // ready-to-push / needs-update
const CLUSTER_COLOR = '#00e8ff';
const CLUSTER_COLOR_GREY = '#7c8797';
const GREY_CLUSTERS = new Set(['Read-only', 'Local', 'Orphans']);
const CLUSTER_ORDER = ['My Repo', 'Collab Projects', '_unsorted projects', 'Open Source', 'Read-only', 'Local', 'Orphans'];
const CLUSTER_LABEL = {
  'My Repo': 'MY REPO', 'Collab Projects': 'COLLAB PROJECTS',
  '_unsorted projects': 'UNSORTED', 'Open Source': 'OPEN SOURCE', 'Read-only': 'READ-ONLY',
  'Local': 'LOCAL', 'Orphans': 'ORPHAN WORKTREES',
};

let graphData = {nodes: [], projectLinks: []};
let currentSlug = null;

document.getElementById('copies-toggle').onclick = () => { showCopies = !showCopies; render(); };

async function loadGraph() {
  const res = await fetch('/api/graph');
  const data = await res.json();
  graphData.nodes = data.nodes;
  graphData.projectLinks = data.project_links || [];
  document.getElementById('loading').style.display = 'none';
  render();
}

// Deterministic per-edge curvature (same hashing trick as agent-core's
// web_ui.py) so branches fan out organically instead of as straight spokes,
// and the same pair always curves the same way.
function edgeSign(a, b) {
  let h = 0; const s = a < b ? a + b : b + a;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) & 0xffff;
  return (h & 1) ? 1 : -1;
}

function bezierPath(src, tgt, curveK) {
  const dx = tgt.x - src.x, dy = tgt.y - src.y;
  const len = Math.hypot(dx, dy) || 1;
  const curv = len * curveK;
  const mx = (src.x + tgt.x) / 2 - (dy / len) * curv;
  const my = (src.y + tgt.y) / 2 + (dx / len) * curv;
  return `M ${src.x} ${src.y} Q ${mx} ${my} ${tgt.x} ${tgt.y}`;
}

// Category-clustered radial layout — deterministic, never a physics
// simulation flinging nodes into corners. Cluster centers ring the canvas
// center; each cluster's own members ring their cluster center, with the
// per-cluster radius sized to the member count so labels don't collide.
function layoutGraph(nodes) {
  const byCat = new Map();
  nodes.forEach(n => { const c = n.category || 'Other'; if (!byCat.has(c)) byCat.set(c, []); byCat.get(c).push(n); });
  const rank = c => { const i = CLUSTER_ORDER.indexOf(c); return i < 0 ? CLUSTER_ORDER.length : i; };
  const cats = Array.from(byCat.keys()).sort((a, b) => rank(a) - rank(b));

  const clusters = cats.map(cat => {
    const members = byCat.get(cat);
    const minArc = 96; // px of arc length per member, keeps labels apart
    const orbitR = Math.max(64, members.length * minArc / (2 * Math.PI));
    return {cat, members, orbitR};
  });

  const clusterOrbit = Math.max(300, Math.max(...clusters.map(c => c.orbitR)) * 2.1 + 240);
  const n = clusters.length;
  clusters.forEach((c, i) => {
    const angle = (i / n) * 2 * Math.PI - Math.PI / 2;
    c.x = Math.cos(angle) * clusterOrbit;
    c.y = Math.sin(angle) * clusterOrbit * 0.78;
  });

  const clusterNodes = clusters.map(c => ({
    id: 'cluster::' + c.cat, cat: c.cat, label: CLUSTER_LABEL[c.cat] || c.cat, x: c.x, y: c.y, isCluster: true,
  }));

  clusters.forEach(c => {
    c.members.forEach((m, j) => {
      const angle = (j / c.members.length) * 2 * Math.PI - Math.PI / 2;
      m.x = c.x + Math.cos(angle) * c.orbitR;
      m.y = c.y + Math.sin(angle) * c.orbitR;
      m._clusterId = 'cluster::' + c.cat;
    });
  });

  return clusterNodes;
}

// No library and no SVG filters: the page used to wait for d3 from a CDN and then blur every node on every
// pan frame. Edges are three paths (not ~110 elements), the glow is a translucent circle, and pan/zoom moves one group.
const SVGNS = 'http://www.w3.org/2000/svg';
function mk(tag, attrs, parent) {
  const e = document.createElementNS(SVGNS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  if (parent) parent.appendChild(e);
  return e;
}

const view = {x: 0, y: 0, k: 1};
let viewRoot = null, viewQueued = false, dragMoved = false;
const copyCount = () => graphData.nodes.filter(n => n.category === 'Missions').length;
function paintView() {
  viewQueued = false;
  if (viewRoot) viewRoot.setAttribute('transform', `translate(${view.x} ${view.y}) scale(${view.k})`);
}
function queueView() { if (!viewQueued) { viewQueued = true; requestAnimationFrame(paintView); } }
function zoomAt(px, py, factor) {
  const k = Math.min(3, Math.max(0.3, view.k * factor)), r = k / view.k;
  view.x = px - (px - view.x) * r; view.y = py - (py - view.y) * r; view.k = k;
  queueView();
}
function bindViewControls(svg) {
  if (svg._bound) return;
  svg._bound = true;
  const ptrs = new Map();
  let last = 0;
  const top = () => svg.getBoundingClientRect().top;
  svg.addEventListener('pointerdown', e => {
    ptrs.set(e.pointerId, {x: e.clientX, y: e.clientY, sx: e.clientX, sy: e.clientY});
    dragMoved = false; last = 0;
    if (ptrs.size === 2) { const [a, b] = [...ptrs.values()]; last = Math.hypot(a.x - b.x, a.y - b.y); }
  });
  svg.addEventListener('pointermove', e => {
    const p = ptrs.get(e.pointerId);
    if (!p) return;
    const dx = e.clientX - p.x, dy = e.clientY - p.y;
    p.x = e.clientX; p.y = e.clientY;
    if (ptrs.size === 1) {
      if (!dragMoved && Math.hypot(e.clientX - p.sx, e.clientY - p.sy) < 4) return;
      if (!dragMoved) { dragMoved = true; try { svg.setPointerCapture(e.pointerId); } catch (x) {} }
      view.x += dx; view.y += dy; queueView();
    } else if (ptrs.size === 2) {
      const [a, b] = [...ptrs.values()], d = Math.hypot(a.x - b.x, a.y - b.y);
      dragMoved = true;
      if (last) zoomAt((a.x + b.x) / 2, (a.y + b.y) / 2 - top(), d / last);
      last = d;
    }
  });
  const up = e => { ptrs.delete(e.pointerId); last = 0; setTimeout(() => { if (!ptrs.size) dragMoved = false; }, 0); };
  svg.addEventListener('pointerup', up);
  svg.addEventListener('pointercancel', up);
  svg.addEventListener('wheel', e => {
    e.preventDefault();
    zoomAt(e.clientX, e.clientY - top(), Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015)));
  }, {passive: false});
}

function paintCopiesToggle() {
  const b = document.getElementById('copies-toggle'), n = copyCount();
  if (!b) return;
  b.hidden = !n;
  b.textContent = showCopies ? `HIDE ${n} MISSION COPIES` : `SHOW ${n} MISSION COPIES`;
}
let showCopies = false;

function render() {
  const svg = document.getElementById('graph');
  svg.textContent = '';
  bindViewControls(svg);
  const width = window.innerWidth, height = window.innerHeight;
  const nodes = graphData.nodes.filter(n => showCopies || n.category !== 'Missions');
  paintCopiesToggle();

  const root = mk('g', {id: 'graph-root'}, svg);
  viewRoot = root;
  const edgeLyr = mk('g', {}, root);
  const nodeLyr = mk('g', {}, root);

  const clusterNodes = layoutGraph(nodes);
  const clusterById = new Map(clusterNodes.map(c => [c.id, c]));

  // ── Edges: each project -> its cluster centre (curved), the wiki-documented project -> LLM Wiki, and real wikilinks between projects ──
  const edgePath = (cls, d, stroke, opacity, width, dash) => d && mk('path', {
    class: cls, d, fill: 'none', stroke, 'stroke-opacity': opacity, 'stroke-width': width, ...(dash ? {'stroke-dasharray': dash} : {})}, edgeLyr);
  edgePath('edge', nodes.map(m => { const t = clusterById.get(m._clusterId); return t ? bezierPath(m, t, edgeSign(m.slug, t.id) * 0.16) : ''; }).join(' '),
    '#ffffff', 0.18, 0.75, '1,3');

  // Absence of a wiki edge is the point: a visible "undocumented" signal, not a missing decoration.
  const wikiNode = nodes.find(n => n.slug === 'llm-wiki');
  if (wikiNode) {
    edgePath('wiki-edge', nodes.filter(n => n.wiki_entity && n.slug !== 'llm-wiki')
      .map(n => bezierPath(n, wikiNode, edgeSign(n.slug, 'llm-wiki') * 0.1)).join(' '), '#ffffff', 0.32, 0.9, '1,3');
  }

  // Real [[wikilinks]] between two projects' own wiki pages: solid and brighter, documented relationships.
  const bySlug = new Map(nodes.map(n => [n.slug, n]));
  edgePath('project-edge', graphData.projectLinks.map(l => ({src: bySlug.get(l.a), tgt: bySlug.get(l.b)})).filter(e => e.src && e.tgt)
    .map(e => bezierPath(e.src, e.tgt, edgeSign(e.src.slug, e.tgt.slug) * 0.13)).join(' '), '#6a3fd1', 0.55, 1);

  // ── Cluster hub nodes ──
  clusterNodes.forEach(c => {
    const col = GREY_CLUSTERS.has(c.cat) ? CLUSTER_COLOR_GREY : CLUSTER_COLOR;
    const g = mk('g', {class: 'cgrp', transform: `translate(${c.x},${c.y})`}, nodeLyr);
    mk('circle', {r: 22, fill: col, 'fill-opacity': 0.12}, g);
    mk('circle', {r: 16, fill: 'none', stroke: col, 'stroke-width': 1.2, opacity: 0.28}, g);
    mk('circle', {r: 13, fill: col, 'fill-opacity': 0.85, stroke: col, 'stroke-opacity': 0.6, 'stroke-width': 1}, g);
    mk('text', {dy: 30}, g).textContent = c.label;
  });

  // ── Project nodes ──
  const tt = document.getElementById('tt');
  nodes.forEach(d => {
    const col = COLORS[d.state] || COLORS.unknown;
    const g = mk('g', {class: 'ngrp', transform: `translate(${d.x},${d.y})`}, nodeLyr);
    mk('circle', {r: 15, fill: col, 'fill-opacity': 0.16}, g);                       // the glow: no blur filter
    mk('circle', {class: 'n-ring', r: 11, fill: 'none', stroke: col, 'stroke-width': 0.8, opacity: 0.12}, g);
    mk('circle', {class: 'n-dot', r: 8, fill: col, 'fill-opacity': 0.85,
      stroke: d.ring ? RING_COLORS[d.ring] : col, 'stroke-width': d.ring ? 3 : 1, 'stroke-opacity': d.ring ? 1 : 0.6}, g);
    mk('text', {dy: 22, 'font-size': 10.5, fill: col, 'fill-opacity': 0.7}, g).textContent = d.name.length > 20 ? d.name.slice(0, 18) + '…' : d.name;
    g.addEventListener('click', () => { if (!dragMoved) openPanel(d); });
    g.addEventListener('mouseover', () => { tt.textContent = `${d.name} — ${d.category || ''}`; tt.style.display = 'block'; });
    g.addEventListener('mousemove', e => { tt.style.left = (e.clientX + 14) + 'px'; tt.style.top = (e.clientY - 8) + 'px'; });
    g.addEventListener('mouseout', () => { tt.style.display = 'none'; });
  });

  // ── Fit whatever the layout produced into the window ──
  const all = [...clusterNodes, ...nodes];
  const xs = all.map(d => d.x), ys = all.map(d => d.y);
  const minX = Math.min(...xs) - 80, maxX = Math.max(...xs) + 80, minY = Math.min(...ys) - 80, maxY = Math.max(...ys) + 80;
  const fit = Math.min(width / (maxX - minX), (height - 56) / (maxY - minY), 1.1);
  view.k = fit;
  view.x = width / 2 - fit * (minX + maxX) / 2;
  view.y = (height - 56) / 2 - fit * (minY + maxY) / 2;
  paintView();
}

function renderConnections(d) {
  const el = document.getElementById('panel-connections');
  const parts = [];

  if (d.slug === 'llm-wiki') {
    const documented = graphData.nodes.filter(n => n.wiki_entity && n.slug !== 'llm-wiki');
    if (documented.length) {
      const links = documented.map(n =>
        `<a class="conn-link" data-slug="${n.slug}">${n.name}</a>`).join(', ');
      parts.push(`<div class="conn-title">DOCUMENTS ${documented.length} PROJECT${documented.length === 1 ? '' : 'S'}</div><div>${links}</div>`);
    }
  } else {
    const related = graphData.projectLinks
      .filter(l => l.a === d.slug || l.b === d.slug)
      .map(l => l.a === d.slug ? l.b : l.a);
    if (related.length) {
      const links = related.map(slug => {
        const n = graphData.nodes.find(x => x.slug === slug);
        return `<a class="conn-link related" data-slug="${slug}">${n ? n.name : slug}</a>`;
      }).join(', ');
      parts.push(`<div class="conn-title">RELATED PROJECTS</div><div>${links}</div>`);
    }
  }

  el.innerHTML = parts.join('');
  el.querySelectorAll('a.conn-link').forEach(a => {
    a.onclick = () => {
      const n = graphData.nodes.find(x => x.slug === a.dataset.slug);
      if (n) openPanel(n);
    };
  });
}

// orphan worktree (source folder gone / never a tracked project): drive it by
// the opencode slug via /api/opencode/folders/, not /api/graph/ (which 404s).
function _isOrphan(d) { return d && d.state === 'orphan'; }
function _detailBase(slug) {
  const n = graphData.nodes.find(x => x.slug === slug);
  return _isOrphan(n) ? `/api/opencode/folders/${encodeURIComponent(slug)}`
                      : `/api/graph/${encodeURIComponent(slug)}`;
}

async function renderOrphanControls(d) {
  const el = document.getElementById('panel-chat');
  const missing = d.source_missing
    ? '<span style="color:#e0a53c"> — source folder not found</span>' : '';
  el.innerHTML =
    `<div class="chat-row"><span style="color:var(--text-muted)">origin: ${d.origin || 'unknown'}${missing}</span></div>` +
    `<button class="chat-btn new" id="orphan-open">OPEN WORKTREE</button>` +
    `<button class="chat-btn" id="orphan-remove" style="border-color:rgba(255,92,92,.5);color:#ff6b6b">REMOVE WORKTREE</button>`;
  el.querySelector('#orphan-open').onclick = async () => {
    const b = el.querySelector('#orphan-open'); b.disabled = true; b.textContent = 'OPENING…';
    try {
      const r = await fetch(`/api/opencode/folders/${encodeURIComponent(d.slug)}/open`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({mode: 'autonomous'}),
      });
      if (!r.ok) throw new Error(await r.text());
      window.open('/agents?slug=' + encodeURIComponent(d.slug), 'oc-' + d.slug);
    } catch (e) { alert('Open failed: ' + e.message); }
    b.disabled = false; b.textContent = 'OPEN WORKTREE';
  };
  el.querySelector('#orphan-remove').onclick = async () => {
    if (!confirm(`Remove worktree "${d.slug}"?\\n\\nDeletes ${d.worktree} and its chat history. Cannot be undone.`)) return;
    await fetch(`/api/opencode/sessions/${encodeURIComponent(d.slug)}?purge=1`, {method: 'DELETE'});
    const g = await (await fetch('/api/graph')).json();
    graphData.nodes = g.nodes; graphData.projectLinks = g.project_links || [];
    document.getElementById('panel').classList.remove('open');
    render();
  };
}

async function renderChatControls(d) {
  const el = document.getElementById('panel-chat');
  if (d.readonly) { el.innerHTML = ''; return; }
  if (_isOrphan(d)) { await renderOrphanControls(d); return; }

  el.innerHTML = `<button class="chat-btn new" id="dispatch-btn">DISPATCH A MISSION →</button>`;
  document.getElementById('dispatch-btn').onclick = () => {
    location.href = '/missions?project=' + encodeURIComponent(d.slug);
  };
}

async function openPanel(d) {
  currentSlug = d.slug;
  document.getElementById('panel-title').textContent = d.name;
  document.getElementById('panel-path').textContent = d.path;
  document.getElementById('diff-view').classList.remove('show');
  document.getElementById('diff-view').textContent = '';

  const badge = document.getElementById('panel-badge');
  const STATE_LABEL = {red:'READ-ONLY', blue:'AVAILABLE', amber:'HAS DIFF', green:'IN SYNC', unknown:'UNKNOWN', orphan:'ORPHAN'};
  const stateLabel = STATE_LABEL[d.state] || 'UNKNOWN';
  const wikiNote = d.wiki_entity
    ? `<span style="color:#5dcaa5;margin-left:8px">documented — ${d.wiki_entity}</span>`
    : `<span style="color:var(--text-muted);margin-left:8px">no wiki page yet</span>`;
  badge.innerHTML = `<span class="state-badge" style="background:${COLORS[d.state]}22;color:${COLORS[d.state]}">${stateLabel}</span>${wikiNote}`;

  renderConnections(d);
  renderSkills(d);

  const filesEl = document.getElementById('panel-files');
  const pushAllBtn = document.getElementById('push-all');
  const pushStatus = document.getElementById('push-status');
  pushAllBtn.style.display = 'none';
  pushStatus.textContent = '';
  filesEl.innerHTML = '<div class="empty">Loading…</div>';
  document.getElementById('panel').classList.add('open');

  if (d.readonly) {
    document.getElementById('panel-chat').innerHTML = '';
    filesEl.innerHTML = '<div class="empty">Read-only — OpenCode never modifies this project.</div>';
    return;
  }

  renderChatControls(d);
  const detail = await fetchDetail(d.slug);
  renderFiles(d.slug, detail);
}

async function fetchDetail(slug) {
  const n = graphData.nodes.find(x => x.slug === slug);
  if (_isOrphan(n)) {
    const res = await fetch(`/api/opencode/folders/${encodeURIComponent(slug)}/changes`);
    return res.json();      // {changed_files, origin}
  }
  const res = await fetch(`/api/graph/${encodeURIComponent(slug)}`);
  return res.json();
}

async function renderSkills(d) {
  const el = document.getElementById('panel-skills');
  el.innerHTML = '';
  let data;
  try {
    data = await (await fetch('/api/graph/skills?project=' + encodeURIComponent(d.slug))).json();
  } catch (e) { return; }
  const relevant = new Set(data.relevant || []);
  const skills = data.skills || [];
  const wikiCount = skills.filter(s => s.origin === 'wiki-concept').length;
  const vendCount = skills.filter(s => s.origin === 'vendored').length;
  const rel = skills.filter(s => relevant.has(s.name));
  let html = '<div class="sk-title">SKILLS &middot; ' + data.count + ' via the skill tool';
  if (vendCount) html += ' &middot; ' + vendCount + ' vendored (Anthropic)';
  if (wikiCount) html += ' &middot; ' + wikiCount + ' from the wiki';
  html += '</div>';
  if (rel.length) {
    html += rel.map(s => {
      const cls = s.origin === 'wiki-concept' ? 'sk-tag wiki'
                : s.origin === 'vendored' ? 'sk-tag vend' : 'sk-tag';
      const tip = (s.description || '').split('"').join('&quot;');
      return '<span class="' + cls + '" title="' + tip + '">' + s.name + '</span>';
    }).join('');
  } else {
    html += '<span class="sk-muted">no project-specific matches &mdash; all ' + data.count + ' are available on demand</span>';
  }
  el.innerHTML = html;
}

function renderFiles(slug, detail) {
  const filesEl = document.getElementById('panel-files');
  const pushAllBtn = document.getElementById('push-all');
  if (!detail.changed_files || detail.changed_files.length === 0) {
    const node = graphData.nodes.find(n => n.slug === slug);
    filesEl.innerHTML =
      node && node.state === 'orphan' ? '<div class="empty">No changes on this worktree.</div>'
      : node && node.state === 'blue' ? '<div class="empty">No chat opened for this project yet.</div>'
      : '<div class="empty">No pending changes — in sync with the source.</div>';
    pushAllBtn.style.display = 'none';
    return;
  }
  filesEl.innerHTML = '';
  const orphan = _isOrphan(graphData.nodes.find(n => n.slug === slug));
  const pushable = orphan ? [] : detail.changed_files.filter(f => f.status !== 'D');
  detail.changed_files.forEach(f => {
    const row = document.createElement('div');
    row.className = 'file-row';
    if (orphan) {
      row.innerHTML = `<div class="file-left"><span class="badge ${f.status}">${f.status}</span><span>${f.path}</span></div>`;
      row.onclick = () => showDiff(slug, f.path, row);
      filesEl.appendChild(row);
      return;
    }
    if (f.status === 'D') {
      row.innerHTML = `<div class="file-left"><span class="badge ${f.status}">${f.status}</span><span>${f.path}</span></div>` +
        `<span class="del-note">not auto-pushed</span>`;
      row.onclick = () => showDiff(slug, f.path, row);
    } else {
      row.innerHTML = `<div class="file-left"><span class="badge ${f.status}">${f.status}</span><span>${f.path}</span></div>` +
        `<button class="push-btn">Push</button>`;
      row.querySelector('.file-left').onclick = () => showDiff(slug, f.path, row);
      row.querySelector('.push-btn').onclick = (e) => { e.stopPropagation(); pushFiles(slug, [f.path], detail.copy_folder); };
    }
    filesEl.appendChild(row);
  });
  const pushAllBtn2 = document.getElementById('push-all');
  pushAllBtn2.style.display = pushable.length ? 'block' : 'none';
  pushAllBtn2.onclick = () => pushFiles(slug, pushable.map(f => f.path), detail.copy_folder);
}

async function pushFiles(slug, files, copyFolder, force) {
  const pushStatus = document.getElementById('push-status');
  pushStatus.textContent = 'Pushing…';
  const res = await fetch(`/api/graph/${encodeURIComponent(slug)}/push`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({files, copy: copyFolder, force: !!force}),
  });
  const result = await res.json();
  const lines = [];
  if (result.pushed && result.pushed.length) lines.push(`Pushed: ${result.pushed.join(', ')}`);
  if (result.conflicts && result.conflicts.length) {
    lines.push(`Source changed since copy — refused: ${result.conflicts.join(', ')}`);
    lines.push('(source moved on; review manually, or push again to overwrite)');
  }
  if (result.skipped_deletions && result.skipped_deletions.length) {
    lines.push(`Deletions never auto-pushed: ${result.skipped_deletions.join(', ')}`);
  }
  if (result.errors && result.errors.length) lines.push(`Errors: ${JSON.stringify(result.errors)}`);
  pushStatus.textContent = lines.join('\\n');

  // Refresh: this project's node state + the panel's file list
  const detail = await fetchDetail(slug);
  renderFiles(slug, detail);
  const idx = graphData.nodes.findIndex(n => n.slug === slug);
  if (idx !== -1) {
    const g = await (await fetch('/api/graph')).json();
    const updated = g.nodes.find(n => n.slug === slug);
    if (updated) Object.assign(graphData.nodes[idx], updated);
    render();
  }
}

async function showDiff(slug, path, rowEl) {
  document.querySelectorAll('#panel-files .file-row').forEach(r => r.classList.remove('active'));
  rowEl.classList.add('active');
  const view = document.getElementById('diff-view');
  view.textContent = 'Loading diff…';
  view.classList.add('show');
  const res = await fetch(`${_detailBase(slug)}/diff?path=${encodeURIComponent(path)}`);
  const text = await res.text();
  view.innerHTML = '';
  text.split('\\n').forEach(line => {
    const span = document.createElement('div');
    if (line.startsWith('+') && !line.startsWith('+++')) span.className = 'diff-add';
    else if (line.startsWith('-') && !line.startsWith('---')) span.className = 'diff-del';
    span.textContent = line;
    view.appendChild(span);
  });
}

document.getElementById('panel-close').onclick = () => {
  document.getElementById('panel').classList.remove('open');
  currentSlug = null;
};

window.addEventListener('resize', () => { if (graphData.nodes.length) render(); });

loadGraph();
</script>
</body>
</html>
"""


_GRAPH_HTML = _GRAPH_HTML.replace('</head>', '<style>' + _PhonePath(__file__).with_name('static').joinpath('phone-ui.css').read_text(encoding='utf-8') + '</style></head>', 1)


@routes.get("/graph")
async def graph_page(request: web.Request) -> web.Response:
    return web.Response(text=embedded(_GRAPH_HTML, request), content_type="text/html", charset="utf-8")
