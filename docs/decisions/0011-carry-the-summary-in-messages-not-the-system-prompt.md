# 0011: Carry the summary in messages, not the system prompt

The rolling summary from 0010 has to go somewhere in the request. The
system prompt looks like the natural place — it reads like background
context.

**Other options considered:**
- Append it to the system prompt
- Insert it as a new, separate message
- Prepend it into the content of the first kept message

**Decision:** Prepend it into the first kept message's content.

**Reverse if:** The provider offers first-class server-side conversation
compaction.

**Trade-off:** None really — the messages array already changes every
turn, so this costs nothing extra. Putting it in the system prompt instead
would have broken prompt caching, since that block is supposed to stay
identical across the whole conversation.
