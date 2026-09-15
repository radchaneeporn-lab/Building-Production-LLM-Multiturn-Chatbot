# 0013: Build one service instance per process, at startup

**Date:** 2026-08-12 (recorded retroactively)
**Status:** Accepted

**Context:**
The CLI entry points build the object graph inside `main()` — one process,
one run, obvious lifetime. Under HTTP there's no `main()`; the process
outlives every individual request, and the object graph needs a defined
construction point and a defined teardown point.

**Options:**
1. Construct `LLMClient` / `SQLiteStore` / `ChatService` inside the route
   handler, per request.
2. Module-level globals at import time.
3. FastAPI's `lifespan` async context manager: everything before `yield`
   runs once at startup, everything after runs once at shutdown.

**Chose:** (3). One `ChatService` serves every concurrent request. That's
safe precisely because of 0005 — the service holds capabilities, not
conversation state, so there's no shared mutable state to interleave. The
composition root in `main_api.py` is line-for-line the same as
`main_service.py`'s, concrete proof that the HTTP step needed no change
inside `src/chatbot/`.

**Rejected:**
(1) opens a SQLite connection and builds an SDK client on every request —
pure waste, and it rules out connection pooling later. (2) runs at import
time, which means it also runs during test collection and any tooling that
imports the module, and it has no shutdown hook, so nothing closes cleanly
on container termination.

**Reverses when:** A dependency needs per-request scope (a request-scoped
database transaction, a per-user credential, a per-request trace context).
At that point FastAPI's `Depends()` is the mechanism, and `lifespan` keeps
only what's genuinely process-lifetime.

**Related gap:** startup is where "fail fast on configuration" should live.
`LLMClient.__init__` already validates the API key, so a missing key kills
the process at boot rather than failing the first request. `/health`
currently only reports that the process is up — it doesn't check that the
database is reachable or the provider is responding.

**What I know:**
- The distinction between process-lifetime and request-scoped dependencies.
- That a stateless service can be safely shared across concurrent requests.
- That startup is the right place to fail on bad configuration.

**What I don't know yet:**
- **What's actually running my code.** I write route functions; something
  else runs them. The server model — an ASGI application, a server process,
  an event loop, a thread pool for sync handlers, and multiple worker
  processes. Crucially: `lifespan` runs once per worker process, not once
  per machine. With four workers I have four `ChatService` instances and
  four SQLite connections to the same file. I didn't know that when I wrote
  this, and it changes 0014.
- **`def` vs. `async def`.** I chose `def` and wrote down the reason, but
  haven't learned what actually happens: sync handlers run in a bounded
  thread pool, so pool size becomes a concurrency ceiling. Blocking inside
  an `async def` handler blocks the entire event loop and every other
  request with it. Probably the single most consequential thing to
  understand about FastAPI, and my code already depends on it.
- **Graceful shutdown.** The code after `yield` only runs if the process is
  asked politely. SIGTERM vs. SIGKILL, drain periods, and what happens to a
  request that's mid-inference when a deploy starts. Relevant immediately:
  an LLM call can take 30 seconds, longer than many default drain windows.
- **Liveness vs. readiness.** `/health` conflates them. Liveness: the
  process is alive, restart me if not. Readiness: I can actually serve
  traffic (dependencies reachable), send me requests. A readiness check that
  doesn't test dependencies will happily route traffic to a replica whose
  database is gone.
- **Twelve-factor configuration.** Config comes from `.env` via `dotenv`,
  which doesn't exist in a container. Configuration should live in the
  environment, not the image — that's what makes the same artifact run in
  dev and production.

**Pillar pressure:** Performance efficiency (no per-request construction
cost) and operational excellence (clean startup/shutdown hooks, which
matter as soon as a container orchestrator starts sending termination
signals).
