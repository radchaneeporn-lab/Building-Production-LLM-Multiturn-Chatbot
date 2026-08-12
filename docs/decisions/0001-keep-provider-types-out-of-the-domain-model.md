# 0001: Keep provider types out of the domain model

**Date:** 2026-08-12 (recorded retroactively)
**Status:** Accepted

**Context:**
Every layer of the app needs to talk about "a message" and "a model response."
The Anthropic SDK already has types for both. Reusing them is the path of least
resistance and saves writing `models.py` entirely.

**Options:**
1. Pass SDK objects (`anthropic.types.Message`, `Usage`) through the whole app.
2. Pass raw `dict`s in the wire format.
3. Define local dataclasses (`Message`, `InferenceConfig`, `InferenceResponse`)
   and translate at the edge.

**Chose:** (3). `models.py` has zero outgoing imports and is the shared
vocabulary every other module depends on. `Message.to_api_dict()` is the only
place that knows the wire shape. Verifiable invariant:
`grep -rn "anthropic" src/` returns `client.py` and nothing else.

**Rejected:**
(1) makes the SDK a transitive dependency of the service layer, the storage
layer, and the tests — a provider swap or a breaking SDK release then touches
every file, and tests need SDK objects constructed by hand. (2) loses type
checking exactly where the data is user-controlled, and gives no place to hang
derived fields like `token_count` (which is deliberately *not* sent to the API —
see `to_api_dict()`).

**Reverses when:** Never, realistically. The translation cost is a few lines per
type and it is the load-bearing decision under 0002, 0006, and every test
that will ever be written. Revisit only if the domain model starts duplicating
so much of the SDK surface (tool blocks, thinking blocks, citations) that the
mapping layer becomes the bulk of the code — at which point the answer is a
richer content model, not the removal of the seam.

**What I know:**
- Why an anti-corruption layer exists: a volatile external type must not become
  a transitive dependency of stable internal code.
- How to translate in both directions at a single boundary.
- That `token_count` can ride on the domain type without leaking to the wire.

**What I don't know yet → fundamentals to learn:**
- **Schema evolution / versioning.** `Message` is currently `role + content: str`.
  Real messages carry content *blocks* — text, images, tool calls, tool results.
  When that change lands, every stored row written under the old shape still
  exists. How do you change a data shape that already has persisted instances?
  (Keywords: backward/forward compatibility, additive-only changes, schema
  version fields.)
- **Serialisation boundaries.** `to_api_dict()` handles one direction to one
  consumer. A real system serialises the same type to a database, an HTTP
  response, a log line, and a message queue — each with different rules about
  what's allowed to leak. What's the discipline for keeping those separate?
- **Structured content modelling.** Once `content` stops being a string, the
  question of how to model a discriminated union of block types becomes real.
  This is where Pydantic earns its keep over dataclasses.

**Pillar pressure:** Operational excellence (changeability, testability).
Costs a little up-front effort; buys freedom for every layer above.
