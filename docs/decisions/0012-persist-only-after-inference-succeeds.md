# 0012: Persist only after inference succeeds

**Date:** 2026-08-12 (recorded retroactively)
**Status:** Accepted

**Context:**
A turn touches an unreliable dependency (the provider API) and a reliable
one (the store), and has to leave the store consistent whether the call
succeeds or fails. `Conversation.send()` appended the user message first,
which meant a failed call left a dangling user turn — needing a
`try/except` with a `pop()` to undo the write. That works, but the cleanup
path is code that only runs when things are already going wrong: the code
least likely to be tested and most likely to be wrong.

**Options:**
1. Append user turn, infer, append assistant turn; roll back on failure.
2. Wrap the whole turn in a transaction.
3. Order the operations so failure needs no cleanup: build the prompt
   without mutating anything, and write only after `infer()` returns.

**Chose:** (3). In `ChatService.send()`, `recent_history + [user_msg]`
builds a new list rather than mutating the loaded one; nothing is persisted
until `infer()` returns. If it raises, the `append()` line is simply never
reached, and the store still holds a clean history.

**Rejected:**
(1) is correct but keeps a rollback path alive forever. (2) doesn't help —
the transaction would have to span a multi-second network call to a third
party, holding a database lock open the whole time.

**The rule this generalises to:** reordering operations so failure needs no
cleanup beats writing cleanup code. Where it applies, it removes a whole
class of bug rather than handling it.

**Reverses when:** Streaming becomes the primary path. A stream can fail
partway through, after real tokens have already reached the user — at which
point "nothing was written" is no longer obviously right, since the user
saw output the transcript won't contain. That's a real design question, not
a mechanical port, and deserves its own record.

**Known gap:** this makes the turn safe against failure, not against
concurrency. Two simultaneous `send()` calls on one session both load the
same history and both append — see
[0014](0014-concurrency-safety-for-the-sqlite-store.md).

**What I know:**
- Operation ordering can eliminate a rollback path instead of handling it.
- Holding a database transaction across a slow third-party call is a bad
  idea.
- Building a new list instead of mutating one is what makes the rollback
  unnecessary.

**What I don't know yet:**
- **Failure modes, precisely.** I treat "`infer()` raises" as one case. It's
  several with different correct responses: a 4xx (my bug, don't retry), a
  429 (retry with backoff), a 5xx (retry), a timeout (unknown outcome — the
  call may have succeeded and I may be charged). The timeout case is the
  interesting one, and I currently handle none of them explicitly.
- **Delivery semantics.** At-most-once, at-least-once, exactly-once — and
  why exactly-once is generally unachievable without idempotency at the
  receiver. The theory under the retry question in 0002.
- **Two-system consistency.** A turn writes to a database and calls an
  external paid API, with no transaction spanning both. If the API call
  succeeds and the database write then fails, I've paid for a response the
  user never sees and the transcript never records. The outbox pattern,
  sagas, compensating actions — the standard vocabulary for "I can't make
  two systems atomic."
- **Idempotency keys.** The concrete tool for making a retried request safe.
- **Partial failure in streaming.** Named in "Reverses when" above and
  genuinely open: what's the correct persistence behaviour when the user has
  already seen half an answer?

**Pillar pressure:** Reliability. Costs nothing — purely a matter of
statement order.
