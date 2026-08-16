---
name: unity-csharp-game
description: Unity 6 / C# game development conventions (neon-warfare style projects)
keywords: unity, csharp, cs, prefab, neon-warfare, gamedev
---

# Unity / C# game development

- Never edit `.meta` files directly — they're Unity-generated and pairing
  drift breaks asset references. If a `.meta` is missing after an edit, let
  Unity regenerate it (don't hand-author one).
- Prefab changes: check whether the target is a prefab asset or a scene
  instance before editing — editing an instance when you meant the prefab
  (or vice versa) silently doesn't propagate.
- `ScriptableObject` data assets are usually the source of truth for tunable
  values (damage, costs, stats) — search for one before hardcoding a number
  in a script.
- MonoBehaviour lifecycle: prefer `Awake`/`OnEnable` for wiring that must be
  ready before any other script's `Start`, plain `Start` otherwise. Getting
  this wrong is a common source of null-reference-on-first-frame bugs.
- C# coroutines vs `async/await`: match whatever the surrounding codebase
  already uses — mixing both patterns in one system is a common source of
  subtle timing bugs.
