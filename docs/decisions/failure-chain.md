# The Chatbot Failure Chain

Fifty-nine things that broke, in the order they broke, and the concept each
one forced me to learn. Every step names the file I changed and the
decision record it produced.

Read it as a chain: each concept is caused by the previous step's failure.
If a step could be moved somewhere else, it's in the wrong place.

| | |
|---|---|
| Steps | 59, in 9 phases |
| Span | `main_plain.py` → a public URL |
| Records | ADR 0001 → 0020 |
| Companion | [`decisions/README.md`](README.md) |

---

## Phase 1 — One call

### 01 · Stateless inference
> `main_plain.py`

**✕** I sent a prompt, got a reply, printed it. Then I asked a follow-up and the model had no idea what I'd just said.

**↓** Every request is independent — **stateless inference**. The model has no memory; "conversation" is something I construct by resending the past. — *Anthropic Messages API / OpenAI Chat Completions*

### 02 · The messages array
> `models.py` · `Message`

**✕** So I glued the history into one big string. It fell apart the first time a message contained a quote mark and the model started answering its own earlier turn.

**↓** Turns are structured data, not text — a **messages array** of role/content pairs, where the boundary between speakers is a field, not punctuation I hope survives.

### 03 · Anti-corruption layer
> `models.py` · ADR 0001

**✕** I passed the SDK's own response objects around the whole app. An SDK upgrade then broke files that never called the SDK.

**↓** Wrap foreign types at the border and pass my own — an **anti-corruption layer** (older books just call it "the domain model"). The test is mechanical: `grep -rn "anthropic" src/` should hit one file. — *Python dataclasses / Pydantic models*

### 04 · Adapter
> `client.py` · ADR 0002

**✕** Even with my own types, `import anthropic` had spread to five files. Trying a second provider meant editing all five.

**↓** One file speaks the vendor's language and nothing else does — an **adapter** (the port/adapter or "hexagonal" shape). — *client.py / LiteLLM*

### 05 · Streaming transport
> `client.py` · `infer_streaming` · ADR 0003

**✕** A long answer sat in silence and then died on a timeout, with nothing to show for the wait.

**↓** Ask for tokens as they're produced even when I intend to block on the whole answer — **streaming transport** keeps the connection alive and turns one long silence into steady progress. — *SSE / httpx streaming*

---

## Phase 2 — Memory

### 06 · Encapsulated conversation state
> `conversation.py` · ADR 0004

**✕** My history lived in a local list inside `main()`. Worked perfectly for exactly one person at one keyboard.

**↓** Give the conversation an owner — an object that holds its own turns and appends to them, so the loop stops doing bookkeeping. **Encapsulated conversation state**.

### 07 · Session identifier
> ADR 0005 (supersedes 0004)

**✕** To resume a chat, the caller had to still be holding my object. I can't put an object in a URL, a cookie, or a JSON body.

**↓** Hand out a string instead and look the state up by it — a **session identifier**. "Hold the object" → "hold an ID" is the single move that makes everything after this possible.

### 08 · Repository pattern
> `storage.py` · ADR 0006

**✕** An ID needs somewhere to look up, so I called the database directly from my service. Then every test needed a real database file.

**↓** Put an interface between the logic and the storage — the **repository pattern**, a named seam I can swap. Tests get a dict; production gets a database; the service can't tell. — *storage.py / SQLAlchemy repositories*

### 09 · Structural typing
> `ConversationStore` · ADR 0006

**✕** I made the interface a base class, which meant every store had to inherit from mine — including ones I'd want to write later against someone else's code.

**↓** Match on shape, not ancestry: **structural typing** via `Protocol`, versus the **nominal typing** of an ABC. Duck typing the type checker actually enforces. — *typing.Protocol / Go interfaces*

---

## Phase 3 — Persistence

### 10 · Durable store
> `SQLiteStore` · ADR 0007

**✕** My dict-backed store lost every conversation the moment the process exited. Restarting the app was indistinguishable from wiping the database.

**↓** State has to outlive the process — a **durable store**, written to disk rather than held in memory. — *SQLite / PostgreSQL*

### 11 · Append-only rows
> ADR 0008

**✕** I stored each conversation as one JSON blob. Turn 40 meant reading 39 turns, appending one, and rewriting all 40 — and a stale copy could silently shrink a conversation.

**↓** Write only what's new: **append-only, one row per message**. Cheap inserts, no read-modify-write, and the table mirrors how the data actually changes — conversations only grow at the end.

