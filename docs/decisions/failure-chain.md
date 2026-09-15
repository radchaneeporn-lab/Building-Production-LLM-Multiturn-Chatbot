# The Build, Step by Step

Fifty-nine things that broke, in the order they broke, and the concept
each one taught. Nothing here was added because it looked professional —
every step is a direct response to something that failed at the step
before it.

## Phase 1 — One call

01. Stateless inference — the model has no memory; you resend the history every turn
02. Structured messages — turns as role/content pairs, not one glued-together string
03. Anti-corruption layer — wrap the SDK's types in your own, don't pass them around
04. Adapter — one file owns the vendor SDK
05. Streaming transport — keep long calls from timing out

## Phase 2 — Memory

06. Encapsulated conversation state — give the conversation an owner, not a loose variable
07. Session identifier — hand out a string instead of an object, so it survives being resumed
08. Repository pattern — put an interface between logic and storage
09. Structural typing — match on shape (`Protocol`), not inheritance

## Phase 3 — Persistence

10. Durable store — save to disk, not memory, so conversations survive a restart
11. Append-only rows — one row per message; cheap inserts, no rewriting history
12. Ordering as data — a `turn_index` column, never insertion order
13. Unguessable identifiers — random UUIDs, since sequential IDs let anyone browse other users' data

## Phase 4 — Context economics

14. The context window — there's a ceiling, and you pay for the whole prompt again every turn
15. Window plus rolling summary — keep recent turns verbatim, compress the rest
16. Incremental computation — update the summary by one turn at a time, not from scratch
17. Prompt caching — a stable prefix gets billed less; don't make it churn
18. Strict role alternation — the API requires user/assistant to alternate; work around it, don't fight it
19. Persist only after success — a failed call should leave nothing to clean up
20. Token accounting — count and store tokens once, at write time

## Phase 5 — Serving

21. HTTP API — anything that speaks HTTP is now a client, not just your own script
22. Composition root and lifespan — build the app's objects once at startup, not per request
23. Stateless service — hold capabilities, not state, so any worker can serve any request
24. DTO — the wire format is a contract, kept separate from the internal data model
25. Validation at the boundary — reject bad input at the door, with a clear error
26. CORS — the browser blocks cross-origin calls unless the server allows it
27. Race condition — two requests touching the same conversation at once can corrupt it

## Phase 6 — Packaging and config

28. Containerization — ship the environment with the code, as one artifact
29. Ephemeral layer vs. volume — a container's filesystem resets on rebuild; only a volume survives
30. Config in the environment — anything that differs per deployment shouldn't be baked into the build
31. Images are immutable — a source change needs a rebuild; an env change just needs a restart
32. Precedence chain — an explicit value beats a default, an env var beats both
33. Single source of truth — one function decides a config value, not four copies of it
34. Variable substitution — `${VAR:-default}` lets the shell override a value; a literal doesn't
35. Dotenv parsing rules — `.env` is a key/value format, not safe for arbitrary text

## Phase 7 — Scaling out

36. Client-server database — a file has one writer; a real database server supports many
37. Connection pool — keep a set of live connections ready, instead of opening one per request
38. Fail fast — a bad config should crash the app at startup, not fail a request later
39. Readiness vs. liveness — "started" and "able to serve traffic" are different things
40. Pessimistic locking — lock a row before reading it, so two writers can't collide
41. Physical integrity ≠ logical consistency — no duplicate keys doesn't mean no confused replies
42. Migrations — changing a schema that already has data needs its own tooling
43. Lazy import — an optional backend shouldn't force everyone to install its driver
44. Data migration — swapping databases moves no data; that's a separate job
45. Client state vs. server state — the server has the truth; a page refresh shouldn't lose it
46. Tooling drift — a script can keep "succeeding" while quietly pointing at the wrong thing

## Phase 8 — Going public

47. Build-time vs. runtime config — the same variable, read at two different moments, is two different mechanisms
48. Backend for frontend — let the frontend's own server forward the call, so there's no cross-origin request to configure
49. PID 1 and signal handling — a shell as the container's main process won't forward shutdown signals
50. Port injection — the platform decides which port to use, not the image
51. Address families — some private networks are IPv6-only; binding the wrong one fails silently
52. Read-only-looking commands — a "just checking" command can still change something

## Phase 9 — Paying for strangers

53. Signed cookies — a cookie the browser can edit needs a signature the server alone can produce
54. Constant-time comparison — comparing secrets with `==` can leak them through timing
55. Defense in depth — two independent checks, so one mistake isn't a full exposure
56. Fail closed — a missing security setting should block access, not default to open
57. Atomic upsert — read-and-write as one database statement, so there's no gap to race in
58. Rate limit vs. cost limit — capping requests isn't the same as capping the bill
59. 429 vs. 503 — tell the client whether retrying will actually help

---

## The three questions that explain most of it

1. **Where does the state live, and who's allowed to write it?** — memory → session ID → store → durability → ordering → concurrency (steps 6–13, 27, 36–41)
2. **What has to change without a rebuild?** — config, baked in vs. read at runtime (steps 28–35)
3. **What happens on the second concurrent user, and the second process?** — stateless services, pooling, readiness (steps 21–23, 36–39)

## Still open

- Two people chatting into the same conversation at once can still get a
  reply computed against a stale view — the rows stay ordered, but the
  conversation itself can interleave oddly (step 41).
- No schema migration tooling — the first change to a live table has
  nothing to lean on (step 42).
- No read endpoint — refreshing the browser loses the chat, even though
  it's safely stored (step 45).
