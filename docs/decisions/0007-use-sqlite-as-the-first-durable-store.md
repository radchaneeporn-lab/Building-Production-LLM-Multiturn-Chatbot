# 0007: Use SQLite as the first durable store

*Superseded by [0017](0017-move-the-durable-store-to-postgresql.md)*

Conversations kept only in memory vanish on restart — durability was the
first real production requirement this project hit.

**Other options considered:**
- JSON files on disk, one per session
- SQLite — embedded, file-backed, real SQL
- PostgreSQL from the start
- Redis for active sessions

**Decision:** SQLite — no server, no account, no network hop, just a file.
The right fit while there's one process and no concurrent users.

**Reverse if:** More than one process writes at once, the app runs
somewhere with an ephemeral disk, or managed backups become necessary.

**Trade-off:** Zero operational cost now, in exchange for a single-writer
limit that would need solving the moment real traffic showed up.