### 12 · Ordering as data
> `turn_index` · ADR 0008

**✕** Rows came back in the order I inserted them. Until one day they didn't, and a reply appeared before the question.

**↓** Never lean on insertion order or rowid — make ordering **explicit, as data**. A `turn_index` column *is* the ordering; the database is free to store rows however it likes.

### 13 · Unguessable identifiers
> ADR 0009

**✕** My session IDs were 1, 2, 3. Anyone holding session 7 could type 6 and read a stranger's conversation.

**↓** Identifiers handed to users must be unguessable — random **UUID4**, because sequential IDs are an enumeration attack waiting to happen (**IDOR**). — *uuid4 / ULID*

---

## Phase 4 — Context economics

### 14 · The context window
**✕** Long conversations got expensive, then slow, then hit a hard error — I was resending the entire history on every single turn.

**↓** There's a ceiling and a meter: the **context window**, and the fact that I pay for the whole prompt again every turn. Cost grows quadratically with conversation length if I do nothing.

### 15 · Window plus rolling summary
> `truncation.py` · ADR 0010

**✕** I dropped the oldest turns to fit. The model promptly forgot the user's name, mentioned once, in turn one.

**↓** Keep recent turns verbatim and compress the rest — a **sliding window plus rolling summary**. Recent wording matters exactly; old turns matter only as facts.

### 16 · Incremental computation
> `summarized_through_turn` · ADR 0010

**✕** My summariser re-read every old turn on every call. Turn 20 summarised turns 1–16, turn 21 re-summarised 1–17 — an extra model call that got slower and pricier forever.

**↓** Only fold in what just changed and cache the result — an **incremental (rolling) computation**: `new = fold(old_summary, turn_that_just_aged_out)`. O(1) per turn instead of O(n).

### 17 · Prompt caching
> ADR 0011

**✕** I put the rolling summary in the system prompt. That made the one part of the request that never changes, change on every turn.

**↓** Providers bill less for a repeated identical prefix — **prompt caching** — so the stable block has to actually stay stable. Churning the system prompt throws away the discount I was set up to get.

### 18 · Strict role alternation
> ADR 0011

**✕** Moving the summary into the messages array returned a 400: two user messages in a row.

**↓** The API demands **strict role alternation** starting with user. I prepended the summary into the existing first message's content instead — zero roles changed, alternation untouched.

### 19 · Persist only after success
> ADR 0012

**✕** An API error mid-turn left the user's message saved with no reply next to it. My cleanup code was a `try/except` that popped it back off.

**↓** Reorder so failure needs no cleanup: compute first, **persist only after success**. If inference raises, I simply never reach the write, and the store was never inconsistent. Beats writing rollback code.

### 20 · Token accounting
> `Message.token_count`

**✕** I wanted per-message token counts, so I re-tokenised the whole history each call — and then found `input_tokens` couldn't be split back up per message anyway.

**↓** **Token accounting** has two shapes: `output_tokens` is exactly the message just generated, `input_tokens` is cumulative for the whole prompt. Count and store each message once, at write time.

---

## Phase 5 — Serving

### 21 · HTTP API
> `main_api.py`

**✕** My CLI while-loop read stdin. One process, one user, one conversation — nothing else could reach it.

**↓** Put it behind a request/response boundary anything can speak — an **HTTP API**. The call site barely changed: ID and text in, reply out, now from a JSON body instead of `input()`. — *FastAPI / Flask*

### 22 · Composition root and lifespan
> `lifespan()` · ADR 0013

**✕** I built the client, store and service inside the route handler, so every single request reopened a database and rebuilt the object graph.

**↓** Build the graph once where the process starts, tear it down where it ends: a **composition root** plus an **application lifespan**. Under HTTP there's no `main()`, so startup needs a defined home. — *FastAPI lifespan / ASP.NET Startup*

### 23 · Stateless service
> `ChatService` · ADR 0013

**✕** Sharing one service across concurrent requests felt reckless — until I looked and found it held no conversation data at all.

**↓** A **stateless service** holds capabilities, not state. Because the conversation lives in the store, any worker, process or replica can serve turn 5 of a chat it's never seen. This is what makes horizontal scaling possible later.

### 24 · DTO
> `ChatRequest` · `ChatResponse`

**✕** I returned my internal result object straight out of the endpoint. Renaming an internal field would silently have changed my public API with no warning.

