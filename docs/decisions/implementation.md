# Implementation: how this version is built

What exists **as of 2026-09-14**, deployed and verified. The companion documents
answer different questions:

| Document | Question |
|---|---|
| this file | *How is it built, and what runs where?* |
| [`README.md`](README.md) | *Why was each choice made?* (ADR 0001–0020) |
| [`failure-chain.md`](failure-chain.md) | *What broke, and what did each break teach?* (59 steps) |
| [`deploy-railway.md`](deploy-railway.md) | *How do I deploy it again?* |

---

## 1. The shape of the system

Three processes and one database, with exactly one of them reachable from the
internet.

```
                    ┌──────────────────────────────────────────┐
   browser ─https──▶│ frontend  (Next.js 16, standalone)        │  PUBLIC
                    │                                          │
                    │  page.js ── login gate ── chat UI        │
                    │  /api/login   verify passphrase          │
                    │               issue signed cookie        │
                    │  /api/chat    verify cookie              │
                    │               attach X-Internal-Key      │
                    │               attach X-Client-Id         │
                    └───────────────────┬──────────────────────┘
                                        │ server-side fetch, private network
                                        ▼
                    ┌──────────────────────────────────────────┐
                    │ chatbot  (FastAPI + uvicorn)              │  PRIVATE
                    │                                          │
                    │  require_internal_key   → 401             │
                    │  limiter.check(identity)→ 429 / 503       │
                    │  ChatService.send()                       │
                    │  limiter.record(tokens)                   │
                    └─────────┬────────────────────┬───────────┘
                              │                    │
                              ▼                    ▼
                    ┌──────────────────┐   ┌──────────────────┐
                    │ PostgreSQL        │   │ Anthropic API    │
                    │ sessions          │   │ Messages         │
                    │ messages          │   └──────────────────┘
                    │ rate_limit_…      │        PRIVATE
                    │ usage_daily       │
                    └──────────────────┘
```

Three properties hold this together, and each one is a decision rather than an
accident:

- **One public surface.** The backend has no domain. It is reachable only at
  `chatbot.railway.internal:8000`. *(ADR 0019)*
- **Two independent credentials.** A visitor needs a cookie; the proxy needs a
  shared header. Neither substitutes for the other. *(ADR 0020)*
- **Nothing is configured at build time.** Every environment-specific value is
  read at process start or per request, so one image runs anywhere. *(0015, 0019)*

---

## 2. What one message actually does

Following a single "hello" end to end is the fastest way to understand the
codebase — every layer appears exactly once.

| # | Where | What happens |
|---|---|---|
| 1 | `app/page.js` | `fetch("/api/chat")` — **same origin**, so no CORS |
| 2 | `app/api/chat/route.js` | `verifySession(cookie)` → HMAC check → 401 if bad |
| 3 | ↳ | forward to `$API_URL/chat` with `X-Internal-Key` + `X-Client-Id` |
| 4 | `main_api.py` | `require_internal_key` → constant-time compare → 401 |
| 5 | ↳ | `limiter.check(identity)` → atomic upsert → 429 / 503 |
| 6 | `service.py` | `store.load()` — replay history from Postgres |
| 7 | `truncation.py` | window + rolling summary if the history is long |
| 8 | `client.py` | `.stream()` + `get_final_message()` → Anthropic |
| 9 | `service.py` | `store.append()` — persist **only after** success *(0012)* |
| 10 | `main_api.py` | `limiter.record(in, out)` — bill the token budget |
| 11 | ↳ | `ChatResponse` → proxy → browser |

Two things about the order matter. The credential check (4) and the limit
check (5) both happen before any model call, so a refused request costs
nothing. And persistence (9) happens after inference succeeds, so a failed
call leaves no orphaned user message.

---

## 3. Where the code lives

```
src/chatbot/            the domain — no HTTP, no framework
  models.py             Message, InferenceConfig, InferenceResponse   (0001)
  client.py             the ONLY file that imports anthropic          (0002, 0003)
  storage.py            ConversationStore Protocol + 3 implementations (0006-0008)
  truncation.py         window + rolling summary                      (0010, 0011)
  service.py            ChatService.send() — the orchestration        (0012)
  limits.py             RateLimiter Protocol + Postgres counters      (0020)
  config.py             environment → objects, in one place           (0016)

main_api.py             HTTP entry point: routes, auth, lifespan      (0013, 0018-0020)
main_service.py         same service, stdin loop (laptop, SQLite)
main_multiturn.py       earlier learning step
main_plain.py           earlier learning step

frontend/app/
  page.js               login gate + chat UI
  lib/auth.js           HMAC cookie sign/verify                       (0020)
  api/login/route.js    POST login, GET session, DELETE logout        (0020)
  api/chat/route.js     the server-side proxy                         (0019, 0020)

Dockerfile              backend image — $PORT, $HOST, exec uvicorn    (0015, 0018)
frontend/Dockerfile     multi-stage Next.js standalone build
docker-compose.yml      the whole stack locally
```

The dependency rule the layout enforces: **`src/chatbot/` knows nothing about
HTTP, and `models.py` imports nothing at all.** `grep -rn "anthropic" src/`
returns exactly one file. Those are mechanical checks, and they are the point of
ADRs 0001 and 0002.

---

## 4. Two seams, and what they buy

Both follow the same shape — a `Protocol`, several implementations, one
environment-driven factory in `config.py`. This is why the same code runs as a
CLI on a laptop and as a deployed service with no branching in the callers.

