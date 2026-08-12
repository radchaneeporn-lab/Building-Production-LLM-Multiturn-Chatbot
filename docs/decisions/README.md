# Decision Log

Architecture Decision Records (ADRs) for `Production-Agentic-Multiturn-Chatbot`.

## What goes in here

One record per decision that is **expensive to reverse**. Not every choice —
variable names, formatting, and anything a single commit can undo are not
decisions in this sense. The test: *if I changed my mind in three months,
would it cost me an afternoon or a rewrite?* Afternoon -> no record.
Rewrite -> record.

## What a record is for

Six months from now, the code will still show *what* you chose. It will not
show what you rejected, what you were optimising for, what would make the
choice wrong, or **what you did not understand at the time**. That context is
the part that evaporates, and it is the part you need when the constraint
changes.

## Format

```
# NNNN: <short imperative title>

Date:
Status:            Accepted | Superseded by NNNN | Open

Context:           What forced a choice. Include the constraint, not just the goal.
Options:           What was actually on the table.
Chose:             The decision, plus the reason in one or two lines.
Rejected:          The runners-up and why they lost — this is the highest-value field.
Reverses when:     The condition that makes this decision wrong. Write it now,
                   while you can still see it.

What I know:       The understanding this decision actually rests on. Short.
What I don't
know yet:          The gaps. Named as topics, phrased as questions I can't yet
                   answer. This is the honesty valve — it is what stops a
                   record from becoming false confidence.

Pillar pressure:   What this bought, and which pillar it charged.
```

Two fields do the heavy lifting and both are easy to skip:

**`Reverses when:`** turns a static choice into a *trigger* — something you can
watch for rather than rediscover during an incident.

