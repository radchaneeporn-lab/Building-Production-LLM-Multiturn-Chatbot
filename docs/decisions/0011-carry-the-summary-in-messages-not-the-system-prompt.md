# 0011: Carry the summary in messages, not the system prompt

**Date:** 2026-08-12 (recorded retroactively)
**Status:** Accepted

**Context:**
0010 produces a summary of aged-out turns. It has to go somewhere in the
request. The system prompt is the intuitive home — it reads like context,
and it's where "background information" conventionally lives.

**Options:**
1. Append the summary to `config.system`.
2. Insert it as a new synthetic message.
3. Prepend it into the content of the first message of the kept window.

**Chose:** (3).

**Rejected:**

(1) fails on cache economics, not correctness. `system` is the one part of a
request designed to stay byte-identical for the whole conversation, which is
what lets a single prompt-cache breakpoint cover it. The summary changes
every time the window advances. Putting a churning value into the one stable
block turns the best cache prefix in the request into a guaranteed miss —
exactly backwards. Keeping it in `messages` costs nothing extra, because the
messages array was already changing turn to turn: a sliding window was never
a stable prefix to begin with.

(2) fails on the API contract. Messages must strictly alternate
user/assistant and start with user. The kept window already starts with a
user message, so a synthetic message is either a second consecutive user
turn or an assistant turn in the leading position — both invalid. Prepending
into the existing first message's content changes zero roles, so alternation
stays exactly as valid as before.

**Reverses when:** The provider offers first-class server-side conversation
compaction, or a request shape with a dedicated slot for derived context
that's independently cacheable.

**Worth noting:** this decision is constrained by two unrelated systems — a
caching cost model and a request-format rule — and neither is visible in the
resulting code. That's a good illustration of why the log exists at all: the
final line looks arbitrary, and reconstructing the reasoning from scratch
would take an afternoon.

**What I know:**
- A cache prefix has to be stable to be worth anything, and putting a
  changing value into a stable block destroys the benefit.
- The alternation rule of the messages array, and why it forced the
  placement.

**What I don't know yet:**
- **Cache key design.** What goes in a cache key, why a key that varies per
  request has a 0% hit rate, and how to split stable from volatile parts of
  a payload. Applies well beyond prompt caching — same reasoning behind
  HTTP caching and CDN behaviour.
- **Cache invalidation and TTL.** What happens when the cached thing becomes
  wrong, and how a system notices. Stale reads are the classic cost of
  caching.
- **Hit rate as a metric.** I reason about caching qualitatively ("this
  would be a miss"). The quantitative version — measure hit rate, compute
  the cost delta — is what turns this from an argument into a decision. I
  currently measure nothing.
- **Layered caching.** Prompt cache at the provider, response cache in the
  app, session cache in memory or Redis — three caches with three different
  invalidation stories. Worth mapping before adding the second one.

**Pillar pressure:** Cost optimisation (preserves cache viability) and
reliability (stays inside the format contract).
