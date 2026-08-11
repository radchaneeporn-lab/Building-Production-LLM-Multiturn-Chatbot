# 0008: Store one row per message, with explicit ordering

**Date:** 2026-08-12 (recorded retroactively)
**Status:** Accepted

**Context:**
A conversation is a list. Relational storage offers two obvious shapes for a
list: serialise it into one column, or normalise it into rows.

**Options:**
1. One `sessions` row per conversation with a JSON blob column holding all
   messages.
2. One `messages` row per message, keyed `(session_id, turn_index)`.

**Chose:** (2). Appending is a two-row `INSERT`. Ordering is carried by an
explicit `turn_index` column, never inferred from insertion order or `rowid`.
`token_count` rides on each row, populated at write time from the real API
response rather than re-tokenised later.

**Rejected:**
(1) makes every append a read-modify-rewrite of the entire conversation — cost
grows with conversation length, and two concurrent writers lose one of their
writes entirely. It also makes cross-session queries (analytics, debugging,
auditing, "what did this user actually send") impossible without unpacking every
blob in the table, and makes partial reads impossible — which matters directly,
because 0010's sliding window is exactly a partial read.

**Reverses when:** Nothing foreseeable. The row shape is the one that survives
the move to Postgres unchanged.

**The generalisable rule:** *make ordering data.* Any property your code relies
on but the storage layer does not guarantee is a latent bug waiting for a query
planner, a replica, or a migration to reorder things. `ORDER BY turn_index` is
a promise; "rows come back how they went in" is a hope.

**Known gap:** `append()` computes the next `turn_index` with a `SELECT
COUNT(*)` and then inserts, non-atomically. Under one writer this is correct;
under two it is a race that produces a primary-key collision. Tracked in
[0014](0014-concurrency-safety-for-the-sqlite-store.md).

**Pillar pressure:** Performance efficiency (append cost is constant, not
linear in history length) and operational excellence (the data is queryable, so
it is debuggable).
