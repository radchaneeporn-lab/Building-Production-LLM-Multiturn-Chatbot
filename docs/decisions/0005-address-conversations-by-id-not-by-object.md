# 0005: Address conversations by ID, not by object

**Date:** 2026-08-12 (recorded retroactively)
**Status:** Accepted
**Supersedes:** [0004](0004-give-history-ownership-to-the-caller.md)

**Context:**
`Conversation` holds one conversation's state inside a Python object, so the
caller must hold that object. An object cannot be put in a cookie, a URL, or a
JSON body, and it cannot be handed to a different process. Both limits become
binding the moment turn 5 might be served by a worker that never saw turn 1.

**Options:**
1. Keep `Conversation`; add persistence by having it save/load itself.
2. Keep `Conversation` objects in a process-level registry keyed by ID.
3. `ChatService` holds no conversation state at all — only capabilities (a
   client, a store, a config) — and every call is `load → compute → append`,
   addressed by a `session_id` string.

**Chose:** (3). `ChatService` has no `self.history`. Between requests it
remembers nothing. The caller's entire state is a string, which is
serialisable and therefore transportable — the property that made `main_api.py`
a thin wrapper instead of a rewrite.

**Rejected:**
(2) is the trap that looks like a solution: it works perfectly on one process
and fails silently on two, because a request routed to worker B cannot see
worker A's registry. It also makes memory grow without bound unless you build
eviction. (1) leaves the object as the unit of addressing, so the transport
problem is unsolved.

**Reverses when:** Never for this architecture — statelessness at the service
layer is what makes horizontal scaling free. The thing that *will* change is
what sits behind the store (see 0007), not this decision.

**Note on a distinction worth keeping straight:** the API being stateless
(0004) and the service being stateless (this record) are two different facts at
two different layers. The first forces history to be re-sent; the second forces
history to live outside the process. They are independent, and confusing them
makes both harder to reason about.

**Pillar pressure:** Reliability and performance efficiency (any replica serves
any request; no session affinity required at the load balancer).
