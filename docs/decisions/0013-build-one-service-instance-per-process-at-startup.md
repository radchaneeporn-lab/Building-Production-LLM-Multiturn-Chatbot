# 0013: Build one service instance per process, at startup

**Date:** 2026-08-12 (recorded retroactively)
**Status:** Accepted

**Context:**
The CLI entry points build the object graph inside `main()` — one process, one
run, obvious lifetime. Under HTTP there is no `main()`; the process outlives
every individual request, and the object graph needs a defined construction
point and a defined teardown point.

**Options:**
1. Construct `LLMClient` / `SQLiteStore` / `ChatService` inside the route
   handler, per request.
2. Module-level globals at import time.
3. FastAPI's `lifespan` async context manager: everything before `yield` runs
   once at startup, everything after runs once at shutdown.

**Chose:** (3). One `ChatService` serves every concurrent request. This is safe
precisely because of 0005 — the service holds capabilities, not conversation
state, so there is no shared mutable state to interleave. The composition root
in `main_api.py` is line-for-line the same as `main_service.py`'s, which is the
concrete evidence that the HTTP step required no change inside
`src/plain_python/`.

**Rejected:**
(1) opens a SQLite connection and constructs an SDK client on every request —
pure waste, and it makes connection pooling impossible later. (2) runs at import
time, which means it also runs during test collection and during any tooling
that imports the module; it also has no shutdown hook, so nothing gets closed
cleanly on container termination.

**Reverses when:** A dependency needs per-request scope (a request-scoped
database transaction, a per-user credential, a per-request trace context). At
that point FastAPI's `Depends()` is the mechanism, and `lifespan` keeps only the
things that genuinely are process-lifetime.

**Related gap:** startup is where the "fail fast on configuration" discipline
should live. `LLMClient.__init__` already validates the API key, so a missing
key kills the process at boot rather than failing the first request. Note that
`/health` currently reports only that the process is up; it does not check that
the database is reachable or that the provider is responding.

**What I know:**
- The distinction between process-lifetime and request-scoped dependencies.
- That a stateless service can be safely shared across concurrent requests.
- That startup is the right place to fail on bad configuration.

**What I don't know yet → fundamentals to learn:**
- **What is actually running my code.** I write route functions; something else
  runs them. Learning goal: the server model — an ASGI application, a server
  process, an event loop, a thread pool for sync handlers, and multiple worker
  processes. Crucially: **`lifespan` runs once per worker process, not once per
  machine.** With four workers I have four `ChatService` instances and four
  SQLite connections to the same file. I did not know that when I wrote this,
  and it changes 0014.
- **`def` vs. `async def`.** I chose `def` and wrote down the reason. What I
  have not learned is what actually happens: sync handlers run in a bounded
  thread pool, so the pool size becomes a concurrency ceiling. Blocking inside
  an `async def` handler blocks the entire event loop and every other request
  with it. This is the single most consequential thing to understand about
  FastAPI, and my code depends on it already.
- **Graceful shutdown.** The code after `yield` runs at shutdown — but only if
  the process is asked politely. Learning goal: SIGTERM vs. SIGKILL, drain
  periods, and what happens to a request that is mid-inference when a deploy
  starts. Relevant immediately: an LLM call can take 30 seconds, which is longer
  than many default drain windows.
- **Liveness vs. readiness.** `/health` conflates them. *Liveness* = the process
  is alive, restart me if not. *Readiness* = I can actually serve traffic
  (dependencies reachable), send me requests. A readiness check that does not
  test dependencies will happily route traffic to a replica whose database is
  gone.
- **Twelve-factor configuration.** Config comes from `.env` via `dotenv`, which
  does not exist in a container. The general principle — configuration lives in
  the environment, not in the image — is what makes the same artifact runnable
  in dev and production.

**Pillar pressure:** Performance efficiency (no per-request construction cost)
and operational excellence (clean startup/shutdown hooks, which matter as soon
as a container orchestrator is sending termination signals).
