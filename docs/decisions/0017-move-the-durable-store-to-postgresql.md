# 0017: Move the durable store to PostgreSQL

*Supersedes [0007](0007-use-sqlite-as-the-first-durable-store.md)*

SQLite's single-writer limit (0014) becomes a real problem the moment more
than one process can talk to the database at once — which containerizing
(0015) makes easy to do by accident.

**Other options considered:**
- Postgres in its own container, behind the existing storage interface
- Stay on SQLite, fix the race with an app-level lock
- Move to Postgres and delete the SQLite implementation entirely
- Skip the container, point at a managed Postgres immediately

**Decision:** Postgres in Compose, selected by `DATABASE_URL`, with
row-level locking replacing SQLite's whole-file lock. Verified by firing
five concurrent requests at one conversation and confirming no lost or
duplicated messages.

**Reverse if:** One Postgres container becomes a single point of failure
that actually matters, or a schema change hits a database that already has
rows.

**Trade-off:** A second stateful service to run and eventually back up, in
exchange for fixing a real concurrency bug.
