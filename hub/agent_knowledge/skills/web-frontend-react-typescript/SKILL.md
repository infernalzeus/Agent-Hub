---
name: web-frontend-react-typescript
description: "React/TypeScript frontend conventions — state, rendering, types (for founder projects outside the current Python/D3 stack). Relevant when the task involves: react, typescript, ts, tsx, jsx, frontend, next, vite, hooks."
metadata:
  keywords: "react, typescript, ts, tsx, jsx, frontend, next, vite, hooks"
  origin: hand-written
---

# React / TypeScript frontend

- State lives at the lowest common ancestor that actually needs it — don't
  reach for a global store (Redux/Zustand/Context) before local `useState`
  stops being enough; premature global state makes every component harder
  to reason about in isolation.
- Derive, don't duplicate — a value computable from existing state/props
  (a filtered list, a total) should be computed at render time, not stored
  in its own `useState` that can drift out of sync with its source.
- `useEffect` is for synchronizing with something OUTSIDE React (a
  subscription, a fetch, a DOM API) — if you can compute the same value
  during render, that's not an effect, and the dependency-array footgun
  (stale closures, missing deps) mostly shows up when effects are used for
  things that should've just been plain computation.
- Type the boundaries strictly (API responses, form inputs, props) and
  let inference handle the interior — hand-writing types for every local
  variable is noise; a wrong type at an API boundary is a real bug.
- Keys in a list must be a stable identity from the data (an id), never the
  array index, if the list can reorder/filter/insert — an index key causes
  React to misattribute state to the wrong row after a reorder.
- Avoid prop-drilling past 2-3 levels — either lift the component that
  needs the data closer to its source, or use composition (children/slots)
  instead of threading props through components that don't use them.

## See also

- **`frontend-design`** (vendored from Anthropic) — aesthetic direction:
  typography, colour, layout, visual intentionality. This skill is code/state
  conventions; that one is how it should look.
- **`web-artifacts-builder`** (vendored) — building elaborate multi-component
  claude.ai HTML artifacts (React + Tailwind + shadcn/ui) specifically.
- **`theme-factory`** (vendored) — applying a consistent visual theme across
  slides/docs/landing pages.