**↓** The wire format is a contract, separate from the domain type behind it — a **DTO** (older vocabulary: serializer, view model). Mine combines fields from two sources and renames one, so it was never a passthrough anyway. — *Pydantic BaseModel / Django serializers*

### 25 · Validation at the boundary
> Pydantic

**✕** Raw JSON from the network reached my code unchecked — a missing field became an exception deep inside the service instead of a clear rejection at the door.

**↓** Validate untrusted input where it enters, and fail with a precise error naming the field — **schema validation at the boundary**, returning 422 before the handler body ever runs.

### 26 · CORS
> `FRONTEND_ORIGIN` · `frontend/app/page.js`

**✕** I built a browser frontend and its `fetch()` failed with no HTTP status at all — while `curl` against the same URL worked fine.

**↓** The browser blocks cross-origin reads unless the server opts in — **CORS**, enforced client-side, which is exactly why curl and Swagger never hit it. It's the browser refusing, not my server erroring. — *CORSMiddleware / nginx add_header*

### 27 · Race condition
> ADR 0014 · **Open**

**✕** Two requests hit one session at the same moment. Both counted the existing messages, both got N, both wrote turn N — and `turn_index` is my ordering key, so that corrupts order permanently, not just one write.

**↓** Read-then-write with a gap in the middle is the classic **race condition**; the unsafe span is the **critical section**. Naming it didn't fix it — I logged it as unresolved and carried on.

---

## Phase 6 — Packaging and config

### 28 · Containerization
> `Dockerfile` · ADR 0015

**✕** Running it anywhere else meant reproducing my virtualenv, my Python version, my `.env`, and "run from the project root" by hand.

**↓** Ship the environment with the code as one artifact — **containerization**. Same image on my laptop and on the deploy target. — *Docker / Podman*

### 29 · Ephemeral layer vs volume
> `chatbot-data` · ADR 0015

**✕** My database disappeared on every rebuild. The container was doing exactly what it's designed to do; I just hadn't understood where the file lived.

**↓** A container's writable layer is thrown away on restart — only a **volume** survives it. "Ephemeral vs. persistent storage" stopped being a phrase and became a thing I'd watched happen. — *named volumes / Kubernetes PersistentVolume*

### 30 · Config in the environment
> ADR 0015

**✕** Hardcoded paths and `localhost` were correct on my machine and wrong inside a container — and the image can't hold a different value per environment.

**↓** Anything that differs per deployment belongs outside the build — **config in the environment**, the twelve-factor rule. `DB_PATH` and `FRONTEND_ORIGIN` became env vars for exactly this reason.

### 31 · Images are immutable
> `docker compose up --build`

**✕** I edited my Python, refreshed the browser, and saw no change. Refreshed harder. Still nothing — for a full day, because the container was serving yesterday's code.

**↓** An image is an **immutable build artifact**: a snapshot taken at build time, not a live view of my folder. Source change → rebuild. Env-var change → restart only. Knowing which I owe is the whole trick.

### 32 · Precedence chain
> ADR 0016

**✕** I changed `max_tokens` on the dataclass and the running app ignored it. Twice. The default I was editing was never reached by any real entry point.

**↓** Values resolve through a **precedence chain** — an explicit argument beats a field default, an env var beats both. A "default" only applies where nothing else supplies a value, and I had four things supplying one.

### 33 · Single source of truth
> `config.py` · `load_inference_config()` · ADR 0016

**✕** The same three literals were copy-pasted into four entry points. Changing a value properly meant editing four files and hoping I'd found them all.

**↓** One function owns the decision and everything calls it — a **single source of truth** for config. Duplication isn't ugly here, it's a correctness bug with a delay fuse. — *pydantic-settings / Viper*

### 34 · Variable substitution
> `docker-compose.yml`

**✕** I set a shell variable to try a value quickly, and the compose file's hardcoded number won anyway. I'd assumed the shell would override it; I tested it and it doesn't.

**↓** A literal in the compose file is fixed; `${VAR:-default}` is **variable substitution** — the shell can override it, and the default still applies when nothing does. Two different mechanisms that look identical in the file.

### 35 · Dotenv parsing rules
> `.env`

**✕** I moved a prompt into `.env` and half of it vanished. A `#` in the text had been read as a comment; a `$WORD` expanded to nothing. Silently, both times.

