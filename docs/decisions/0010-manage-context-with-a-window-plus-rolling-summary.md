# 0010: Manage context with a window plus a rolling summary

Because the full history is resent every turn, cost grows the longer a
conversation runs, and eventually it won't fit the model's context window
at all.

**Other options considered:**
- Do nothing until the model returns an error
- A hard window — keep the last N turns, drop everything older
- Summarize everything, keep nothing verbatim
- A window plus a rolling summary

**Decision:** Keep the last 4 turns word-for-word; fold anything older into
a summary that updates one turn at a time instead of being recomputed from
scratch.

**Reverse if:** A fixed turn count stops matching reality — real budgets
are in tokens, not turns. Token counts are already stored per message, so
this upgrade is ready to build.

**Trade-off:** Summarized turns permanently lose detail from what gets sent
to the model, even though the full, untouched record is still stored.
