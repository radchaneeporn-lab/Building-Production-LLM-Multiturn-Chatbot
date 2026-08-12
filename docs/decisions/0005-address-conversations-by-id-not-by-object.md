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
   client, a store, a config) — and every call is `load -> compute -> append`,
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

**What I know:**
- The `load -> compute -> append` handler pattern, and that it makes the service
  hold capabilities rather than state.
- That an ID is serialisable and an object is not, and why that is the whole
  reason the HTTP step was cheap.
- That a process-level registry fails silently at two replicas.

**What I don't know yet → fundamentals to learn:**
- **How a request actually reaches a replica.** I claim "any replica serves any
  request," but I have never seen the routing layer that makes it true. Learning
  goal: what a load balancer does, round-robin vs. least-connections, and health
  checks as the mechanism that removes a sick replica from rotation.
- **Session affinity ("sticky sessions").** The alternative approach: pin a user
  to one replica so in-process state works. Why it is generally considered a
  smell — it breaks on deploy, breaks on scale-in, and makes load uneven.
  Worth understanding what I avoided.
- **Horizontal vs. vertical scaling.** I use the phrase "horizontal scaling
  falls out for free." The underlying idea — add machines vs. add capacity to
  one machine, and which workloads permit which — deserves to be learned
  properly rather than repeated.
- **Where session state lives in real systems.** Cookie vs. signed token vs.
  server-side store keyed by ID. I chose the third without knowing the trade
  space of the other two (size limits, tamper resistance, revocation).
- **Session lifecycle.** Sessions currently live forever. Expiry, TTL, and
  cleanup are unaddressed — both a cost concern and, once conversations contain
  user data, a retention/privacy concern.

**Pillar pressure:** Reliability and performance efficiency (any replica serves
any request; no session affinity required at the load balancer).
