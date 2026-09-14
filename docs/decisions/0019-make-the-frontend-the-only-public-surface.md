# 0019: Make the frontend the only public surface

**Date:** 2026-09-14
**Status:** Accepted

**Context:**
0018 put both containers on a platform, which turns a detail that was harmless
in Compose into a real coupling. The browser's backend URL is
`NEXT_PUBLIC_API_URL`, and `NEXT_PUBLIC_*` values are **inlined into the client
bundle at `next build`** (`frontend/Dockerfile:29-31` says so; the Next.js
self-hosting guide confirms it). Locally that cost nothing — `localhost:8000` is
always correct. Deployed, it means:

- the frontend image cannot be built until the backend's public URL exists,
- changing that URL is an image rebuild, not a restart,
- one image cannot serve two environments.

The same string is then needed from the other side: `FRONTEND_ORIGIN` feeds
`CORSMiddleware` (`main_api.py:138`), which compares it to the browser's
`Origin` header. So one fact — "where the other service is" — is written in two
places, baked at two different times (one at image build, one at process boot),
and a mismatch fails as a browser-side CORS error that never reaches app code.

And underneath the ergonomics: `/chat` publicly reachable is an unauthenticated
path to a paid model that anyone who finds it can spend money through.

**Options:**
1. A Route Handler at `frontend/app/api/chat/route.js` that forwards
   server-side to the backend over the platform's private network. The browser
   only ever calls its own origin.
2. `rewrites()` in `next.config.mjs` pointing `/api/:path*` at the backend.
3. Keep both services public: bake the backend URL at build time, and give
   `FRONTEND_ORIGIN` a comma-separated list so preview/localhost also work.
4. Put both services behind one gateway/reverse-proxy service that owns the
   public domain and routes by path.

**Chose:** (1). It moves "where the backend is" from a build-time constant in a
browser bundle to a runtime server-side variable (`API_URL`), which makes the
frontend image environment-independent — build once, run anywhere, the property
0015 claimed and this was quietly breaking. CORS stops being load-bearing,
because there is no cross-origin request left to permit. The backend needs no
public domain at all. And it puts a server-side seam exactly where the next two
things have to go: authentication and rate limiting (backlog §5), and the SSE
termination point that 0003's `Reverses when:` describes — a Route Handler can
stream a response body through, so choosing it now does not have to be revisited
to get token-by-token delivery later.

**Rejected:**
(2) looks identical and may well be, but `rewrites()` lives in
`next.config.mjs`, and I could not establish from the docs whether the
standalone `server.js` re-evaluates it at boot or reads a destination baked
into the build manifest. If it is the latter, it reproduces the exact
build-time coupling this record exists to remove. A Route Handler has no such
ambiguity — it is a function that runs per request — and rewrites give me
nowhere to put auth.
(3) is the least work and keeps every problem in Context: two public services,
one fact in two places, a rebuild to change a URL, and `/chat` still open.
(4) is the right answer at a different size. A third service to run, health
check and configure, so that two services can share an origin, is more moving
parts than (1) for the same result — and (1) already has a server process in
the request path, so adding one is redundant.

**Reverses when:**
- **A non-browser client needs the API** — a mobile app, a CLI, someone else's
  integration. The moment the backend has a consumer that is not this frontend,
  hiding it behind the frontend is an obstacle rather than a simplification,
  and `/chat` needs a real public contract with real authentication.
- **The proxy hop costs something I can measure.** Every request now passes
  through a Node process before reaching Python. For a call dominated by model
  latency (0003: `infer()` returns only when generation completes) that is
  noise. If it stops being noise, the hop is the thing to remove.
- **The frontend stops being a server.** A static export or an edge-only
  deployment has no server-side runtime to forward from, and this collapses
  back to option (3).
- **Streaming arrives** (0003). The handler keeps working, but it becomes code
  with behaviour — backpressure, cancellation when the user navigates away,
  and a client disconnect that should abort the upstream request rather than
  leak a generation. Today it forwards one JSON body and none of that applies.

**What I know:**
- `NEXT_PUBLIC_*` is build-time inlining into the browser bundle; server-side
  `process.env` in a Route Handler is read at request time. Those are two
  different configuration mechanisms that look like one, and picking the wrong
  one bakes an environment into an image.
- Same-origin requests do not involve CORS at all. CORS was never a feature I
  wanted — it was the cost of a topology, and changing the topology removes it
  rather than configuring it.
- **This is not authentication.** The Next.js docs are blunt that Route
  Handlers are public HTTP endpoints; `/api/chat` on the frontend is exactly as
  open as `/chat` was. What this buys is one public surface instead of two, a
  runtime-configurable URL, and a place where a check *can* live — not a check.
- Keeping `CORSMiddleware` is still right for `npm run dev` against a
  containerised backend, where the two origins genuinely differ. It is now a
  development affordance, not part of the deployed path.

**What I don't know yet → fundamentals to learn:**
- **Whether `rewrites()` reads env at build or at boot** in `standalone`
  output. I chose around the uncertainty instead of resolving it; it is a
  fifteen-minute experiment (`API_URL=x npm run build`, then run with
  `API_URL=y`) and I have not run it.
- **What a forwarding handler must copy, and what it must not.** Method, body,
  content type, status, and error shape are obvious. Which headers it is wrong
  to pass through (`host`, `connection`, hop-by-hop headers), and whether the
  backend should learn the real client IP via `X-Forwarded-For` — needed the
  moment rate limiting is per-IP — I am guessing at.
- **Timeouts, now doubled.** There are two request lifecycles in series: the
  browser→Next hop and the Next→backend `fetch`. `fetch` has its own default
  timeout behaviour, and a generation at `MAX_TOKENS` can be slow. 0003 said I
  could not name the clocks on one request; this adds a whole second set.
- **Server-side fetch and connection reuse.** Every turn opens a connection
  from Node to Python. Whether that pools, and what it costs under concurrency,
  is the same capacity question 0017 raised about the Postgres pool, one layer up.
- **Whether the backend should be private at the network level or merely
  undocumented.** 0018 takes the platform's private-network claim on trust;
  this record spends it.

**Pillar pressure:** Security and operational excellence bought — one public
service instead of two, the paid-model endpoint off the public internet, and a
frontend image that no longer has a deployment environment compiled into it.
Charged to performance efficiency (an extra process hop and a second set of
timeouts on every turn) and to reliability (the frontend is now a hard
dependency of the API, so a frontend deploy is an outage for the API, which it
was not before). The honest summary: this fixed a configuration coupling and
narrowed the attack surface; it did not add a single authorisation check, and
the endpoint is as unmetered as it was yesterday.
