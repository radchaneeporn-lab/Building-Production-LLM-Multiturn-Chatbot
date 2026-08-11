# 0003: Use streaming transport for blocking inference

**Date:** 2026-08-12 (recorded retroactively)
**Status:** Accepted

**Context:**
A plain `.create()` call holds an HTTP connection silent for the entire
generation. At small `max_tokens` this is fine; at 16k (the `InferenceConfig`
default) the silence is long enough that load balancers, proxies, and
gateways can classify the connection as stalled and kill it — losing the whole
response, with no partial output to salvage.

**Options:**
1. `.create()` — simplest, silent connection.
2. `.stream()` + `get_final_message()` — SSE events act as a heartbeat, SDK
   accumulates the identical final message.
3. `.stream()` consumed incrementally — true streaming.

**Chose:** (2) for `infer()`, the default path. Same signature and same
`InferenceResponse` as (1), so the caller cannot tell them apart — the
timeout-proofing is entirely inside the boundary. All three variants exist in
`client.py`; the default is what matters, the others are available where their
tradeoff fits. `truncate_history()` deliberately uses (1), since a 512-token
summary is short enough that the timeout risk does not apply and the simpler
call is the better fit.

**Rejected:**
(1) as the default, because the failure mode is total loss on long
generations. (3) as the default, because incremental delivery cannot hide
behind a single return value — it changes the contract from
`InferenceResponse` to `Iterator[str]`, forcing every caller into a loop and
losing usage/`stop_reason` reporting (they arrive in the final `message_delta`).
That cost is worth paying for a chat UI and not worth paying for a summariser.

**Reverses when:** The HTTP layer needs token-by-token delivery to the browser
(SSE or WebSocket endpoint). At that point `infer_streaming()` becomes the
primary path for `/chat`, and the open question in `client.py` note (3) —
how to report usage after a stream — becomes a real design task rather than a
footnote.

**Pillar pressure:** Reliability (timeout resistance) over simplicity. Note it
buys *no* latency improvement for the user: `infer()` still returns only when
generation completes. Perceived latency remains a separate, unaddressed problem.
