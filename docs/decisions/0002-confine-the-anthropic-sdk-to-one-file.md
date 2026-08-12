# 0002: Confine the Anthropic SDK to one file

**Date:** 2026-08-12 (recorded retroactively)
**Status:** Accepted

**Context:**
The provider SDK is the most volatile dependency in the project: it changes on
someone else's release schedule, its response contract can shift, and it is the
one component that makes real network calls. Something has to touch it. The
decision is *how many things*.

**Options:**
1. Call `anthropic.Anthropic()` wherever a completion is needed.
2. A thin function wrapper (`def call_llm(...)`) with no state.
3. An `LLMClient` adapter class that owns the SDK instance, validates config at
   construction, and exposes provider-neutral methods.

**Chose:** (3). `client.py` is the only file that imports `anthropic`. It
translates in one direction (`Message` -> `to_api_dict()`) and out the other
(`_to_inference_response()`), so provider objects never escape the boundary.
The API key is validated in `__init__`, before any network call — a missing key
fails at composition-root time with a clear message rather than mid-request
with an SDK-level error.

**Rejected:**
(1) spreads the volatile edge across the codebase and makes every caller
individually responsible for auth, error handling, and response unpacking.
(2) is fine until you need per-instance state (the SDK client, retry policy,
a rate limiter, a circuit breaker) — at which point you are building a class
out of module-level globals.

**Reverses when:** A second provider is added. This decision does not break —
it *pays off* — but the shape changes: `LLMClient` becomes one implementation
behind a `Protocol` (same move as 0006), and the composition root chooses.
Note the seam is already sized for that: no caller can tell `infer()` from
`infer_create()`, which proves transport choices are genuinely sealed inside.

**What I know:**
- Why a single adapter file is the right containment for a volatile dependency.
- Fail-fast on configuration: validate credentials before any network call.
- That this seam is the natural future home for retries, timeouts, and metrics.

**What I don't know yet → fundamentals to learn:**
- **Retry and backoff semantics.** There is currently no retry logic anywhere.
  Which HTTP status codes are safe to retry (429, 503) and which are not (400,
  401)? Why exponential backoff, and why add jitter on top of it? What stops a
  retry storm from making an overloaded dependency worse?
  (Keywords: exponential backoff with jitter, retry budget, thundering herd.)
- **Timeouts.** The SDK has defaults I have never inspected or set. Every
  network call needs a deadline; without one, a hung dependency holds a worker
  forever. Connect timeout vs. read timeout vs. total request deadline.
- **Circuit breakers.** When a dependency is *down* rather than flaky, retrying
  is actively harmful. A breaker fails fast after N consecutive failures and
  probes for recovery. Concept, states (closed/open/half-open), when it's
  overkill.
- **Idempotency keys.** If a request times out, I do not know whether the
  provider processed it. Retrying may double-charge. This is the same discipline
  as PUT-vs-POST, applied to an external API call.
- **Connection pooling.** The SDK holds an HTTP client underneath. How many
  connections does it keep, and what happens when concurrent requests exceed
  that? This becomes real at the same moment 0014 does.

**Pillar pressure:** Reliability (fail-fast configuration), operational
excellence (one place to add retries, timeouts, and instrumentation later).
