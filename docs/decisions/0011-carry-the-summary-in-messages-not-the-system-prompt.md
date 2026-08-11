# 0011: Carry the summary in messages, not the system prompt

**Date:** 2026-08-12 (recorded retroactively)
**Status:** Accepted

**Context:**
0010 produces a summary of aged-out turns. It has to go somewhere in the
request. The system prompt is the intuitive home — it reads like context, and
it is where "background information" conventionally lives.

**Options:**
1. Append the summary to `config.system`.
2. Insert it as a new synthetic message.
3. Prepend it into the content of the first message of the kept window.

**Chose:** (3).

**Rejected:**

(1) fails on **cache economics**, not on correctness. `system` is the one part
of a request designed to be byte-identical for an entire conversation, which is
what makes it coverable by a single prompt-cache breakpoint. The summary changes
every time the window advances. Putting a churning value into the one stable
block converts the best cache prefix in the request into a guaranteed miss —
precisely inverting the mechanism. Keeping it in `messages` costs nothing extra,
because the messages array was already changing turn-to-turn: a sliding window
is not an append-only log, so it was never a stable prefix to begin with.

(2) fails on the **API contract**. Messages must strictly alternate
user/assistant and start with user. The kept window already starts with a user
message, so a synthetic message is either a second consecutive user turn or an
assistant turn in the leading position — both invalid. Prepending into the
existing first message's content changes zero roles, so alternation stays as
valid as it already was.

**Reverses when:** The provider offers first-class server-side conversation
compaction, or a request shape with a dedicated slot for derived context that is
independently cacheable.

**Worth noting:** this is one decision constrained by two unrelated systems —
a caching cost model and a request-format rule. Neither is visible in the code
that results, which is a good illustration of why the log exists at all: the
final line looks arbitrary, and reconstructing the reasoning from scratch would
take an afternoon.

**Pillar pressure:** Cost optimisation (preserves cache viability) and
reliability (stays inside the format contract).
