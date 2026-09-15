# 0001: Keep provider types out of the domain model

Every layer of the app needs to describe "a message" and "a model reply" —
the Anthropic SDK already has types for both.

**Other options considered:**
- Pass the SDK's own objects around the whole app
- Pass raw dicts in the wire format
- Define our own plain types and translate at one boundary

**Decision:** Our own dataclasses (`Message`, `InferenceConfig`,
`InferenceResponse`), defined in `models.py`. Only `client.py` ever touches
the SDK's actual objects. Check: `grep -rn "anthropic" src/` matches one
file.

**Reverse if:** The domain model starts duplicating most of the SDK's own
complexity (tool calls, thinking blocks, citations) — then it needs a
richer content model, not the removal of this boundary.

**Trade-off:** A few lines of translation code per type, in exchange for
the rest of the app never having to care when the SDK changes.
