---
name: app-idea-to-spec
description: Turning a raw app/project idea into a scoped, buildable spec before writing code
keywords: idea, spec, prd, scope, mvp, brainstorm, product, planning
---

# Turning an idea into a buildable spec

The recurring founder task this covers: someone has a raw idea ("an app
that tracks X" / "a tool for Y") and needs it turned into something an
agent can actually start building — not a business plan, a build plan.

- **Answer these four before any code, and write the answers down**: who
  hits this in the next 2 weeks (a specific person/situation, not "users"),
  what's the ONE thing it must do to be worth using at all, what does the
  smallest version that tests that ONE thing look like, and what's
  explicitly cut for v1 (write the cut list — it's what stops scope creep
  mid-build).
- **An idea that can't name its first real user in one sentence isn't ready
  to spec yet** — "for people who want to be healthier" can't be built
  against; "for someone who forgets to log their meds twice a week" can.
  Push back and ask for the specific case before scoping.
- **Spec shape that actually works for an agent build**: (1) the one-line
  pitch, (2) the core flow as a numbered sequence of screens/steps — not
  prose, (3) data model — what objects exist and their key fields, (4)
  explicit v1 cut list, (5) the one thing that would make you scrap the
  idea if it turned out false (the risky assumption).
- **Size the build against the assumption being tested, not the idea's
  full ambition.** If the risky assumption is "will anyone actually use
  this daily," the spec's v1 needs just enough to observe daily use — not
  every feature the full vision eventually needs.
- **Vague feature requests get turned into a concrete question before
  scoping them**: "add social features" isn't buildable; "let a user share
  one result via a public link" is — always convert a vague ask into the
  smallest concrete version before it goes on the spec.
- **Red flags an idea needs more thinking before it's spec-ready**: the
  pitch requires two "and"s to explain (it's actually two ideas), the
  answer to "who's it for" is broader than the answer to "who am I showing
  this to first," or there's no way to tell within a week of shipping v1
  whether it worked.
