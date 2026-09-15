# 0003: Use streaming transport for blocking inference

A plain, non-streaming call holds a connection silent for the entire
generation — long enough, at large reply lengths, that a proxy can decide
it's stalled and kill it, losing the whole response.

**Other options considered:**
- A plain, non-streaming call — simplest, but risks losing long replies to a timeout
- Stream the response but wait for the final assembled message
- Stream and yield text incrementally as it's generated

**Decision:** `infer()` streams under the hood but still waits for and
returns the complete reply, using the same return type as a plain call —
so nothing about the calling code has to change.

**Reverse if:** The HTTP layer needs to show text to the user as it's
generated — then the incremental variant becomes the primary path instead
of a side option.

**Trade-off:** No latency improvement for the user (the call still returns
only once generation is done) — this buys reliability, not speed.
