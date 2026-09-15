# Decision Log

Short write-ups of the choices in this project that would be expensive to
reverse. Not every choice is here — just the ones where the reasoning
isn't obvious from reading the code. Each one covers what else was on the
table, what was decided, what would change the decision, and what it
costs.

## Records

| # | Decision | Status |
|---|---|---|
| [0001](0001-keep-provider-types-out-of-the-domain-model.md) | Keep provider types out of the domain model | |
| [0002](0002-confine-the-anthropic-sdk-to-one-file.md) | Confine the Anthropic SDK to one file | |
| [0003](0003-use-streaming-transport-for-blocking-inference.md) | Use streaming transport for blocking inference | |
| [0004](0004-give-history-ownership-to-the-caller.md) | Give history ownership to the caller | Superseded by 0005 |
| [0005](0005-address-conversations-by-id-not-by-object.md) | Address conversations by ID, not by object | |
| [0006](0006-define-the-store-seam-as-a-protocol.md) | Define the store seam as a Protocol | |
| [0007](0007-use-sqlite-as-the-first-durable-store.md) | Use SQLite as the first durable store | Superseded by 0017 |
| [0008](0008-store-one-row-per-message-with-explicit-ordering.md) | Store one row per message with explicit ordering | |
| [0009](0009-use-uuid4-session-identifiers.md) | Use UUID4 session identifiers | |
| [0010](0010-manage-context-with-a-window-plus-rolling-summary.md) | Manage context with a window plus rolling summary | |
| [0011](0011-carry-the-summary-in-messages-not-the-system-prompt.md) | Carry the summary in messages, not the system prompt | |
| [0012](0012-persist-only-after-inference-succeeds.md) | Persist only after inference succeeds | |
| [0013](0013-build-one-service-instance-per-process-at-startup.md) | Build one service instance per process at startup | |
| [0014](0014-concurrency-safety-for-the-sqlite-store.md) | Concurrency safety for the SQLite store | Open |
| [0015](0015-containerize-with-docker-keep-sqlite-on-a-named-volume.md) | Containerize with Docker; keep SQLite on a named volume | |
| [0016](0016-load-inference-parameters-from-the-environment.md) | Load inference parameters from the environment | |
| [0017](0017-move-the-durable-store-to-postgresql.md) | Move the durable store to PostgreSQL | |
| [0018](0018-deploy-to-a-managed-container-platform-with-managed-postgres.md) | Deploy to a managed container platform, with managed Postgres | |
| [0019](0019-make-the-frontend-the-only-public-surface.md) | Make the frontend the only public surface | |
| [0020](0020-gate-the-endpoint-with-a-shared-passphrase-and-postgres-rate-limits.md) | Gate the endpoint with a shared passphrase and Postgres rate limits | |

## Other docs in this folder

- [`implementation.md`](implementation.md) — how the whole system fits
  together today
- [`failure-chain.md`](failure-chain.md) — the things that broke, in order,
  and what each one led to
- [`deploy-railway.md`](deploy-railway.md) — the exact steps to deploy this
  yourself
