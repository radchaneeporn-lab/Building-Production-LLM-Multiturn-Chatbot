# 0002: Confine the Anthropic SDK to one file

The provider SDK is the most volatile dependency in the project — it moves
on someone else's release schedule, and it's the one piece making real
network calls.

**Other options considered:**
- Call `anthropic.Anthropic()` wherever a completion is needed
- A thin, stateless function wrapper
- An adapter class that owns the SDK instance

**Decision:** `client.py` is the only file that imports `anthropic`. It
checks the API key at construction and translates to/from our own types on
the way in and out.

**Reverse if:** A second provider is added — then `LLMClient` becomes one
implementation behind a shared interface instead of a special case.

**Trade-off:** One extra layer of indirection now, in exchange for retries,
timeouts, and a second provider only ever touching this one file later.
