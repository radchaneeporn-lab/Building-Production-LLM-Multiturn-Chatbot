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

**What I know:**
- That the LLM API is stateless and history is re-sent by the client every turn.
- That shared mutable state on an infrastructure object becomes cross-user
  data leakage the moment there is more than one user.
- That per-conversation state must be keyed by conversation.

**What I don't know yet → fundamentals to learn:**
- **What "shared" actually means in Python.** I asserted that one `LLMClient`
  instance would interleave conversations. That is true — but *why* depends on
  the concurrency model, and I have not learned the three:
  - **Threads:** one process, shared memory, true interleaving. The GIL means
    only one thread runs Python bytecode at a time, but that does not make
    multi-step operations atomic (see 0014).
  - **Async / event loop:** one thread, cooperative switching only at `await`
    points. Different interleaving hazards, fewer of them.
  - **Processes / workers:** separate memory. A module-level global is *not*
    shared between them, which is why in-process state fails silently at 2+
    workers rather than loudly.
  Knowing which one FastAPI is using for my code (both, depending on `def` vs.
  `async def`) is the prerequisite for reasoning about any of this.
- **Race conditions and atomicity.** "Two things happen at once" needs to become
  precise: what an atomic operation is, what a critical section is, and why
  read-then-write is the classic unsafe pattern.

**Pillar pressure:** Security (isolation between users) was the decisive one,
ahead of any performance or elegance argument.
