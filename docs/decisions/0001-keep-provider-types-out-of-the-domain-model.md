# 0001: Keep provider types out of the domain model

**Date:** 2026-08-12 (recorded retroactively)
**Status:** Accepted

**Context:**
Every layer needs to talk about "a message" and "a model response." The
Anthropic SDK already has types for both, and reusing them saves writing
`models.py` at all.

**Options:**
1. Pass SDK objects (`anthropic.types.Message`, `Usage`) through the whole app.
2. Pass raw `dict`s in the wire format.
3. Define local dataclasses (`Message`, `InferenceConfig`, `InferenceResponse`)
   and translate at the edge.

**Chose:** (3). `models.py` imports nothing, and it's the shared vocabulary
every other module depends on. `Message.to_api_dict()` is the only place that
knows the wire shape. `grep -rn "anthropic" src/` returns `client.py` and
nothing else — that's the check that proves it.

**Rejected:**
(1) makes the SDK a dependency of the service layer, the storage layer, and
the tests. A provider swap or a breaking SDK release then touches every file,
and tests need SDK objects built by hand. (2) loses type checking exactly
where the data is user-controlled, and gives nowhere to put derived fields
like `token_count` (deliberately not sent to the API — see `to_api_dict()`).

**Reverses when:** Probably never. Translating costs a few lines per type, and
everything in 0002 and 0006 depends on this seam existing. Revisit only if the
domain model ends up duplicating most of the SDK (tool blocks, thinking
blocks, citations) — at that point the fix is a richer content model, not
removing the seam.

**What I know:**
- Why a volatile external type shouldn't become a dependency of stable
  internal code (an "anti-corruption layer").
- How to translate in both directions at a single boundary.
- That `token_count` can live on the domain type without leaking into the
  request sent to the API.

**What I don't know yet:**
- **Schema evolution.** `Message` is currently `role + content: str`. Real
  messages carry blocks — text, images, tool calls, results. When that
  changes, old rows are already stored in the old shape. How do you change a
  data shape that has persisted instances? (backward/forward compatibility,
  additive-only changes, version fields.)
- **Serialisation boundaries.** `to_api_dict()` only handles one direction to
  one consumer. A real system serialises the same type to a database, an HTTP
  response, a log line, a queue — each with different rules about what's
  allowed to leak.
- **Structured content.** Once `content` stops being a plain string, modelling
  a union of block types becomes real — this is where Pydantic earns its keep
  over dataclasses.

**Pillar pressure:** Operational excellence (changeability, testability).
Small upfront cost, buys freedom for every layer above.
