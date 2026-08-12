# 0006: Define the store seam as a Protocol

**Date:** 2026-08-12 (recorded retroactively)
**Status:** Accepted

**Context:**
Storage is the single most likely thing to change in this system: dict today,
SQLite now, Postgres or Redis later, possibly two of them layered. The service
layer must not care which. The question is what shape the contract takes.

**Options:**
1. No contract — `ChatService` constructs `SQLiteStore` directly.
2. An abstract base class (`ABC`) that every store inherits from.
3. A `typing.Protocol` — structural typing, no inheritance required.

**Chose:** (3). `ConversationStore` declares six methods; `InMemoryStore` and
`SQLiteStore` satisfy it without importing or mentioning it. `ChatService`
receives a store through its constructor and never constructs one, so the
composition root in `main_service.py` / `main_api.py` is the only place a
concrete implementation is named.

**Rejected:**
(1) makes the service untestable without a filesystem and welds it to one
engine. (2) works, but forces every adapter to inherit from a class that lives
in this codebase — awkward for an adapter wrapping a third-party client, and it
couples the adapters to each other through a shared base. Structural typing
keeps them mutually independent.

**Reverses when:** Nothing foreseeable. Worth noting what the Protocol
deliberately does *not* hide: `load()` raising `KeyError` for an unknown session
is part of the contract, and both implementations match on it. An interface that
agrees on signatures but disagrees on error behaviour is not a seam — callers
end up silently depending on one implementation's failure mode.

**Design detail worth preserving:** the interface has two halves with different
semantics. `load`/`append` treat messages as an append-only immutable record —
`append()` rather than `save(full_history)` means turn N writes two rows instead
of 2N, and a stale caller can never shrink a conversation. `get_summary`/
`set_summary` are the opposite: a mutable, derived cache that could be
regenerated from the messages if lost. Keeping them on separate method pairs
makes that distinction visible in the type, not just in a comment.

**What I know:**
- Structural vs. nominal typing, and why `Protocol` decouples adapters from
  each other.
- Dependency injection at a composition root.
- That error behaviour is part of an interface contract, not an implementation
  detail.
- The difference between an append-only record and a regenerable cache.

**What I don't know yet → fundamentals to learn:**
- **Testing against a seam.** The seam exists specifically to make testing
  possible, and there are currently **no tests in this repo**. That is the
  largest gap in the project. Learning goal: fakes vs. mocks vs. stubs (and why
  a real `InMemoryStore` is usually better than a mock), and how to run one test
  suite against both implementations to prove they behave identically —
  the technique that would catch a `KeyError` mismatch automatically.
- **Interface evolution.** I have already added two methods (`get_summary`,
  `set_summary`) to a Protocol with two implementations. With ten
  implementations, or one owned by someone else, that is a breaking change.
  How interfaces version: additive-only rules, default implementations,
  splitting a fat interface into narrow ones.
- **Where seams should *not* go.** Every abstraction has a cost. I have one
  seam and it is clearly justified; the general skill is recognising when a
  seam is speculative — an interface with exactly one implementation and no
  foreseeable second one is usually premature.

**Pillar pressure:** Operational excellence (testability, changeability). The
cost is one extra indirection; the benefit is that 0007 becomes a one-line
change at the composition root.
