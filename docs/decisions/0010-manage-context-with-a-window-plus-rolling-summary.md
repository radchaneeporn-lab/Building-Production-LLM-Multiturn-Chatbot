# 0010: Manage context with a window plus a rolling summary

**Date:** 2026-08-12 (recorded retroactively)
**Status:** Accepted

**Context:**
Because the full history is re-sent every turn, input tokens grow with turn
count and the cost of a conversation grows roughly quadratically. Left
alone, history eventually exceeds the context window and the call fails with
a 400 — but the bill becomes the problem long before correctness does. This
is the dominant variable cost in the system, and it's driven entirely by
user behaviour.

**Options:**
1. Do nothing until the 400 arrives.
2. Hard window — keep the last N turns, drop the rest.
3. Summarise everything, keep nothing verbatim.
4. Window + summary: last N turns verbatim, everything older folded into a
   rolling summary.

**Chose:** (4), `keep_last_n_turns=4`. Recent turns stay word-for-word
because users refer back to exact phrasing; older turns get compressed
because what survives from them is names, facts, and decisions, not wording.

The summary is rolling, not recomputed. The store keeps `(summary_text,
summarized_through_turn)`, and each call folds in only the turn that just
aged out. Recomputing from scratch would re-read the whole old segment on
every turn — O(n) LLM work per turn, and O(n²) over a conversation, exactly
the cost curve this decision exists to flatten.

**Rejected:**
(2) silently forgets — the model loses the user's name at turn 5 with no
error to notice. (3) loses the verbatim recent context users depend on. (1)
isn't a strategy.

**The load-bearing sub-decision:** truncation only affects what's sent.
`ChatService.send()` still persists the complete, untruncated pair. The
store is the permanent record; truncation is a read-time view over it.
Compressing the stored record would be irreversible data loss to save disk
space that costs almost nothing — a bad trade either way.

**Reverses when:**
- A fixed turn count is the wrong trigger. Real budgets are in tokens, and
  four turns of pasted stack traces is a very different prompt from four
  turns of chat. `Message.token_count` is already persisted specifically so
  a token-budget trigger can sum stored counts instead of re-tokenising.
  That upgrade is wired for, not yet built.
- Prompt caching gets introduced, which changes the arithmetic: cached
  prefix tokens are far cheaper, so aggressive truncation may stop paying
  for itself.

**What I know:**
- Why input cost grows quadratically over a conversation.
- Why an incremental fold beats recomputation, and the complexity argument
  for it.
- That the stored record and the sent prompt are different things, and only
  one of them should be lossy.

**What I don't know yet:**
- **Cost attribution.** I know cost grows. I can't answer "what did user X
  cost last month" or "which conversation is most expensive," because usage
  comes back per call and is never aggregated. Unit economics — define the
  unit (a conversation? a user-month?), then instrument it. Without this the
  product can't be priced or capped.
- **Quality measurement.** The sharpest gap. Truncation degrades quality by
  design, and I have no way to detect it. If the 4-turn window is too
  aggressive, nothing fails — answers just quietly get worse. Build a small
  eval set and score against it, so context changes have a measurable effect
  instead of a vibe. For a non-deterministic system, evaluation *is* the
  regression test.
- **Prompt caching mechanics.** Referenced in 0011 and in code comments as a
  reason for design choices, but not implemented and not fully understood:
  what makes a prefix cacheable, how breakpoints work, cache lifetime, and
  billing.
- **Tokenisation.** `count_tokens()` is treated as an oracle. Knowing
  roughly how BPE works, and why token count isn't proportional to character
  count (especially for non-English text and code), would make budget
  reasoning less superstitious.
- **Caching as a general pattern.** Prompt caching is one instance. Cache
  key design, TTL, invalidation, staleness, hit rate — this applies again at
  the session-cache layer later.

**Pillar pressure:** Cost optimisation, primarily — a business constraint
(margin per conversation) expressed as a policy in the service layer.
Secondarily reliability (avoids the context-limit failure). Traded against
fidelity: summarised turns lose detail, and that loss is permanent within
the prompt even though the underlying record stays intact.
