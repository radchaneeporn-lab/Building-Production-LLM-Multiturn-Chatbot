# Decision Log

Architecture Decision Records (ADRs) for `Production-Agentic-Multiturn-Chatbot`.

## What goes in here

One record per decision that is **expensive to reverse**. Not every choice —
variable names, formatting, and anything a single commit can undo are not
decisions in this sense. The test: *if I changed my mind in three months,
would it cost me an afternoon or a rewrite?* Afternoon → no record. Rewrite →
record.

## What a record is for

Six months from now, the code will still show *what* you chose. It will not
show what you rejected, what you were optimising for, or what would make the
choice wrong. That context is the part that evaporates, and it is the part
you need when the constraint changes.

## Format

```
# NNNN: <short imperative title>

Date:
Status:            Accepted | Superseded by NNNN | Open

Context:           What forced a choice. Include the constraint, not just the goal.
Options:           What was actually on the table.
Chose:             The decision, plus the reason in one or two lines.
Rejected:          The runners-up and why they lost — this is the highest-value field.
Reverses when:     The condition that makes this decision wrong. Write it now,
                   while you can still see it.
Pillar pressure:   Which of the six architectural concerns this trades against.
```

`Reverses when:` is the field that turns a note into an architecture artifact.
It converts a static choice into a **trigger** — something you can monitor for
rather than rediscover during an incident.

## Conventions

- Four-digit zero-padded number, monotonic, never reused.
- One decision per file. A file is never rewritten to say something different;
  if the decision changes, write a new record and set the old one's status to
  `Superseded by NNNN`. The log is append-only, like your `messages` table —
  and for the same reason (see 0008).
- Titles are imperative and specific: `Store conversation state in SQLite`,
  not `Storage`.

## Current records

| # | Decision | Status |
|---|---|---|
| [0001](0001-keep-provider-types-out-of-the-domain-model.md) | Keep provider types out of the domain model | Accepted |
| [0002](0002-confine-the-anthropic-sdk-to-one-file.md) | Confine the Anthropic SDK to one file | Accepted |
| [0003](0003-use-streaming-transport-for-blocking-inference.md) | Use streaming transport for blocking inference | Accepted |
| [0004](0004-give-history-ownership-to-the-caller.md) | Give history ownership to the caller | Superseded by 0005 |
| [0005](0005-address-conversations-by-id-not-by-object.md) | Address conversations by ID, not by object | Accepted |
| [0006](0006-define-the-store-seam-as-a-protocol.md) | Define the store seam as a Protocol | Accepted |
| [0007](0007-use-sqlite-as-the-first-durable-store.md) | Use SQLite as the first durable store | Accepted |
| [0008](0008-store-one-row-per-message-with-explicit-ordering.md) | Store one row per message with explicit ordering | Accepted |
| [0009](0009-use-uuid4-session-identifiers.md) | Use UUID4 session identifiers | Accepted |
| [0010](0010-manage-context-with-a-window-plus-rolling-summary.md) | Manage context with a window plus rolling summary | Accepted |
| [0011](0011-carry-the-summary-in-messages-not-the-system-prompt.md) | Carry the summary in messages, not the system prompt | Accepted |
| [0012](0012-persist-only-after-inference-succeeds.md) | Persist only after inference succeeds | Accepted |
| [0013](0013-build-one-service-instance-per-process-at-startup.md) | Build one service instance per process at startup | Accepted |
| [0014](0014-concurrency-safety-for-the-sqlite-store.md) | Concurrency safety for the SQLite store | **Open** |

## Adding one

Copy the format block above, take the next number, write it in under ten
minutes. If it takes longer than that, you are writing a design document —
which is a fine thing to write, but it belongs in `docs/design/`, not here.
