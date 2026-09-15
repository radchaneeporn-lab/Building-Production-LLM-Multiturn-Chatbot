# 0002: Confine the Anthropic SDK to one file

**Date:** 2026-08-12 (recorded retroactively)
**Status:** Accepted

**Context:**
The provider SDK is the most volatile dependency in the project — it moves on
someone else's release schedule, its response contract can shift, and it's
the one piece making real network calls. Something has to touch it directly.
The question is how many things.

**Options:**
1. Call `anthropic.Anthropic()` wherever a completion is needed.
2. A thin function wrapper (`def call_llm(...)`) with no state.
3. An `LLMClient` adapter class that owns the SDK instance, validates config
   at construction, and exposes provider-neutral methods.

**Chose:** (3). `client.py` is the only file that imports `anthropic`. It
translates one way in (`Message -> to_api_dict()`) and the other way out
(`_to_inference_response()`), so provider objects never escape. The API key
is validated in `__init__`, before any network call, so a missing key fails
loudly at startup instead of mid-request with an SDK error.

**Rejected:**
(1) spreads the volatile edge across the codebase — every caller becomes
responsible for auth, error handling, and unpacking responses. (2) is fine
until you need per-instance state (the SDK client, a retry policy, a rate
limiter, a circuit breaker), at which point you're building a class out of
module-level globals anyway.

**Reverses when:** A second provider is added. This doesn't break the
decision, it pays it off: `LLMClient` becomes one implementation behind a
`Protocol` (same move as 0006), and the composition root picks. No caller can
already tell `infer()` from `infer_create()`, which proves the transport
choice is sealed inside where it belongs.

**What I know:**
- Why a single adapter file is the right container for a volatile dependency.
- Fail fast on configuration: validate credentials before any network call.
- That this file is the natural future home for retries, timeouts, metrics.

**What I don't know yet:**
- **Retries and backoff.** There's no retry logic anywhere. Which status
  codes are safe to retry (429, 503) and which aren't (400, 401)? Why
  exponential backoff, and why add jitter? What stops a retry storm from
  making an overloaded dependency worse?
- **Timeouts.** The SDK has defaults I've never inspected or set. Every
  network call needs a deadline, or a hung dependency holds a worker forever.
  Connect timeout vs. read timeout vs. total deadline.
- **Circuit breakers.** When a dependency is down rather than flaky, retrying
  is actively harmful. A breaker fails fast after N failures and probes for
  recovery — states, when it's overkill.
- **Idempotency keys.** If a request times out, I don't know whether the
  provider processed it. Retrying could double-charge.
- **Connection pooling.** The SDK holds an HTTP client underneath. How many
  connections does it keep, and what happens when concurrent requests exceed
  that? Becomes real at the same moment 0014 does.

**Pillar pressure:** Reliability (fail-fast configuration), operational
excellence (one place to add retries, timeouts, instrumentation later).
