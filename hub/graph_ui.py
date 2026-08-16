"""Project status graph page (Phase 4).

One node per PROJECT (never per file) — see hub/agent_knowledge/status.py for
the state model and hub/features/graph.py for the API it reads. Clicking a
node opens a git-desktop-style detail panel (changed-file list + diff view)
in place; it never explodes the graph into extra file nodes.
"""
from __future__ import annotations

from aiohttp import web

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
<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
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
header{position:fixed;top:0;left:0;right:0;z-index:20;height:56px;display:flex;align-items:center;gap:14px;
  padding:0 20px;border-bottom:1px solid rgba(0,230,118,.14);
  background:linear-gradient(150deg,#080c28 0%,#0d1050 45%,#18095c 100%)}
.brand{font-family:'Orbitron',monospace;font-size:16px;font-weight:900;color:var(--accent);letter-spacing:3px}
.back-link{margin-left:auto;font-family:'Orbitron',monospace;font-size:11px;letter-spacing:1.5px;
  color:var(--text-muted);text-decoration:none;padding:8px 14px;border:1px solid rgba(0,230,118,.28);border-radius:8px;
  transition:color .15s,border-color .15s}
.back-link:hover{color:var(--accent);border-color:var(--accent)}

svg#graph{position:fixed;top:56px;left:0;right:0;bottom:0;width:100%;height:calc(100% - 56px);
  cursor:grab;background:#000}
svg#graph:active{cursor:grabbing}
.ngrp{cursor:pointer}
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
</style>
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
  <div class="row"><span class="dot" style="background:var(--grey)"></span>read-only / local cluster</div>
  <div class="row" style="margin-top:4px"><span style="width:16px;height:0;border-top:1.5px dotted #ffffff;flex-shrink:0"></span>documented in wiki</div>
  <div class="row"><span style="width:16px;height:0;border-top:1.5px solid #6a3fd1;flex-shrink:0"></span>related project (wiki link)</div>
</div>

<div id="panel">
  <button class="close" id="panel-close" aria-label="Close">&times;</button>
  <h2 id="panel-title"></h2>
  <div id="panel-badge"></div>
  <div class="path" id="panel-path"></div>
  <div id="panel-connections"></div>
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
const COLORS = {red:'#e2544a', blue:'#5b9bf5', amber:'#f5c842', green:'#00e676', unknown:'#888780'};
const RING_COLORS = {green:'#97c459', orange:'#ef9f27'};   // ready-to-push / needs-update
const CLUSTER_COLOR = '#00e8ff';
const CLUSTER_COLOR_GREY = '#7c8797';
const GREY_CLUSTERS = new Set(['Read-only', 'Local']);
const CLUSTER_ORDER = ['My Repo', 'Collab Projects', '_unsorted projects', 'Open Source', 'Read-only', 'Local'];
const CLUSTER_LABEL = {
  'My Repo': 'MY REPO', 'Collab Projects': 'COLLAB PROJECTS',
  '_unsorted projects': 'UNSORTED', 'Open Source': 'OPEN SOURCE', 'Read-only': 'READ-ONLY',
  'Local': 'LOCAL',
};

let graphData = {nodes: [], projectLinks: []};
let currentSlug = null;
let zoomBehavior = null;

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
  const byCat = d3.group(nodes, d => d.category || 'Other');
  const cats = Array.from(byCat.keys()).sort(
    (a, b) => CLUSTER_ORDER.indexOf(a) - CLUSTER_ORDER.indexOf(b));

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

function render() {
  const svg = d3.select('#graph');
  svg.selectAll('*').remove();
  const width = window.innerWidth, height = window.innerHeight;

  const defs = svg.append('defs');
  [['glow-blue', COLORS.blue, 4], ['glow-amber', COLORS.amber, 4], ['glow-green', COLORS.green, 4],
   ['glow-red', COLORS.red, 4], ['glow-cyan', CLUSTER_COLOR, 6], ['glow-unknown', COLORS.unknown, 4],
   ['glow-cluster-grey', CLUSTER_COLOR_GREY, 6]]
    .forEach(([id, , std]) => {
      const f = defs.append('filter').attr('id', id)
        .attr('x', '-60%').attr('y', '-60%').attr('width', '220%').attr('height', '220%');
      f.append('feGaussianBlur').attr('stdDeviation', std).attr('result', 'b');
      const merge = f.append('feMerge');
      merge.append('feMergeNode').attr('in', 'b');
      merge.append('feMergeNode').attr('in', 'SourceGraphic');
    });
  const glowFor = state => `url(#glow-${state in COLORS ? state : 'unknown'})`;

  const root = svg.append('g').attr('id', 'graph-root');
  const edgeLyr = root.append('g');
  const nodeLyr = root.append('g');
  const partLyr = root.append('g'); // reserved for future pulse/activity effects

  const clusterNodes = layoutGraph(graphData.nodes);

  // ── Edges: each project -> its cluster center, curved like agent-core's dendrites ──
  const edgeData = graphData.nodes.map(m => ({src: m, tgt: clusterNodes.find(c => c.id === m._clusterId)}))
    .filter(e => e.tgt);
  edgeLyr.selectAll('path.edge').data(edgeData).enter().append('path')
    .attr('class', 'edge')
    .attr('d', d => bezierPath(d.src, d.tgt, edgeSign(d.src.slug, d.tgt.id) * 0.16))
    .attr('fill', 'none')
    .attr('stroke', '#ffffff')
    .attr('stroke-opacity', 0.18)
    .attr('stroke-width', 0.75)
    .attr('stroke-dasharray', '1,3');

  // ── Wiki-link edges: project -> LLM Wiki node, only when a wiki entity page
  // declares this project via project_slug frontmatter (or a name match).
  // Absence of this edge is the point — it's a visible "undocumented" signal,
  // not just a missing decoration. Drawn distinctly (dashed, wiki teal) so it
  // never reads as just another cluster-membership line.
  const wikiNode = graphData.nodes.find(n => n.slug === 'llm-wiki');
  if (wikiNode) {
    const wikiEdgeData = graphData.nodes.filter(n => n.wiki_entity && n.slug !== 'llm-wiki')
      .map(n => ({src: n, tgt: wikiNode}));
    edgeLyr.selectAll('path.wiki-edge').data(wikiEdgeData).enter().append('path')
      .attr('class', 'wiki-edge')
      .attr('d', d => bezierPath(d.src, d.tgt, edgeSign(d.src.slug, 'llm-wiki') * 0.1))
      .attr('fill', 'none')
      .attr('stroke', '#ffffff')
      .attr('stroke-opacity', 0.32)
      .attr('stroke-width', 0.9)
      .attr('stroke-dasharray', '1,3');
  }

  // ── Project-to-project edges: real [[wikilinks]] between two projects' OWN
  // wiki pages (e.g. agent-hub.md linking to [[movie-shorts-clipper]]) — the
  // wiki's existing prose cross-references, not a separately-invented signal.
  // Solid and brighter than the other edge types since these are documented,
  // real functional relationships, not just structural/organizational ones.
  const bySlug = new Map(graphData.nodes.map(n => [n.slug, n]));
  const projectEdgeData = graphData.projectLinks
    .map(l => ({src: bySlug.get(l.a), tgt: bySlug.get(l.b)}))
    .filter(e => e.src && e.tgt);
  edgeLyr.selectAll('path.project-edge').data(projectEdgeData).enter().append('path')
    .attr('class', 'project-edge')
    .attr('d', d => bezierPath(d.src, d.tgt, edgeSign(d.src.slug, d.tgt.slug) * 0.13))
    .attr('fill', 'none')
    .attr('stroke', '#6a3fd1')
    .attr('stroke-opacity', 0.55)
    .attr('stroke-width', 1);

  // ── Cluster hub nodes ──────────────────────────────────────────────────────
  const cGroups = nodeLyr.selectAll('.cgrp').data(clusterNodes).enter()
    .append('g').attr('class', 'cgrp')
    .attr('transform', d => `translate(${d.x},${d.y})`);
  const clusterColor = d => GREY_CLUSTERS.has(d.cat) ? CLUSTER_COLOR_GREY : CLUSTER_COLOR;
  cGroups.append('circle').attr('r', 16).attr('fill', 'none')
    .attr('stroke', clusterColor).attr('stroke-width', 1.2).attr('opacity', 0.28);
  cGroups.append('circle').attr('r', 13)
    .attr('fill', clusterColor).attr('fill-opacity', 0.85)
    .attr('stroke', clusterColor).attr('stroke-opacity', 0.6).attr('stroke-width', 1)
    .attr('filter', d => GREY_CLUSTERS.has(d.cat) ? 'url(#glow-cluster-grey)' : 'url(#glow-cyan)');
  cGroups.append('text').attr('dy', 30).text(d => d.label);

  // ── Project nodes ────────────────────────────────────────────────────────
  const node = nodeLyr.selectAll('.ngrp').data(graphData.nodes).enter()
    .append('g').attr('class', 'ngrp')
    .attr('transform', d => `translate(${d.x},${d.y})`)
    .on('click', (event, d) => openPanel(d))
    .on('mouseover', function (event, d) {
      const tt = document.getElementById('tt');
      tt.textContent = `${d.name} — ${d.category || ''}`;
      tt.style.display = 'block';
      d3.select(this).select('.n-dot').transition().duration(150).attr('r', 11).attr('fill-opacity', 1);
    })
    .on('mousemove', event => {
      const tt = document.getElementById('tt');
      tt.style.left = (event.clientX + 14) + 'px';
      tt.style.top = (event.clientY - 8) + 'px';
    })
    .on('mouseout', function () {
      document.getElementById('tt').style.display = 'none';
      d3.select(this).select('.n-dot').transition().duration(200).attr('r', 8).attr('fill-opacity', 0.85);
    });

  node.append('circle').attr('class', 'n-ring')
    .attr('r', 11).attr('fill', 'none')
    .attr('stroke', d => COLORS[d.state] || COLORS.unknown)
    .attr('stroke-width', 0.8)
    .attr('opacity', 0.12);

  node.append('circle').attr('class', 'n-dot')
    .attr('r', 8)
    .attr('fill', d => COLORS[d.state] || COLORS.unknown)
    .attr('fill-opacity', 0.85)
    .attr('stroke', d => d.ring ? RING_COLORS[d.ring] : (COLORS[d.state] || COLORS.unknown))
    .attr('stroke-width', d => d.ring ? 3 : 1)
    .attr('stroke-opacity', d => d.ring ? 1 : 0.6)
    .attr('filter', d => glowFor(d.state));

  node.append('text').attr('dy', 22)
    .attr('font-size', 10.5)
    .attr('fill', d => COLORS[d.state] || COLORS.unknown)
    .attr('fill-opacity', 0.7)
    .text(d => d.name.length > 20 ? d.name.slice(0, 18) + '…' : d.name);

  // ── Pan / zoom, auto-fit to whatever the layout produced ───────────────────
  const allX = [...clusterNodes, ...graphData.nodes].map(d => d.x);
  const allY = [...clusterNodes, ...graphData.nodes].map(d => d.y);
  const minX = Math.min(...allX) - 80, maxX = Math.max(...allX) + 80;
  const minY = Math.min(...allY) - 80, maxY = Math.max(...allY) + 80;
  const boundsW = maxX - minX, boundsH = maxY - minY;
  const fitScale = Math.min(width / boundsW, height / boundsH, 1.1);
  const midX = (minX + maxX) / 2, midY = (minY + maxY) / 2;

  zoomBehavior = d3.zoom().scaleExtent([0.3, 3]).on('zoom', event => {
    root.attr('transform', event.transform);
  });
  svg.call(zoomBehavior);
  const initialTransform = d3.zoomIdentity
    .translate(width / 2, height / 2)
    .scale(fitScale)
    .translate(-midX, -midY);
  svg.call(zoomBehavior.transform, initialTransform);
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

async function renderChatControls(d) {
  const el = document.getElementById('panel-chat');
  if (d.readonly) { el.innerHTML = ''; return; }

  let running = [];
  try { running = await (await fetch('/api/opencode/sessions')).json().then(r => r.sessions || []); }
  catch (e) { /* best-effort */ }

  const rows = (d.copies || []).map(c => {
    const live = running.find(s => s.folder === c.folder);
    const action = live
      ? `<button class="chat-btn" data-open="${live.open_url}">OPEN</button>`
      : `<button class="chat-btn" data-resume="${c.folder}">RESUME</button>`;
    const statusText = live ? 'running' : (c.has_diff ? 'has diff, stopped' : 'stopped');
    return `<div class="chat-row"><span>${c.folder} <span style="color:var(--text-muted)">(${statusText})</span></span>${action}</div>`;
  }).join('');

  el.innerHTML = rows + `<button class="chat-btn new" id="new-chat-btn">+ New chat for this project</button>`;

  el.querySelectorAll('[data-open]').forEach(btn => {
    btn.onclick = () => window.open(btn.dataset.open, '_blank');
  });
  el.querySelectorAll('[data-resume]').forEach(btn => {
    btn.onclick = async () => {
      btn.disabled = true; btn.textContent = '…';
      try {
        const res = await fetch('/api/opencode/sessions/resume', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({folder: btn.dataset.resume}),
        });
        const sess = await res.json();
        if (sess.open_url) window.open(sess.open_url, '_blank');
      } catch (e) { alert('Resume failed: ' + e.message); }
      renderChatControls(d);
    };
  });
  const newBtn = document.getElementById('new-chat-btn');
  if (newBtn) newBtn.onclick = async () => {
    newBtn.disabled = true; newBtn.textContent = 'STARTING…';
    try {
      const res = await fetch('/api/opencode/sessions', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({source: d.path, name: d.name}),
      });
      const sess = await res.json();
      if (sess.open_url) window.open(sess.open_url, '_blank');
    } catch (e) { alert('New chat failed: ' + e.message); }
    // Refresh: a new copy now exists, so the graph node's state/copies changed.
    const g = await (await fetch('/api/graph')).json();
    graphData.nodes = g.nodes;
    graphData.projectLinks = g.project_links || [];
    const updated = graphData.nodes.find(n => n.slug === d.slug);
    if (updated) { renderChatControls(updated); render(); }
  };
}

async function openPanel(d) {
  currentSlug = d.slug;
  document.getElementById('panel-title').textContent = d.name;
  document.getElementById('panel-path').textContent = d.path;
  document.getElementById('diff-view').classList.remove('show');
  document.getElementById('diff-view').textContent = '';

  const badge = document.getElementById('panel-badge');
  const STATE_LABEL = {red:'READ-ONLY', blue:'AVAILABLE', amber:'HAS DIFF', green:'IN SYNC', unknown:'UNKNOWN'};
  const stateLabel = STATE_LABEL[d.state] || 'UNKNOWN';
  const wikiNote = d.wiki_entity
    ? `<span style="color:#5dcaa5;margin-left:8px">documented — ${d.wiki_entity}</span>`
    : `<span style="color:var(--text-muted);margin-left:8px">no wiki page yet</span>`;
  badge.innerHTML = `<span class="state-badge" style="background:${COLORS[d.state]}22;color:${COLORS[d.state]}">${stateLabel}</span>${wikiNote}`;

  renderConnections(d);

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
  const res = await fetch(`/api/graph/${encodeURIComponent(slug)}`);
  return res.json();
}

function renderFiles(slug, detail) {
  const filesEl = document.getElementById('panel-files');
  const pushAllBtn = document.getElementById('push-all');
  if (!detail.changed_files || detail.changed_files.length === 0) {
    const node = graphData.nodes.find(n => n.slug === slug);
    filesEl.innerHTML = node && node.state === 'blue'
      ? '<div class="empty">No chat opened for this project yet.</div>'
      : '<div class="empty">No pending changes — in sync with the source.</div>';
    pushAllBtn.style.display = 'none';
    return;
  }
  filesEl.innerHTML = '';
  const pushable = detail.changed_files.filter(f => f.status !== 'D');
  detail.changed_files.forEach(f => {
    const row = document.createElement('div');
    row.className = 'file-row';
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
  const res = await fetch(`/api/graph/${encodeURIComponent(slug)}/diff?path=${encodeURIComponent(path)}`);
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


@routes.get("/graph")
async def graph_page(request: web.Request) -> web.Response:
    return web.Response(text=_GRAPH_HTML, content_type="text/html", charset="utf-8")
