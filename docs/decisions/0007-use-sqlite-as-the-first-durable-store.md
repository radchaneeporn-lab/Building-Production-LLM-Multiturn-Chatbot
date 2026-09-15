# 0007: Use SQLite as the first durable store

**Date:** 2026-08-12 (recorded retroactively)
**Status:** Superseded by 0017

**Context:**
`InMemoryStore` loses every conversation on process restart. Durability is
the first genuine production requirement the project hit. The question is
which engine to reach for at a stage with one process, one developer, and no
concurrent traffic.

**Options:**
1. JSON files on disk, one per session.
2. SQLite — embedded, file-backed, real SQL.
3. Postgres (local or managed) from the start.
4. Redis for active sessions.

**Chose:** (2). No server process, no account, no network hop, no
credentials to manage — the whole database is one file that `inspect_db.py`
can read in twenty lines. It teaches the real concepts (schema, rows,
transactions, migrations, parameterised queries) with none of the
operational noise, and the SQL written against it carries over to Postgres
almost unchanged.

**Rejected:**
(3) is the right production answer and the wrong learning-stage answer: real
ops burden (server lifecycle, connection pooling, credentials, backups)
bought to solve a concurrency problem that doesn't exist yet. (1) has no
query capability, no transactions, and turns every append into a
read-modify-rewrite. (4) is a cache, not a system of record, and durability
is the actual requirement here.

**Reverses when:** Any of these becomes true —
- more than one process writes to the database (the HTTP step makes this
  likely: SQLite serialises writes through a single file lock);
- the app runs on a machine that isn't the one holding the file (any
  container platform with ephemeral disk deletes this file on every deploy);
- managed backups, point-in-time recovery, or row-level access control is
  needed;
- vector search over conversation history is needed.

The first two are near-certain within the next phase. The migration is a
new `PostgresStore` implementing the same six methods, no service-layer
change needed, per 0006.

**What I know:**
- SQLite is an embedded database: a file, no server process, one write lock.
- Durability is the requirement a cache can't satisfy.
- This is deliberate, time-boxed debt, not an oversight.

**What I don't know yet:**
This record has the widest knowledge gap in the log, and is the natural
centre of the next study block.

- **Ephemeral vs. persistent storage.** The single most important gap. A
  container's filesystem is usually ephemeral: recreated from the image on
  every deploy and restart, so `conversations.db` disappears. Not a
  cloud-vendor quirk — it's the container model. Understanding it is what
  turns "deploy the app" from a packaging step into a design decision.
- **The three storage shapes**, as concepts before any service name:
  - **Block storage** — a virtual disk attached to one machine. Fast, tied
    to that machine.
  - **File storage** — a shared filesystem several machines can mount.
  - **Object storage** — key/value blobs over HTTP, effectively infinite,
    not a filesystem. Cheapest, highest latency.
  Every managed storage product is one of these three with a bill attached.
- **Transactions and ACID.** I use `with self._conn:` and know it commits or
  rolls back. I couldn't define atomicity, consistency, isolation, or
  durability precisely — and isolation is exactly what 0014 turns on.
- **Isolation levels.** Read-uncommitted through serialisable, and what each
  permits (dirty reads, non-repeatable reads, phantoms) — the vocabulary for
  reasoning about concurrent access instead of guessing.
- **Connection pooling.** SQLite has one connection because it's a file. A
  networked database needs a pool: connections are expensive to open, and
  pool size becomes a real capacity limit that interacts with worker count.
- **Backup, RPO and RTO.** There's currently no backup at all. RPO is how
  much data you can afford to lose; RTO is how long you can afford to be
  down. Writing those two numbers down turns "we should have backups" into a
  design requirement.
- **Indexes.** See 0008.

**Pillar pressure:** Cost and operational excellence now (zero of both);
knowingly deferring reliability (single point of failure, no backup, no
concurrent writers). Deliberate, time-boxed debt, not an oversight.
