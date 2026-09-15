# 0005: Address conversations by ID, not by object

*Supersedes [0004](0004-give-history-ownership-to-the-caller.md)*

A conversation object can't be put in a cookie, a URL, or a JSON body, and
it dies with the process — a real problem once a request might be handled
by a different server than the one before it.

**Other options considered:**
- Keep the `Conversation` object; add save/load methods to it
- Keep objects alive in a registry inside the process, keyed by ID
- Hold no conversation state at all; address everything by a `session_id` string

**Decision:** The service loads history by ID, does the work, and saves it
back — nothing is kept in memory between requests.

**Reverse if:** Essentially never for this architecture. What changes
instead is what sits behind the store (0007 → 0017), not this.

**Trade-off:** Every request now does a load/save round trip instead of
touching an object already in memory — worth it for letting any server
handle any request.
