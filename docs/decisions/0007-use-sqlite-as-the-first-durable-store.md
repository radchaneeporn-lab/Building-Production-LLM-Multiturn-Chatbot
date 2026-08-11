# 0007: Use SQLite as the first durable store

**Date:** 2026-08-12 (recorded retroactively)
**Status:** Accepted

**Context:**
`InMemoryStore` loses every conversation on process restart. Durability is the
first genuine production requirement the project hit. The choice is which
engine to reach for at a stage with one process, one developer, and no
concurrent traffic.

**Options:**
1. JSON files on disk, one per session.
2. SQLite — embedded, file-backed, real SQL.
3. Postgres (local or managed) from the start.
4. Redis for active sessions.

**Chose:** (2). No server process, no account, no network hop, no credentials
to manage; the whole database is one file that `inspect_db.py` can read in
twenty lines. It teaches the actual concepts — schema, rows, transactions,
migrations, parameterised queries — with none of the operational noise, and the
SQL written against it transfers almost unchanged to Postgres.

**Rejected:**
(3) is the correct production answer and the wrong learning-stage answer: real
ops burden (server lifecycle, connection pooling, credentials, backups) bought
to solve a concurrency problem that does not yet exist. (1) has no query
capability, no transactions, and turns every append into a read-modify-rewrite.
(4) is a cache, not a system of record — durability is the requirement here.

**Reverses when:** Any one of these becomes true —
- more than one process writes to the database (the HTTP step makes this
  likely: SQLite serialises writes through a single file lock);
- the app runs on a machine that is not the machine holding the file (any
  container platform with ephemeral disk — App Runner included — deletes this
  file on every deploy);
- managed backups, point-in-time recovery, or row-level access control is
  needed;
- vector search over conversation history is needed (pgvector).

The first two are near-certain within the next phase. The migration is a new
`PostgresStore` implementing the same six methods — no service-layer change,
per 0006.

**Pillar pressure:** Cost and operational excellence now (zero of both);
knowingly deferring reliability (single point of failure, no backup, no
concurrent writers). This is a deliberate, time-boxed debt, not an oversight.
