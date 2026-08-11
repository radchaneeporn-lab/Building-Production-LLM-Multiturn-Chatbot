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
translates in one direction (`Message` → `to_api_dict()`) and out the other
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

**Pillar pressure:** Reliability (fail-fast configuration), operational
excellence (one place to add retries, timeouts, and instrumentation later).
