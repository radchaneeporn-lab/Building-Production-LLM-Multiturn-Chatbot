# 0020: Gate the endpoint with a shared passphrase and Postgres rate limits

**Date:** 2026-09-14
**Status:** Accepted

**Context:**
0018 put `/chat` on the public internet and 0019 narrowed the public surface to
one service — and said so plainly in its postscript: *"Narrowing the surface is
not securing it."* Backlog §5's `Done when:` has been the same sentence since
0009: *"/chat is no longer an open, unmetered proxy to a paid model."* Until
today both halves of that were true. Anyone who found the URL could spend my
Anthropic credits, in unlimited quantity, anonymously.

Two distinct problems, routinely conflated:

- **Who may call this** — an access problem.
- **How much may be spent** — a cost problem. Note that solving the first does
  not solve the second: a handful of authorised users can run up an unbounded
  bill without ever doing anything wrong.

The constraint on the answer is that this project has **no migration tooling**
(0017's still-open gap) and a **live database with rows in it**. Any design
requiring a non-trivial schema change has to bring a migration story with it.

**Options:**
1. Shared passphrase → signed cookie, checked at the proxy; a required shared
   header between proxy and backend; request and token limits counted in
   Postgres.
2. Per-user accounts — a `users` table, hashed passwords, sessions owned by a
   user id.
3. No login at all; rate limit by IP only.
4. API keys in an `Authorization` header, issued by hand.
5. Put an authenticating reverse proxy / platform auth in front of everything.

**Chose:** (1), on all three axes.

*Access.* A shared passphrase adds **no tables**, which is the whole reason it
fits today: `CREATE TABLE IF NOT EXISTS` covers the two new counter tables
because they start empty, and nothing existing changes shape. It matches the
actual audience — me, and people I send a link to.

*Enforcement — both layers.* The proxy checks the visitor's cookie; the backend
independently requires a shared `X-Internal-Key` that only the proxy knows, and
`main_api.py` **refuses to boot** without it. The argument is not hypothetical:
earlier today a command run to *read* domains created one, and the backend was
briefly on the public internet. Under "backend is private because it has no
domain," that window was fully open. Two independent controls mean one mistake
is not an exposure.

*Limits — Postgres, two dimensions.* Requests per identity per hour bound abuse;
output tokens per day, globally, bound the bill. Only the second maps onto money,
because tokens are the billed unit — twenty short messages and twenty long ones
pass the same request limit and cost very differently. Counters live in Postgres
because an in-process dict resets on every deploy (and this app deploys on every
push) and protects exactly one replica — the same "local primitive for a
distributed problem" trap 0017 rejected for `turn_index`.

The identity limited is a **random id minted at login and carried in the signed
cookie**, not the passphrase — which is shared and therefore identifies nobody —
and not the IP, which behind a platform proxy is often the proxy's.

**Rejected:**
(2) is the honest answer and the wrong step *today*: a `users` table, a foreign
key onto existing `conversations` rows, password hashing, and a real migration
against a live database — using tooling this project does not have. It converts
"add auth" into "add auth and solve 0017's migration gap," and the second half
is the larger job. It stays the destination.
(3) caps spend but authorises nobody, and IPs are shared by whole offices and
rotated in seconds; it slows casual abuse only.
(4) is right for scripts and non-browser clients — 0019's own `Reverses when` —
but a browser has nowhere safe to keep a key, so it would have needed a login
flow anyway to be usable from the UI.
(5) is the least code and the most vendor coupling, and would have taught me
nothing about the mechanism. Reconsider the moment there is more than one
service to protect.

**Reverses when:**
- **More than one person needs their own conversations.** A shared passphrase
  means a shared identity: everyone who signs in can create sessions, and
  nothing stops one visitor guessing another's `session_id` (0009's UUID4s are
  unguessable, but nothing *checks ownership*). The first time "my chats" must
  mean something, this becomes (2).
- **The passphrase needs rotating or revoking per person.** One secret means one
  blast radius — a leak locks out everyone or nobody.
- **A non-browser client appears.** Cookies are a browser mechanism; a script
  wants (4). Both can coexist, but the backend would need to accept two
  credential types.
