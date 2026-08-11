# 0004: Give history ownership to the caller

**Date:** 2026-08-12 (recorded retroactively)
**Status:** Superseded by [0005](0005-address-conversations-by-id-not-by-object.md)

**Context:**
The `/v1/messages` endpoint is stateless: there is no session on the provider's
side. Multi-turn is an illusion the client constructs by re-sending the entire
history every call. Something must own that list. The obvious candidate was
`LLMClient`, since it already exists and already talks to the API.

**Options:**
1. `LLMClient` keeps `self.history` and appends internally.
2. `LLMClient.infer()` takes `messages: list[Message]` from the caller; a
   separate `Conversation` object owns the list.

**Chose:** (2). `infer()` became a stateless pipe — full history in, response
out. `Conversation` holds `self.history` plus cumulative token counters, and is
the only thing that appends.

**Rejected:**
(1) collapses under the very first multi-user deployment: one `LLMClient`
instance means one history, so concurrent conversations interleave into each
other. That is not a performance bug, it is a **privacy incident** — user A
reads user B's messages. Per-conversation state must be keyed by conversation,
never held on a shared infrastructure object.

**Reverses when:** Already did — see 0005. `Conversation` correctly separated
state from transport, but kept the state *in a Python object*, which means it
dies with the process and cannot be handed to a different worker. Both
constraints became binding at the HTTP step. The file is retained as the
in-memory reference implementation and as the readable version of the
append-user / infer / append-assistant loop.

**Pillar pressure:** Security (isolation between users) was the decisive one,
ahead of any performance or elegance argument.
