# 0004: Give history ownership to the caller

*Superseded by [0005](0005-address-conversations-by-id-not-by-object.md)*

The API itself has no memory — "conversation" only exists because the
client resends the whole history every call. Something has to own that
list.

**Other options considered:**
- Keep the history on the API client object itself
- Move history into its own object, one per conversation

**Decision:** A `Conversation` object owns the messages list; the API
client (`LLMClient`) stays a stateless pipe that takes history in and
returns a reply.

**Reverse if:** The object itself needs to survive across processes — it
did, almost immediately (see 0005).

**Trade-off:** One shared client object holding one shared history breaks
the moment two people are chatting at once — a privacy bug, not just a
performance one.