- **Failed logins need to cost something.** Today a wrong password gets a fixed
  400 ms delay and nothing else. That is a speed bump, not a lockout.
- **The daily budget starts refusing real users.** That is the signal to move
  from one global budget to per-identity quotas — at which point "who is this"
  has to be durable, i.e. (2) again.

**What I know:**
- **A cookie is untrusted input.** The browser stores it and the user can edit
  it, so `authenticated=true` would be a suggestion. An HMAC signature over the
  payload, with a server-only secret, is what makes it a claim — verified with
  `timingSafeEqual`, and with the expiry *inside* the signed payload so it
  cannot be extended by hand.
- **Signed is not encrypted.** The cookie's contents are readable by anyone
  holding it. Fine for a random id and a timestamp; never for anything secret.
- **`httpOnly` / `secure` / `sameSite` each stop a specific attack** — script
  theft via XSS, interception over plaintext, and cross-site forgery — and none
  substitutes for the signature.
- **The atomic upsert is the correct counter.** `INSERT ... ON CONFLICT DO
  UPDATE SET count = count + 1 RETURNING count` does the read and the write in
  one statement, so there is no gap to race in. This is the same bug class 0017
  had to fix in `append()` with `FOR UPDATE`, avoided here by never separating
  the read from the write. Windows are part of the primary key, so nothing ever
  resets a counter — a new hour is a new row, the append-only reasoning of 0008.
- **429 and 503 are different claims.** 429 means *you* should slow down and a
  retry will work; 503 means the *service* is out of budget and retrying sooner
  changes nothing. `Retry-After` is forwarded through the proxy explicitly,
  because a client that has to guess is how a retry storm starts.
- **The budget is checked before inference and recorded after**, because output
  tokens are unknowable in advance. It can therefore overshoot by up to one call
  per concurrent request — accepted, and the reason the word is *budget*.
- **A UI gate is an affordance, not a control.** Hiding the chat form is
  convenience; `/api/chat` returning 401 is the security.

**What I don't know yet → fundamentals to learn:**
- **Failed logins are not rate limited.** The 400 ms delay is arbitrary and I
  chose it by feel. A determined guesser still gets unlimited attempts against a
  human-chosen passphrase. The counter infrastructure to fix this now exists and
  is not wired to the login route — the obvious next hour of work.
- **Signed tokens cannot be revoked.** Logout clears the browser's cookie; a
  copy taken beforehand stays valid until it expires. Real revocation needs
  server-side session state. I've accepted a 7-day window without deciding
  whether 7 days is right.
- **Secret rotation is undefined.** Changing `COOKIE_SECRET` signs everyone out;
  changing `INTERNAL_API_KEY` needs both services updated, and there is an
  ordering where one is redeployed before the other and every request 401s.
  Zero-downtime rotation means accepting two valid secrets at once, which
  nothing here does.
- **`X-Client-Id` and the IP fallback are both weak in ways I can't yet
  quantify.** Clearing cookies mints a fresh identity and a fresh allowance;
  `request.client.host` behind a platform proxy may be the platform. I have not
  checked which it is on Railway, and `X-Forwarded-For` parsing is its own
  minefield (trusting a client-supplied header is worse than not trying).
- **Nothing is measured.** `usage_daily` now records tokens per day, which is
  the raw material for backlog §6's "what did this conversation cost" — but the
  number is not surfaced anywhere, and there is no alert before the budget is
  reached. A cap that is hit silently is an outage.
- **No tests, still.** Every claim above was verified by hand with `curl`
  (401 without a key, 401 on a wrong key, 401 with a forged signature, 200 when
  signed, 429 with `Retry-After: 861`, 503 on budget). These are the most
  obviously testable behaviours in the codebase and backlog §7 is still empty.

**Pillar pressure:** Security bought — the endpoint is no longer anonymous, the
backend requires a credential independent of network topology, and the bill has
a ceiling for the first time. Charged to operational excellence (three new
secrets that must agree across two services, with no rotation story) and to
cost/efficiency in a small way (two extra Postgres round trips per message, on
a second connection pool). Charged most honestly to *simplicity*: a
`/chat` that anyone could call was one function; it is now a cookie format, a
signature, a shared header, two counter tables and two failure modes with
distinct status codes — and it still does not know who anyone is.