**`What I don't know yet:`** does two jobs at once. It keeps the record honest
("SQLite is fine for production" is dangerous; "SQLite works now, and I don't
know what happens to the file on redeploy" is useful), and it generates your
study list from real blockers instead of a syllabus. A record with gaps is still
a record. `Status: Open` with four options and no decision — see 0014 — is a
perfectly good entry.

## Pillar pressure: the six questions

Every real decision buys something in one pillar and charges another. If you
cannot name the cost, run these until one produces an answer:

| Question | Pillar |
|---|---|
| What gets worse under 10x the load? | Performance efficiency |
| What gets worse if someone hostile is using this? | Security |
| What does this cost per month at real volume? | Cost optimisation |
| What's harder to change now than it was yesterday? | Operational excellence |
| What happens when something I depend on breaks? | Reliability |
| Am I doing work I don't need to do? | Sustainability |

If you only ever run two, run **hostile user** and **cost per month** — those
are the two whose failures are silent. Load and dependency failures announce
themselves.

## Conventions

- Four-digit zero-padded number, monotonic, never reused.
- One decision per file. A file is never rewritten to say something different;
  if the decision changes, write a new record and set the old one's status to
  `Superseded by NNNN`. The log is append-only, like the `messages` table —
  and for the same reason (see 0008).
- Titles are imperative and specific: `Store conversation state in SQLite`,
  not `Storage`.

## Current records

| # | Decision | Status |
|---|---|---|
| [0001](0001-keep-provider-types-out-of-the-domain-model.md) | Keep provider types out of the domain model | Accepted |
| [0002](0002-confine-the-anthropic-sdk-to-one-file.md) | Confine the Anthropic SDK to one file | Accepted |
| [0003](0003-use-streaming-transport-for-blocking-inference.md) | Use streaming transport for blocking inference | Accepted |
| [0004](0004-give-history-ownership-to-the-caller.md) | Give history ownership to the caller | Superseded by 0005 |
| [0005](0005-address-conversations-by-id-not-by-object.md) | Address conversations by ID, not by object | Accepted |
| [0006](0006-define-the-store-seam-as-a-protocol.md) | Define the store seam as a Protocol | Accepted |
| [0007](0007-use-sqlite-as-the-first-durable-store.md) | Use SQLite as the first durable store | Accepted |
| [0008](0008-store-one-row-per-message-with-explicit-ordering.md) | Store one row per message with explicit ordering | Accepted |
| [0009](0009-use-uuid4-session-identifiers.md) | Use UUID4 session identifiers | Accepted |
| [0010](0010-manage-context-with-a-window-plus-rolling-summary.md) | Manage context with a window plus rolling summary | Accepted |
| [0011](0011-carry-the-summary-in-messages-not-the-system-prompt.md) | Carry the summary in messages, not the system prompt | Accepted |
| [0012](0012-persist-only-after-inference-succeeds.md) | Persist only after inference succeeds | Accepted |
| [0013](0013-build-one-service-instance-per-process-at-startup.md) | Build one service instance per process at startup | Accepted |
| [0014](0014-concurrency-safety-for-the-sqlite-store.md) | Concurrency safety for the SQLite store | **Open** |

---

## Learning backlog

Every item below came out of a `What I don't know yet:` field. Nothing here is
vendor-specific by design — these are the primitives that transfer to any cloud,
any provider. Service names get learned later, as *implementations* of these.

Ordered by what blocks the next step, not by topic.

### 1. Concurrency — blocks any multi-user deployment
*From 0004, 0013, 0014*

- Threads vs. async vs. processes: what "shared" means in each
- Atomicity, critical sections, read-then-write as the classic race
- Locks: mutexes, granularity, deadlock, cost
- Optimistic vs. pessimistic concurrency control
- The GIL: what it does and does not protect
- Load testing — reproducing a race on demand

**Done when:** I can make my own `turn_index` collision happen deliberately,
then make it stop happening.

### 2. Storage & databases — blocks deployment and durability
*From 0007, 0008*

- Ephemeral vs. persistent storage (why a container deletes my database)
- Block / file / object storage as three shapes
- ACID; transaction isolation levels and what each anomaly is
- Indexes: what they physically are, and reading a query plan
- Connection pooling; why pool size is a capacity limit
- Migrations: versioned, ordered, backward-compatible with running code
- Backup, RPO, RTO — as numbers I choose, not features I enable

**Done when:** I can state my RPO and RTO, and explain what happens to
`conversations.db` on redeploy without guessing.

### 3. The server & request lifecycle — blocks understanding my own runtime
*From 0003, 0005, 0013*

- ASGI: application, server, event loop, thread pool, worker processes
- `def` vs. `async def` and where blocking hurts
- The several independent timeouts on one request
- SSE vs. WebSocket vs. long polling; proxy buffering
- Graceful shutdown, SIGTERM, drain periods
- Liveness vs. readiness checks
- Load balancing, health checks, why sticky sessions are a smell

**Done when:** I can draw every hop a `/chat` request takes, and name what can
time out at each one.

### 4. Reliability of external calls — blocks trusting the provider
*From 0002, 0012*

- Which status codes are retryable, and why
- Exponential backoff with jitter; retry storms
- Timeouts: connect / read / total deadline
- Circuit breakers
- Idempotency keys; at-least-once vs. exactly-once
- Two-system consistency: outbox pattern, compensating actions

**Done when:** a provider 429 during a burst degrades gracefully instead of
amplifying.

### 5. Security — the thinnest pillar in this log
*From 0009*

- Authentication vs. authorisation
- Session tokens vs. signed tokens vs. API keys
- Rate limiting and quotas (token bucket, per-user vs. per-IP)
- Secrets: runtime injection, never in the image; rotation
- Encryption in transit vs. at rest
- Least privilege and blast radius
- Data retention and deletion

**Done when:** `/chat` is no longer an open, unmetered proxy to a paid model.

### 6. Cost & quality measurement — blocks pricing and blocks knowing if I broke it
*From 0010, 0011*

- Unit economics: define the unit, then instrument it
- Evaluation: an eval set as the regression test for a non-deterministic system
- Prompt caching mechanics; cache key design, TTL, invalidation, hit rate
- Tokenisation basics

**Done when:** I can answer "what did this conversation cost" and "did that
change make answers worse."

### 7. Code-level hygiene — cheap, and currently absent
*From 0001, 0006*

- **Tests.** There are none. The Protocol seam in 0006 exists precisely to make
  them easy, and one suite run against both store implementations would prove
  they behave identically.
- Fakes vs. mocks vs. stubs
- Schema evolution and versioning of persisted types
- Structured content modelling (when `content: str` becomes content blocks)

**Done when:** `pytest` runs and the store contract is verified against both
implementations.

---

## Adding a record

Copy the format block above, take the next number, write it in under ten
minutes. Leave `What I don't know yet:` genuinely blunt — a gap you have named
is searchable; a gap you have papered over is not.

If it takes longer than ten minutes, you are writing a design document — which
is a fine thing to write, but it belongs in `docs/design/`, not here.