**↓** **Dotenv files have parsing rules** — they're a key/value format, not a safe container for arbitrary prose. Secrets yes; sentences no.

---

## Phase 7 — Scaling out

### 36 · Client-server database
> `PostgresStore` · ADR 0017 (supersedes 0007)

**✕** My race from step 27 had no fix available: SQLite hides it behind a lock on the entire file, which serialises every writer in the process and protects nothing once a second process exists.

**↓** A file database has one writer by design; a **client-server database** is built for many. The constraint wasn't performance, it was that "more than one process" was off the table. — *PostgreSQL / MySQL*

### 37 · Connection pool
> `ConnectionPool`

**✕** I carried over SQLite's one-shared-connection habit. A remote connection can only run one statement at a time, and my framework runs sync handlers on a thread pool.

**↓** Keep a set of live connections and lend them out — a **connection pool**. Opening one per request instead would pay a TCP and auth handshake on every message. — *psycopg_pool / PgBouncer*

### 38 · Fail fast
> `open=True` · `wait()`

**✕** The pool opened lazily, so a wrong connection string looked completely fine at boot and surfaced as a failed user request minutes later.

**↓** Make startup prove its dependencies — **fail fast**. Open eagerly and wait, so a bad URL is a process that refuses to start while I'm still watching, not a mystery 500 during someone's chat.

### 39 · Readiness vs liveness
> `healthcheck` · `condition: service_healthy`

**✕** On a cold start my app raced the database and lost — Postgres takes a couple of seconds to initialise, and my container was already trying to connect.

**↓** "Started" and "able to serve" are different states — **readiness vs. liveness**. `depends_on` alone waits for the former; a healthcheck plus `condition: service_healthy` waits for the latter. — *pg_isready / Kubernetes readinessProbe*

### 40 · Pessimistic locking
> `SELECT … FOR UPDATE` · ADR 0017

**✕** Ported straight across, my count-then-insert still raced — a different engine doesn't fix a logic bug.

**↓** Take the lock before reading: **pessimistic locking** with `SELECT … FOR UPDATE`. And **lock granularity** is the real win — one session's row, so different conversations still write in parallel. Verified: 5 concurrent writers, 24 rows, 24 distinct indexes.

### 41 · Physical integrity ≠ logical consistency
> **still unresolved**

**✕** I'd fixed the collision and caught myself calling the concurrency problem solved. It isn't: two simultaneous turns still both read the same history, so the rows are perfectly ordered and the conversation can still make no sense.

**↓** **Physical integrity is not logical consistency.** No duplicate keys says nothing about whether the reply made sense given what else was happening. Still open — the candidates are a lock across the whole turn, **optimistic concurrency control** with a version column, or a per-session queue.

### 42 · Migrations
> **not yet built**

**✕** My schema setup is `CREATE TABLE IF NOT EXISTS`, which quietly does nothing useful the moment a deployed database already holds rows in the old shape.

**↓** Changing a schema that has data underneath it is its own discipline — **migrations**: versioned, ordered, and backward-compatible with code that's still running. — *Alembic / Flyway*

### 43 · Lazy import
> `PostgresStore.__init__`

**✕** I imported the Postgres driver at the top of the storage module. That instantly broke every SQLite-only run in any environment that hadn't reinstalled dependencies — including my own virtualenv.

**↓** An optional backend must not be a mandatory import — **lazy import** inside the class that needs it, with an error message that says what to install. Whoever asks for the backend pays for it.

### 44 · Data migration
> **outstanding**

**✕** The new database came up clean and empty — and my old conversations were still sitting in the SQLite volume, invisible to the running app.

**↓** Swapping engines moves no data. **Data migration** is a separate job from schema or engine migration, and it needs its own script, its own verification, and a decision about the cutover window.

### 45 · Client state vs server state
> **no `GET /sessions/{id}`**

**✕** I refreshed the browser and my whole chat vanished — even though every message was safely in Postgres the entire time.

**↓** The server has the truth; the page only had a copy in memory. **Client state vs. server state** — and I'd never built a read endpoint, so the UI had no way to ask for a transcript it already owned.

### 46 · Tooling drift
> `inspect_db.py` · **stale**

**✕** I ran my own inspection script to check the data. It printed conversations from July — from a dead file nothing uses — and looked entirely successful doing it.

**↓** Tooling rots silently when the system moves under it — **tooling drift**. A tool that fails loudly is fine; one that succeeds against the wrong source teaches you something false.

