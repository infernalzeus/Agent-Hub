---
name: d3-dataviz-frontend
description: D3.js v7 graph/dashboard conventions — deterministic layout, SVG glow effects, layered rendering
keywords: d3, svg, graph, dashboard, dataviz, force-simulation, canvas
---

# D3.js graphs and dashboards

- Prefer a **deterministic layout** (radial/grid, computed from data) over
  `d3.forceSimulation` when the graph needs to look the same on every load
  and every node needs a stable, predictable position — force simulations
  are great for organic exploration, bad for anything that needs to stay
  legible or diffable across reloads.
- Layer the SVG explicitly (`<g>` groups in a fixed z-order — edges, then
  nodes, then labels/particles) rather than relying on document order across
  a flat node list; it's the only way to guarantee edges never paint over
  nodes regardless of data order.
- SVG glow/halo effects: a real `<filter>` with `feGaussianBlur` + `feMerge`
  reads as a genuine glow; a faded-opacity duplicate shape reads as blur,
  not light. Worth the extra markup for anything meant to look "alive."
- **Every custom path element needs an explicit `fill="none"`** if it's a
  line/curve, not a filled shape — SVG's default fill is black, and a path
  without `fill="none"` renders as a solid blob instead of a stroke. This is
  the single most common D3 edge-rendering bug.
- Deterministic per-edge curvature (so the same pair of nodes always curves
  the same way, no randomness): hash the two IDs into a sign bit and bend
  the bezier control point that direction — reads as organic, stays stable.
- Bind data with a stable key (`.data(nodes, d => d.id)`), never index —
  otherwise a re-render after a data change reassigns DOM elements to the
  wrong nodes instead of updating in place.
