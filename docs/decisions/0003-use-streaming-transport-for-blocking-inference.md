# 0003: Use streaming transport for blocking inference

**Date:** 2026-08-12 (recorded retroactively)
**Status:** Accepted

**Context:**
A plain `.create()` call holds an HTTP connection silent for the whole
generation. At small `max_tokens` that's fine; at 16k (the `InferenceConfig`
default) the silence runs long enough that load balancers, proxies, and
gateways can decide the connection is stalled and kill it — losing the whole
response, with nothing partial to save.

**Options:**
1. `.create()` — simplest, silent connection.
2. `.stream()` + `get_final_message()` — SSE events act as a heartbeat, SDK
   assembles the identical final message.
3. `.stream()` consumed incrementally — true streaming.

**Chose:** (2) for `infer()`, the default path. Same signature and same
`InferenceResponse` as (1), so callers can't tell them apart — the
timeout-proofing is entirely hidden inside. All three variants live in
`client.py`; the default is what matters, the others are there for when their
tradeoff fits. `truncate_history()` deliberately uses (1) instead, since a
512-token summary is short enough that timeout risk doesn't apply.

**Rejected:**
(1) as the default, because the failure mode on long generations is total
loss. (3) as the default, because incremental delivery can't hide behind a
single return value — it changes the contract from `InferenceResponse` to
`Iterator[str]`, forcing every caller into a loop and losing usage/
`stop_reason` (they only arrive in the final `message_delta`). That's a fair
price for a chat UI and not for a summariser.

**Reverses when:** The HTTP layer needs token-by-token delivery to the
browser (an SSE or WebSocket endpoint). At that point `infer_streaming()`
becomes the primary path for `/chat`, and reporting usage after a stream
(currently just a footnote in `client.py`) becomes a real design task.

**What I know:**
- That arriving events keep a long-lived connection from looking idle.
- That a transport choice can hide entirely behind a stable return type, and
  that incremental delivery can't.
- That the right variant depends on output length, not preference.

**What I don't know yet:**
- **Where timeouts actually live.** I wrote "intermediaries kill it as
  stalled" without knowing which intermediary, or the number. Several
  independent clocks sit on one request: client read timeout, reverse-proxy
  idle timeout, load-balancer idle timeout, server request timeout. Any one
  can fire — I should be able to name each and its default.
- **What SSE actually is.** Server-Sent Events is a one-way HTTP response
  held open, sent as `text/event-stream` with `data:` lines. I use it through
  the SDK without having seen the raw protocol.
- **SSE vs. WebSocket vs. long polling.** When each is appropriate, and why
  SSE is usually right for chat output (one direction, plain HTTP,
  auto-reconnect).
- **Buffering.** A proxy that buffers a response defeats streaming
  completely — the client sees nothing until the whole body arrives. A
  classic deployment surprise, and it'll hit my future streaming endpoint too.
- **TCP keepalive vs. application heartbeats.** Different layers, both called
  "keepalive." Which one the SSE events are actually standing in for.

**Pillar pressure:** Reliability (timeout resistance) over simplicity. Note
it buys no latency improvement for the user — `infer()` still returns only
when generation completes. Perceived latency stays a separate, unaddressed
problem.