## Phase 8 — Going public

### 47 · Build-time vs. runtime configuration
> `frontend/app/api/chat/route.js` · ADR 0019

**✕** The browser's backend URL was `NEXT_PUBLIC_API_URL`, which the framework compiles into the JavaScript bundle at build time. So I couldn't build the frontend image until the deployed backend's URL existed, and changing that URL meant rebuilding the image rather than restarting it.

**↓** The same variable read at two different moments is two different mechanisms — **build-time vs. runtime configuration**. Moving the lookup server-side made one image work in every environment. — *`NEXT_PUBLIC_*` / twelve-factor config*

### 48 · Backend for frontend
> `route.js` · ADR 0019

**✕** Two public services meant one fact — "where is the backend" — written in two places: baked into the browser bundle on one side, handed to `CORSMiddleware` on the other. A mismatch failed as a browser CORS error that never reached my code.

**↓** Let the frontend's own server forward the call — a **backend-for-frontend** proxy. Same-origin requests have no CORS to configure, and the backend needs no public address at all. — *BFF pattern / reverse proxy*

### 49 · PID 1 and signal handling
> `Dockerfile` · `CMD`

**✕** Expanding `$PORT` forced shell-form `CMD`, which put `sh` at PID 1. A shell doesn't forward signals to its child: `SIGTERM` on redeploy went to the shell, uvicorn never saw it, and the `lifespan` teardown from step 33 silently stopped running.

**↓** **PID 1 has special signal responsibilities.** `exec` replaces the shell with the real process so it receives the signal itself. The tell is exit code 137 — SIGKILL after a timeout — instead of 0. — *`exec` / tini / docker init*

### 50 · Port injection
> `Dockerfile` · ADR 0018

**✕** `CMD ... --port 8000` was hardcoded. A platform decides which port it routes to and injects it as `$PORT`; my container would have started perfectly and failed every healthcheck.

**↓** The runtime environment chooses the port, not the image — **port injection**. Cheap to verify before deploying: run the image with `PORT=9000` and check it bound 9000.

### 51 · Address families
> `HOST=::` · ADR 0018

**✕** The backend deployed, reported healthy, and was unreachable from the frontend. Nothing in either log said why.

**↓** The private network was IPv6-only, and `0.0.0.0` binds **IPv4 only** — two **address families**, where listening on the wrong one fails silently instead of loudly. `::` accepts both. — *dual-stack sockets*

### 52 · Read-only-looking commands
> operational

**✕** Twice I ran a command to check something and it changed something instead. `railway variables <service>` printed a live API key in full, forcing a rotation. `railway domain --service chatbot` created a domain instead of listing one, publishing the backend to the internet for about thirty seconds.

**↓** A verification step has a blast radius too. Before running something to "just check," know whether it can write, and prefer the explicit read (`... list`). A `set` command that reports success needs no reading back.

## Phase 9 — Paying for strangers

### 53 · Signed cookies
> `app/lib/auth.js` · ADR 0020

**✕** My first instinct for "remember they logged in" was a cookie saying so. A cookie is stored by the browser, and the browser belongs to the user — `authenticated=true` is something anyone can type into devtools.

**↓** Attach an **HMAC signature** the server alone can produce. The client may read and edit the cookie, but can't forge a signature for what it changed. Signed, not encrypted: the contents stay readable, so nothing secret goes in one. — *HMAC-SHA256 / JWT*

### 54 · Constant-time comparison
> `secrets.compare_digest` · `crypto.timingSafeEqual`

**✕** I compared the secret with `==`.

**↓** String equality returns as soon as two bytes differ, so how long it takes leaks how many leading bytes were right — a **timing attack** recovers a secret byte by byte. Comparing secrets uses a **constant-time comparison**; it costs nothing and is simply the tool for the job.

### 55 · Defense in depth
> `require_internal_key` · ADR 0020

**✕** The backend was safe because it had no public domain. Then a command I ran to read domains created one (step 52), and "safe" evaporated for thirty seconds.

**↓** Network topology is a setting any command can flip; a required credential is a property of the code. Two independent controls so one mistake isn't an exposure — **defense in depth**, argued from an incident rather than a principle.

### 56 · Fail closed
> `main_api.py` · startup check

**✕** I wrote the check as "if the key is configured, verify it." Forgetting to configure it would then leave the endpoint wide open, and nothing would say so.