| Seam | Implementations | Selected by |
|---|---|---|
| `ConversationStore` | `InMemoryStore`, `SQLiteStore`, `PostgresStore` | `DATABASE_URL` set? |
| `RateLimiter` | `NullRateLimiter`, `PostgresRateLimiter` | `DATABASE_URL` set? |

Consequence: `python main_service.py` needs no database server, no rate limiter,
and no secrets beyond an API key. The deployed service gets Postgres and real
limits. Neither `ChatService` nor any route function contains an `if` about it.

---

## 5. The data

```sql
sessions(id PK, created_at, summary_text, summarized_through_turn)
messages(session_id, turn_index, role, content, token_count, created_at,
         PRIMARY KEY (session_id, turn_index))
rate_limit_counters(key, window_start, count, PRIMARY KEY (key, window_start))
usage_daily(day PK, input_tokens, output_tokens, requests)
```

Three ideas repeat across all four tables:

- **Append-only.** Messages are inserted, never rewritten (0008). Rate-limit
  windows are part of the primary key, so a new hour is a new row and nothing
  ever resets a counter (0020).
- **Ordering is explicit data.** `turn_index`, never insertion order.
- **Writes that read are single statements.** `append()` takes
  `MAX(turn_index)+1` under `SELECT … FOR UPDATE` (0017); the rate counter uses
  `INSERT … ON CONFLICT DO UPDATE … RETURNING count` (0020). Both exist because
  read-then-write in two statements is a race — the same bug, met twice.

---

## 6. Configuration

Every value is read from the environment. Nothing environment-specific is
compiled into either image.

**`chatbot`**

| Variable | Purpose | Missing → |
|---|---|---|
| `ANTHROPIC_API_KEY` | the model | SDK error |
| `DATABASE_URL` | Postgres; also selects the store *and* limiter | falls back to SQLite |
| `INTERNAL_API_KEY` | shared secret from the proxy | **refuses to boot** |
| `HOST` | `::` on IPv6-only private networks | unreachable, silently |
| `PORT` | platform-injected | healthchecks fail |
| `MODEL_NAME`, `MAX_TOKENS`, `SYSTEM_PROMPT` | inference knobs | defaults |
| `RATE_LIMIT_PER_HOUR`, `DAILY_OUTPUT_TOKEN_BUDGET` | limits | 20 / 50000 |

**`frontend`**

| Variable | Purpose | Missing → |
|---|---|---|
| `API_URL` | where the backend is (server-side only) | localhost fallback |
| `APP_PASSWORD` | the shared passphrase | login returns 500 |
| `COOKIE_SECRET` | HMAC signing key | throws; no cookie issued |
| `INTERNAL_API_KEY` | **must equal the backend's** | every message 401s |

None is `NEXT_PUBLIC_*`, so none reaches the browser. A `NEXT_PUBLIC_` prefix on
any of the bottom three would compile the secret into the page.

The sharpest edge here: `INTERNAL_API_KEY` must be identical in two places,
and nothing verifies that it is. Missing is caught loudly (the backend won't
start); different is caught by nothing — both services look healthy and every
message returns 401. This cost a real debugging cycle on 2026-09-14.

---

## 7. Running it

**Locally** — everything, including Postgres:

```bash
docker compose up -d --build          # http://localhost:3000, password: letmein
docker compose logs -f chatbot
```

**Locally, no containers** — SQLite, no rate limits, no auth:

```bash
python main_service.py
```

**Deployed** — see [`deploy-railway.md`](deploy-railway.md).

---

## 8. What this version does not do

Stated plainly, because documentation that overclaims is worse than none.
Each item links to where it's tracked.

- **No per-person identity.** The passphrase is shared, so everyone who signs in
  is the same "who". Nothing checks that a `session_id` belongs to the caller —
  a visitor holding someone else's id can read that conversation. *(0020, 0009)*
- **No migrations.** The schema is `CREATE TABLE IF NOT EXISTS`. The first
  change to an existing table against live rows has no tooling behind it.
  *(0017, 0018 — the most likely thing to hurt next)*
- **No backups you have tested.** Railway runs them; nobody here has restored
  one. RPO and RTO remain unstated. *(0007 → 0017 → 0018, asked three times,
  answered none)*
- **No tests.** Every claim in this document was checked by hand with `curl`.
  *(backlog §7)*
- **One replica only, deliberately.** Two concurrent turns on one session still
  both load the same history, so the conversation can interleave incoherently
  even though the rows stay correctly ordered. *(0014 Open, 0017)*
- **No streaming.** `infer()` blocks until generation completes; the UI shows
  nothing until the whole reply lands. *(0003 — its `Reverses when` is now the
  most user-visible gap)*
- **No revocation, no rotation story.** Logging out clears the browser's cookie;
  a copy taken earlier stays valid for up to 7 days. Changing either shared
  secret has a window where requests fail. *(0020)*
- **Failed logins are not rate limited.** A fixed 400 ms delay, nothing more.
  The counter infrastructure exists and is not wired to the login route. *(0020)*

---

## 9. If you are picking this up cold

Read in this order:

1. **This file** — the shape.
2. **`failure-chain.md`** — 59 failures in causal order. It explains *why* the
   shape is this shape better than any architecture diagram can.
3. **`README.md` §Learning backlog** — what is knowingly unfinished, ordered by
   what blocks the next step.
4. **Any ADR whose title sounds surprising.** 0003, 0011, 0012 and 0019 each
   record a choice whose reasoning is invisible in the code.

The one rule the log keeps: a record is never rewritten to say something
different. Decisions that changed are `Superseded by NNNN`; decisions that were
merely *confirmed by reality* carry a **Postscript** (see 0018 and 0019). What
was believed at the time is part of the record.
