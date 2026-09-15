# 0017: Move the durable store to PostgreSQL, behind the existing seam

**Date:** 2026-09-14
**Status:** Accepted

**Context:**
0007 chose SQLite and wrote its own expiry conditions; 0015 restated them as
"one flag away instead of theoretical" once the app was containerised; 0014
is still Open because the `turn_index` race it describes has no fix that
works in SQLite. The specific trigger: `append()` read `SELECT COUNT(*)` and
then inserted, so two concurrent appends to one session could both read N
and both write turn N — and `turn_index` is the ordering key (0008), so a
collision there corrupts message order permanently rather than just losing
a write. SQLite masked this with a whole-file write lock, which is correct
and also the reason it can't be the answer: it serialises every writer in
the process, and protects nothing once a second process exists.

The constraint isn't "Postgres is more production-grade." It's that the
next step I actually want — more than one replica serving `/chat` — is
incompatible with a single-writer file, and the race is already real in one
process.

**Options:**
1. Postgres in a Compose service; a new `PostgresStore` behind the existing
   `ConversationStore` Protocol, selected at startup by `DATABASE_URL`.
2. Stay on SQLite; fix the race with a per-session lock in application code.
3. Move to Postgres and delete `SQLiteStore` — one store, no branching.
4. Skip the container; point at a managed Postgres (Neon/RDS/Railway) now.

**Chose:** (1). The store was defined as a Protocol in 0006 specifically so
this day would cost one class, and it did: `ChatService` is untouched, and
the only line that changed in either composition root is which store gets
constructed. `turn_index` is now `MAX(turn_index)+1` taken under `SELECT ...
FOR UPDATE` on the session row, which serialises appends per conversation
while leaving different conversations concurrent — narrower than the
file-wide lock it replaces. Verified under load, not assumed: five
concurrent requests to one session produced 24 rows with 24 distinct
contiguous indexes, no duplicates, no gaps.

**Rejected:**
(2) fixes the symptom in exactly the configuration that doesn't matter — it
does nothing across two replicas, the trigger that forced this, and
SQLite's single-writer file would still be there underneath. Solving a
distributed problem with a local primitive is the trap. (3) makes a
database server mandatory to run `main_service.py` or `main_plain.py` on a
laptop, reintroducing the setup friction 0015 existed to remove.
`InMemoryStore` is kept for the same reason — a seam with one
implementation isn't a seam. (4) is the right destination and the wrong
step. It adds an account, a bill, network egress, and a secret to a change
whose content is the engine swap, and would have turned "does the row lock
work" into a question I answer over the internet. Following the
`DATABASE_URL` convention means that move becomes a config change later
instead of a code change, which is most of why I followed it.

**Reverses when:**
- One Postgres container becomes the single point of failure I actually
  care about. A container on one host has no failover and no read
  replicas; the moment uptime matters, this becomes managed Postgres, not a
  bigger container.
- The schema has to change while a deployed database holds rows. `CREATE
  TABLE IF NOT EXISTS` covers an empty database and nothing else — that day
  a migration tool stops being optional, and arrives before the HA one.
- Connection count outgrows direct pooling (many replicas × pool size
  against a default `max_connections` of 100) — pgbouncer's problem, not a
  bigger `max_size`.
- Backups become a requirement. Unchanged from 0007: a Docker volume
  holding Postgres has no more backup story than one holding a `.db` file.
  This decision bought concurrency, not durability.

**What I know:**
- The race is closed at the index level, proved rather than reasoned about:
  24 rows, 24 distinct `turn_index` under five concurrent writers.
- `FOR UPDATE` is pessimistic locking — take the lock, then read — and its
  granularity is the point. Locking one session's row is why two different
  conversations still write in parallel.
- `depends_on` waits for a container to start, not for Postgres to accept
  connections. Without a `healthcheck` plus `condition: service_healthy`,
  the app wins the race on a cold boot and dies opening its pool.
- Why a pool and not one shared connection: FastAPI runs `def` handlers in
  a thread pool, and a Postgres connection runs one statement at a time.
  SQLite's `check_same_thread=False` had no equivalent.
- Opening the pool eagerly (`open=True` + `wait()`) turns "a bad
  DATABASE_URL" from a failed request later into a process that refuses to
  boot.
- An optional backend's driver must not be a hard import. I wrote `from
  psycopg_pool import ...` at module top, and it broke every SQLite-only
  run in an environment that hadn't reinstalled dependencies, including my
  own venv. The import belongs inside the class that needs it.
- Nothing was migrated. Conversations from before the switch are still in
  the SQLite volume and unreachable from a Postgres-backed process.

**What I don't know yet:**
- **The logical race is still open.** I fixed index collision, not
  semantics: two concurrent `send()`s on one session still both `load()`
  the same history and both append, so one reply can be computed against a
  view that's already stale. The rows are well-ordered and the conversation
  can still interleave incoherently. What's the actual fix — a lock held
  across the whole turn, optimistic versioning on the session, or a
  per-session queue — and what does each cost in latency?
- **Isolation levels.** I used `FOR UPDATE` without ever choosing an
  isolation level, so I'm on `READ COMMITTED` by default and can't state
  what that guarantees me. Which anomalies are still possible, and would
  `REPEATABLE READ`/`SERIALIZABLE` change my locking at all?
- **Pool sizing as a capacity decision.** `max_size=10` is a guess. What
  ties it to uvicorn's threadpool size and to `max_connections`, and what
  actually happens at `--scale chatbot=3` — queueing, refusal, or something
  worse?
- **Migrations against live data.** Additive vs. destructive changes,
  expand/contract, and running a migration while old code is still serving
  traffic.
- **Backups as numbers.** 0007 asked for an RPO and RTO I still can't
  state, and moving engines hasn't answered it. `pg_dump` on a schedule is
  the cheap first version; what does point-in-time recovery actually
  require?

**Pillar pressure:** Reliability and performance efficiency bought —
concurrent writers to one conversation are now correct, and the
single-writer constraint that blocked multiple replicas is gone. Charged to
operational excellence and cost: there's now a second stateful service to
run, health-check, and eventually back up; the schema has become something
that needs migrating rather than something a `CREATE TABLE` can express;
and a database is a standing cost where a file was free. The honest summary
is that this bought the ability to scale out, and spent it on a system with
strictly more moving parts and the same backup story as yesterday.
