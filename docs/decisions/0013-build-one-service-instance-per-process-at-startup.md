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
key kills the process at boot rather than failing the first request — which is
the behaviour a container platform's health check is designed to catch. Note
that `/health` currently reports only that the process is up; it does not check
that the database is reachable or that the provider is responding.

**Pillar pressure:** Performance efficiency (no per-request construction cost)
and operational excellence (clean startup/shutdown hooks, which matter as soon
as a container orchestrator is sending termination signals).
