# 0010: Manage context with a window plus a rolling summary

**Date:** 2026-08-12 (recorded retroactively)
**Status:** Accepted

**Context:**
Because the full history is re-sent every turn, input tokens grow with turn
count and the cost of a conversation grows roughly quadratically. Left alone,
history eventually exceeds the context window and the call fails with a 400 —
but the bill becomes the problem long before correctness does. This is the
dominant variable cost in the system and it is driven entirely by user
behaviour.

**Options:**
1. Do nothing until the 400 arrives.
2. Hard window — keep the last N turns, drop the rest.
3. Summarise everything, keep nothing verbatim.
4. Window + summary: last N turns verbatim, everything older folded into a
   rolling summary.

**Chose:** (4), `keep_last_n_turns=4`. Recent turns stay word-for-word because
users refer back to exact phrasing; older turns are compressed because what
survives from them is names, facts, and decisions, not wording.

The summary is **rolling, not recomputed**. The store keeps
`(summary_text, summarized_through_turn)`, and each call folds in only the turn
that just aged out. Recomputing from scratch would re-read the whole old segment
every single turn — O(n) LLM work per turn, and therefore O(n²) over a
conversation, which is the exact cost curve this decision exists to flatten.

**Rejected:**
(2) silently amnesias — the model forgets the user's name at turn 5 and there is
no error to notice. (3) loses the verbatim recent context users depend on.
(1) is not a strategy.

**The load-bearing sub-decision:** truncation affects only what is **sent**.
`ChatService.send()` still persists the complete, untruncated pair.
The store is the permanent record; truncation is a read-time view over it.
Compressing the stored record would be irreversible data loss in exchange for
disk space that costs almost nothing — a bad trade in any direction.

**Reverses when:**
- A fixed turn count is the wrong trigger. Real budgets are in tokens, and four
  turns of pasted stack traces is a very different prompt from four turns of
  chat. `Message.token_count` is already persisted specifically so a token-budget
  trigger can sum stored counts instead of re-tokenising. That upgrade is
  pre-wired and not yet built.
- Prompt caching is introduced, which changes the arithmetic: cached prefix
  tokens are far cheaper, so aggressive truncation may stop paying for itself.

**Pillar pressure:** Cost optimisation, primarily — this is a business
constraint (margin per conversation) expressed as a policy in the service layer.
Secondarily reliability (avoids the context-limit failure). Traded against
fidelity: summarised turns lose detail, and that loss is permanent within the
prompt even though the underlying record is intact.
