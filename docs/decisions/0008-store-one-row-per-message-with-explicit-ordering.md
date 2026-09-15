# 0008: Store one row per message, with explicit ordering

**Date:** 2026-08-12 (recorded retroactively)
**Status:** Accepted

**Context:**
A conversation is a list. Relational storage offers two obvious shapes for
one: serialise it into a column, or normalise it into rows.

**Options:**
1. One `sessions` row per conversation with a JSON blob column holding all
   messages.
2. One `messages` row per message, keyed `(session_id, turn_index)`.

**Chose:** (2). Appending is a two-row `INSERT`. Ordering is carried by an
explicit `turn_index` column, never inferred from insertion order or
`rowid`. `token_count` rides on each row, populated at write time from the
real API response rather than re-tokenised later.

**Rejected:**
(1) makes every append a read-modify-rewrite of the whole conversation —
cost grows with length, and two concurrent writers lose one of their writes
entirely. It also makes cross-session queries (analytics, debugging,
auditing) impossible without unpacking every blob, and rules out partial
reads — which matters directly, since 0010's sliding window is exactly a
partial read.

**Reverses when:** Nothing foreseeable. This row shape is the one that
survives the move to Postgres unchanged.

**The rule this generalises to:** make ordering data. Any property your code
relies on but the storage layer doesn't guarantee is a latent bug waiting for
a query planner, a replica, or a migration to reorder things. `ORDER BY
turn_index` is a promise; "rows come back how they went in" is a hope.

**Known gap:** `append()` computes the next `turn_index` with a `SELECT
COUNT(*)` and then inserts, non-atomically. Fine under one writer; under two
it's a race that produces a primary-key collision. Tracked in
[0014](0014-concurrency-safety-for-the-sqlite-store.md).

**What I know:**
- Normalised rows vs. a serialised blob, and why append cost differs.
- That ordering must be stored, not assumed.
- That a composite primary key `(session_id, turn_index)` enforces uniqueness
  per conversation.

**What I don't know yet:**
- **Indexes.** `load()` runs `WHERE session_id = ? ORDER BY turn_index`. Fast
  today because the table is tiny. What makes it fast at a million rows is an
  index — here the composite primary key happens to serve as one, which I
  didn't plan. What an index physically is (a sorted structure, usually a
  B-tree), why it speeds reads and slows writes, and why an index on the
  leading column of a query's filter is what matters.
- **Reading a query plan.** `EXPLAIN QUERY PLAN` (SQLite) / `EXPLAIN
  ANALYZE` (Postgres) tells you whether a query used an index or scanned the
  whole table — the single most useful database debugging skill, and it
  costs an hour to learn.
- **Primary vs. secondary keys, and foreign keys.** `messages.session_id`
  references `sessions(id)` — I wrote that clause without knowing SQLite
  doesn't enforce foreign keys unless `PRAGMA foreign_keys = ON`. Worth
  checking whether my referential integrity is real or decorative.
- **Migrations.** `_migrate_add_summary_columns()` is hand-rolled with
  `PRAGMA table_info`. It works for adding columns and won't survive a
  rename, a drop, or a backfill. What a migration tool actually provides —
  ordered versioned scripts, up/down, a version table — and why schema
  changes on a live database must stay backward-compatible with the code
  currently running.
- **When to denormalise.** I chose rows over a blob, correctly. The opposite
  is sometimes right (write-heavy, always-read-whole, no cross-queries).
  Knowing the conditions matters more than the rule.

**Pillar pressure:** Performance efficiency (append cost is constant, not
linear in history length) and operational excellence (the data is queryable,
so it's debuggable).
