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
every single turn — O(n) LLM work per turn, and therefore O(n^2) over a
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

**What I know:**
- Why input cost grows quadratically over a conversation.
- Why an incremental fold beats recomputation, and the complexity argument for
  it.
- That the stored record and the sent prompt are different things, and only one
  of them should be lossy.

**What I don't know yet → fundamentals to learn:**
- **Cost attribution.** I know cost grows. I cannot answer "what did user X
  cost last month" or "which conversation is most expensive," because usage is
  returned per call and never aggregated anywhere. Learning goal: unit
  economics — define the unit (a conversation? a user-month?), then instrument
  to measure it. Without this, the product cannot be priced or capped.
- **Quality measurement / evaluation.** This is the sharpest gap. Truncation
  degrades quality by design, and I have **no way to detect it**. If the
  4-turn window is too aggressive, nothing fails — answers just quietly get
  worse. Learning goal: build a small eval set and score against it, so
  context-management changes have a measurable effect rather than a vibe.
  For a system with a non-deterministic component, evaluation *is* the
  regression test.
- **Prompt caching mechanics.** Referenced in 0011 and in the code comments as
  a reason for design choices, but not implemented and not fully understood:
  what makes a prefix cacheable, how breakpoints work, how long a cache lives,
  and how it is billed.
- **Tokenisation.** `count_tokens()` is treated as an oracle. Knowing roughly
  how BPE works — and why token count is not proportional to character count,
  especially for non-English text and code — would make budget reasoning less
  superstitious.
- **Caching as a general pattern.** Prompt caching is one instance. The general
  concepts — cache key design, TTL, invalidation, staleness, hit rate — apply
  again at the session-cache layer later.

**Pillar pressure:** Cost optimisation, primarily — this is a business
constraint (margin per conversation) expressed as a policy in the service layer.
Secondarily reliability (avoids the context-limit failure). Traded against
fidelity: summarised turns lose detail, and that loss is permanent within the
prompt even though the underlying record is intact.
