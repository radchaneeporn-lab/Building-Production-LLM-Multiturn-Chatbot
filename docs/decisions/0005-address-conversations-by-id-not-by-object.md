# 0005: Address conversations by ID, not by object

**Date:** 2026-08-12 (recorded retroactively)
**Status:** Accepted
**Supersedes:** [0004](0004-give-history-ownership-to-the-caller.md)

**Context:**
`Conversation` holds one conversation's state inside a Python object, so the
caller has to hold that object too. An object can't go in a cookie, a URL, or
a JSON body, and it can't be handed to a different process. Both limits bind
the moment turn 5 might be served by a worker that never saw turn 1.

**Options:**
1. Keep `Conversation`; add persistence by having it save/load itself.
2. Keep `Conversation` objects in a process-level registry keyed by ID.
3. `ChatService` holds no conversation state at all — only capabilities (a
   client, a store, a config) — and every call is `load -> compute -> append`,
   addressed by a `session_id` string.

**Chose:** (3). `ChatService` has no `self.history`; between requests it
remembers nothing. The caller's entire state is a string, which is
serialisable and therefore transportable — the property that made
`main_api.py` a thin wrapper instead of a rewrite.

**Rejected:**
(2) looks like a solution and isn't: it works on one process and fails
silently on two, because a request routed to worker B can't see worker A's
registry. It also grows memory without bound unless you build eviction. (1)
leaves the object as the unit of addressing, so the transport problem is
still unsolved.

**Reverses when:** Never, for this architecture — statelessness at the
service layer is what makes horizontal scaling free. What will change is
what sits behind the store (see 0007), not this.

**Worth keeping straight:** the API being stateless (0004) and the service
being stateless (this record) are two different facts at two different
layers. The first forces history to be re-sent; the second forces history to
live outside the process. Confusing them makes both harder to reason about.

**What I know:**
- The `load -> compute -> append` handler pattern, and why it makes the
  service hold capabilities rather than state.
- Why an ID is serialisable and an object isn't, and why that's the whole
  reason the HTTP step was cheap.
- That a process-level registry fails silently at two replicas.

**What I don't know yet:**
- **How a request actually reaches a replica.** I claim "any replica serves
  any request" but have never seen the routing layer that makes it true.
  What a load balancer does, round-robin vs. least-connections, and health
  checks as the mechanism that pulls a sick replica out of rotation.
- **Session affinity ("sticky sessions").** The alternative: pin a user to
  one replica so in-process state works. Why it's generally a smell — it
  breaks on deploy, breaks on scale-in, makes load uneven.
- **Horizontal vs. vertical scaling.** I use the phrase "horizontal scaling
  falls out for free." The underlying idea — add machines vs. add capacity to
  one machine, and which workloads permit which — deserves to be learned
  properly.
- **Where session state lives in real systems.** Cookie vs. signed token vs.
  server-side store keyed by ID. I chose the third without knowing the trade
  space of the other two (size limits, tamper resistance, revocation).
- **Session lifecycle.** Sessions live forever right now. Expiry, TTL, and
  cleanup are unaddressed — a cost concern, and once conversations hold user
  data, a retention/privacy one.

**Pillar pressure:** Reliability and performance efficiency (any replica
serves any request; no session affinity needed at the load balancer).
