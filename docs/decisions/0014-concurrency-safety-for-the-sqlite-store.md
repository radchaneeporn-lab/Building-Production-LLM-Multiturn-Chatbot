# 0014: Concurrency safety for the SQLite store

**Date:** 2026-08-12
**Status:** **Open** — no decision made yet. Recorded because the constraint
became real when `main_api.py` was added.

**Why this is now live rather than theoretical:**
`service.py`, `storage.py`, and `truncation.py` each carry a comment deferring
concurrency "until the HTTP server makes it real." The HTTP server now exists,
so it is real. Specifically:

`/chat` is declared with `def`, not `async def`. FastAPI runs synchronous route
handlers in a **worker thread pool**, so multiple requests execute route bodies
in different threads simultaneously. Three consequences follow:

1. **Shared connection across threads.** `SQLiteStore` opens one
   `sqlite3.connect(..., check_same_thread=False)` and holds it for the process
   lifetime. That flag disables Python's thread-ownership guard; it does not
   make concurrent use of a single connection safe. Interleaved statements on
   one connection can corrupt cursor state and produce transactions that commit
   partially or at the wrong boundary.

2. **Non-atomic `turn_index` allocation.** `append()` runs
   `SELECT COUNT(*)` and then `INSERT`. Two threads can read the same count and
   attempt the same `(session_id, turn_index)` — a primary-key collision, which
   surfaces as an unhandled exception and therefore a bare HTTP 500.

3. **Lost update on the rolling summary.** Two `send()` calls on one session
   both read the same `summarized_through`, both summarise, both write. One
   summary is silently discarded, and the surviving one may not cover the turns
   the other folded in — a correctness bug with no error attached to it.

**How this shows up in practice:** rare, load-dependent, and effectively
invisible in single-user testing. It will not appear in local development. It
will appear the first time two people use the deployed service in the same
second.

**Options under consideration:**
1. Per-session `threading.Lock` in the service layer. Simplest; only works
   within one process, so it evaporates the moment there is a second replica —
   or, per 0013, a second *worker*.
2. Connection-per-request instead of one shared connection, plus an atomic
   `turn_index` (`SELECT MAX(turn_index)+1` inside the same transaction, or
   `INSERT ... SELECT`). Fixes (1) and (2), not (3).
3. Push the whole thing into the database: conditional update for the summary
   (`WHERE summarized_through_turn = <expected>`) so a lost update becomes a
   detectable no-op rather than a silent overwrite. Optimistic concurrency —
   survives multiple replicas.
4. Wait, and solve it as part of the Postgres migration (0007), where proper
   transaction isolation and connection pooling exist anyway.

**Leaning:** (4) for the durable fix, with (2) as an interim measure if the
service is exposed to more than one user before that migration. (1) is
tempting and should be resisted for the same reason a process-level session
registry was rejected in 0005 — it is a solution whose failure mode is
"works on one box."

**What I know:**
- That a read-then-write sequence is not atomic and is the classic race.
- Three specific races in my own code, and which of them fail loudly (2) versus
  silently (3).
- That an in-process lock does not survive multiple processes.

**What I don't know yet → fundamentals to learn:**
This record is mostly gap, which is why it is `Open` rather than `Accepted`.
It is also the best-motivated study target in the log, because every concept
below has a concrete instance in my code.

- **Locks and critical sections.** What a mutex is, what it costs, what
  deadlock is, and why lock granularity (per-session vs. global) is the whole
  design.
- **Optimistic vs. pessimistic concurrency.** Pessimistic: take a lock, nobody
  else proceeds. Optimistic: assume no conflict, detect it at write time via a
  version check, retry on failure. Option (3) above is optimistic and I chose
  the phrase before fully understanding the family it belongs to.
- **Transaction isolation levels.** The real answer to race (3) at the database
  layer. Which anomalies each level permits, and what `SELECT ... FOR UPDATE`
  does. Directly follows the ACID gap noted in 0007.
- **The GIL, honestly.** Python threads do not run bytecode in parallel — which
  is why people wrongly assume threaded Python is race-free. Learning goal: why
  the GIL prevents *some* corruption and not multi-statement races like mine.
- **SQLite's WAL mode.** `journal_mode=WAL` allows concurrent readers with one
  writer and would materially change this record's premises. A cheap partial
  mitigation I have not evaluated.
- **Distributed locking.** Once there are two processes, a lock has to live
  somewhere both can see. Learning goal: why this is genuinely hard, and why
  "just use the database" is usually the right answer at small scale.
- **Load testing.** I cannot currently reproduce any of these bugs on demand.
  Learning goal: fire N concurrent requests at one session and watch it break.
  A race you can reproduce is a bug; a race you cannot is a rumour.

**Pillar pressure:** Reliability and, via the summary lost update, correctness.

**Resolve before:** any deployment reachable by more than one concurrent user.
