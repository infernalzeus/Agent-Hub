---
name: sql-database-design
description: Schema design, indexing, migrations, and query conventions — any relational-DB project
keywords: sql, database, postgres, mysql, sqlite, schema, migration, index, orm
---

# SQL / database design

- Normalize until it hurts, then denormalize deliberately — start from a
  schema with no duplicated facts (each fact lives in exactly one place),
  and only introduce redundancy (a cached count, a denormalized join
  column) when a measured query is actually slow, with a comment saying
  why it's there and what keeps it in sync.
- Every foreign key gets an index — a JOIN or a cascade delete on an
  unindexed foreign key is a full table scan waiting to be noticed in
  production, not in dev with a handful of rows.
- Migrations are forward-only and reversible in pairs (`up`/`down`), never
  hand-edited after being applied anywhere — a migration that already ran
  in one environment must not change; write a new migration instead.
- `NOT NULL` and a real foreign-key constraint by default — a nullable
  column or an unenforced reference is a decision, not a default; every
  place the app currently doesn't handle NULL for that column is a latent
  bug waiting for the first row that has one.
- Transactions wrap anything that must succeed or fail together (e.g.
  "debit one account, credit another") — never leave a multi-step write
  half-applied because an exception hit between two separate statements.
- N+1 queries: a loop that issues one query per row instead of one query
  for the whole batch is the single most common ORM performance bug —
  eager-load/join what you know you'll need, don't lazy-load inside a loop.
- Never build a query by string-concatenating user input — parameterized
  queries/prepared statements, always, no exceptions for "this one's just
  internal tooling."