**↓** An access control that defaults to allow is not a control. **Fail closed**: the process refuses to boot without its secret — the same fail-fast reasoning as opening the database pool at startup (step 40).

### 57 · Atomic upsert
> `limits.py` · `ON CONFLICT DO UPDATE`

**✕** My first counter was SELECT the count, add one, UPDATE — exactly the read-then-write race from step 27, rebuilt from scratch in a new file.

**↓** `INSERT ... ON CONFLICT DO UPDATE SET count = count + 1 RETURNING count` — an **atomic upsert**. The read and the write are one statement, so there's no gap to race in and no lock required. The window is part of the primary key, so no one ever resets a counter: a new hour is a new row.

### 58 · Rate limit vs. cost limit
> `limits.py` · ADR 0020

**✕** I capped requests per hour and called the cost problem solved. Twenty one-word messages and twenty 712-token messages pass the same limit and cost wildly different amounts.

**↓** A request limit bounds *abuse*; only a **token budget** bounds the *bill*, because tokens are the billed unit. Two limits, two different jobs, and the second is the one that maps onto money.

### 59 · 429 vs. 503
> `rate_limit_handler` · `Retry-After`

**✕** I returned 429 for both "you're too fast" and "the service is out of budget," so a client that backed off politely still got nowhere.

**↓** A status code is a machine-readable claim about what happens if you retry. **429** = slow down, retrying works. **503** = the service is out, retrying sooner changes nothing. Send **`Retry-After`** rather than making clients guess — guessing clients are how retry storms start.

---

# The short version

What to keep once the fifty-nine steps have blurred.

## The smallest honest system to start from

```
One file. Send a messages array to the API, print the reply.
No store. No server. No container.

Everything else here is a response to something specific
that broke — never something added because it looked professional.
```

## Three questions that regenerate the whole list

**1. Where does the state live, and who's allowed to write it?**
Regenerates steps 6–13 and 27, 36–41: memory → session ID → store seam →
durability → ordering → races → locking. Almost every structural decision
falls out of this one.

**2. What has to change without a rebuild?**
Regenerates 28–35: what's baked into the image versus supplied at runtime,
and the precedence chain between the places a value can come from.

**3. What happens on the second concurrent user, and the second process?**
Regenerates 21–23 and 36–39: stateless services, pooling, readiness, and
why a single-writer file quietly caps the whole architecture.

## Seven buckets for recall under pressure

| # | Bucket | Collapses to |
|---|---|---|
| 01 | One call | Stateless inference, structured turns, one file owns the vendor. |
| 02 | Memory | Hold an ID, not an object. Put an interface in front of storage. |
| 03 | Persistence | Append-only rows, ordering as data, unguessable IDs. |
| 04 | Context economics | The window is a ceiling and a meter. Window + rolling summary, computed incrementally. |
| 05 | Serving | Build once at startup. Wire format ≠ domain type. Validate at the door. |
| 06 | Packaging | The image is frozen; config comes from the environment; know the precedence. |
| 07 | Scaling out | Many writers need a server, a pool, readiness, and the narrowest lock that works. |
| 08 | Going public | The platform picks the port, the address family and the config moment — and a command run to "check" can write. |
| 09 | Paying for strangers | Untrusted input includes the cookie you issued; a request limit is not a cost limit. |

## The tell

**Reads as junior:**
> "I moved it to Postgres, so the concurrency problem is solved."

Treats a tool as a fix. Names the technology instead of the failure mode,
and doesn't say what's still broken.

**Reads as senior:**
> "The row lock closed the `turn_index` collision — I verified it with
> five concurrent writers. Two simultaneous turns still compute against a
> stale history, so the rows are ordered and the conversation can still
> interleave. I haven't decided between a turn-length lock and optimistic
> versioning."

Separates what was fixed from what was proven from what's still open, and
names the remaining failure mode precisely enough for someone else to pick
up.

---

## Open threads

Five steps in this chain are unresolved, and together they're the real
backlog:

| Step | Thread | Where it's tracked |
|---|---|---|
| 41 | Logical race across a whole turn | ADR 0014 (Open), ADR 0017 |
| 42 | Schema migrations with live data | `storage.py` footer |
| 44 | Migrating the pre-Postgres conversations | `chatbot-data` volume |
| 45 | No read endpoint; browser refresh loses the chat | `main_api.py` |
| 46 | `inspect_db.py` points at a dead SQLite file | `src/chatbot/inspect_db.py` |
