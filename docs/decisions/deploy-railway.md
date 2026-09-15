# Deploying to Railway

The runbook for putting this project on Railway, written right after doing
it the first time — so the order below is the order that works, not the
order the docs imply. Every gotcha in the last section actually happened.

**Decisions this implements:** [ADR 0018](0018-deploy-to-a-managed-container-platform-with-managed-postgres.md)
(platform + managed Postgres) and [ADR 0019](0019-make-the-frontend-the-only-public-surface.md)
(frontend public, backend private). This file is the how; those are the why.

**What you end up with:**

```
browser ──https──> <app>.up.railway.app        frontend  public   :$PORT
                          │ server-side fetch
                          ▼
                   chatbot.railway.internal    backend   private  :8000
                          │
                          ▼
                   postgres.railway.internal   database  private  :5432
```

One public URL. The backend and the database are only reachable from
inside the project's private network.

---

## Before you start

- The code is committed and pushed to GitHub. Railway builds from the
  remote, not your working tree — uncommitted changes deploy nothing.
- `.env` is gitignored and has never been committed. Check, don't assume:
  ```bash
  git log --all --oneline -- .env      # must be empty
  git log --all -S "sk-ant-" --oneline # must be empty
  ```
- Know whether your repo is public or private. If it's private, step 2 is
  mandatory and easy to forget.

---

## 1. Install the CLI and log in

```powershell
npm install -g @railway/cli
railway login          # opens a browser; use --browserless if it can't
railway whoami         # confirm before going further
```

When Railway's authorization screen asks about workspace scope, pick
**Selected workspaces**, not "All workspaces" — the latter also covers
workspaces you create in future.

## 2. Grant the GitHub App access to the repo

Do this before creating any service. Logging into Railway with GitHub
proves your identity; it does not let Railway read your repositories.
Those are two separate grants, and skipping this produces a confusing
failure several steps later (`Repository ... not found or is not
accessible`).

Go to **https://github.com/apps/railway-app** → **Install** → your account
→ **Only select repositories** → pick this repo.

Verify: https://github.com/settings/installations should now show Railway
with a **Configure** button. If it instead says *"Railway App has not been
installed on any accounts you have access to,"* you're looking at the
OAuth App entry (the login grant), and the install hasn't happened.

## 3. Create the project

```powershell
railway init            # prompts for workspace + project name
railway status          # confirm it linked to this directory
```

## 4. Add the database

```powershell
railway add --database postgres
```

Railway provisions it, attaches a volume, and exposes `DATABASE_URL`. You
write no code for this: `load_store()` in `src/chatbot/config.py` reads
`DATABASE_URL` and builds a `PostgresStore` when it's set. ADR 0017's
convention paying off.

## 5. Create the backend service

```powershell
railway add --service chatbot `
  --repo <owner>/<repo> --branch main `
  --variables 'HOST=::' `
  --variables 'PORT=8000' `
  --variables 'DATABASE_URL=${{Postgres.DATABASE_URL}}' `
  --variables 'MODEL_NAME=claude-haiku-4-5-20251001' `
  --variables 'MAX_TOKENS=712' `
  --variables 'SYSTEM_PROMPT=You are a helpful assistant. Be concise.'
```

Three of those are load-bearing:

- **`HOST=::`** — Railway's private network is IPv6-only. A process bound
  to `0.0.0.0` starts fine, logs nothing unusual, and is unreachable. The
  Dockerfile's `CMD` reads `$HOST` for exactly this.
- **`PORT=8000`** — pins the port so the frontend's `API_URL` can name it.
  Railway injects `PORT` anyway; setting it explicitly makes the value
  predictable.
- **`${{Postgres.DATABASE_URL}}`** — a reference, not a copied string. It
  tracks the database if credentials rotate, and it's what draws the
  dependency arrow on the project canvas.

### Auth and rate-limit secrets (ADR 0020)

Generate three random values once and keep them somewhere safe:

```powershell
python -c "import secrets; print('INTERNAL_API_KEY=' + secrets.token_urlsafe(32))"
python -c "import secrets; print('COOKIE_SECRET='   + secrets.token_urlsafe(32))"
python -c "import secrets; print('APP_PASSWORD='    + secrets.token_urlsafe(12))"
```

- `INTERNAL_API_KEY` goes on both services and the values must match — the
  frontend's proxy sends it, the backend requires it. `main_api.py`
  refuses to boot without it, so a missing value is a failed deploy, not a
  silent hole.
- `COOKIE_SECRET` and `APP_PASSWORD` go on the frontend only — used
  server-side in the route handlers and never reach a browser.
- `RATE_LIMIT_PER_HOUR` (default 20) and `DAILY_OUTPUT_TOKEN_BUDGET`
  (default 50000) go on the backend.

Set each one with `--set-from-stdin` (same reasoning as the API key
below):

```powershell
railway variables --service chatbot  --set-from-stdin INTERNAL_API_KEY
railway variables --service frontend --set-from-stdin INTERNAL_API_KEY
railway variables --service frontend --set-from-stdin COOKIE_SECRET
railway variables --service frontend --set-from-stdin APP_PASSWORD
```

### The API key — never on a command line

```powershell
railway variables --service chatbot --set-from-stdin ANTHROPIC_API_KEY
# paste the key, then Ctrl+Z, Enter
```

Or pipe it from `.env` without it ever being printed:

```bash
grep '^ANTHROPIC_API_KEY=' .env | sed 's/^[^=]*=//' | tr -d '\r\n' \
  | railway variables --service chatbot --set-from-stdin ANTHROPIC_API_KEY
```

Do not run `railway variables --service chatbot` to check it worked. That
listing prints every value in full, including the key. `Set variables
ANTHROPIC_API_KEY` is the confirmation. (See gotcha #1.)

## 6. Create the frontend service

```powershell
railway add --service frontend `
  --repo <owner>/<repo> --branch main `
  --variables 'API_URL=http://chatbot.railway.internal:8000'
```

`API_URL` is read server-side at request time by
`frontend/app/api/chat/route.js`. It's not `NEXT_PUBLIC_*` and never
reaches the browser, which is why the internal hostname is correct here.

### Set the root directory — required, and not available as a CLI flag

Both services come from one repo but build different Dockerfiles. Without
this the frontend builds the repo-root `Dockerfile` (the Python backend)
and you get a second copy of the API wearing the frontend's name.

**Dashboard:** `frontend` → Settings → Source → **Root Directory** =
`frontend`

**Or via the API:**

```powershell
railway api 'mutation { serviceInstanceUpdate(serviceId: "<frontend-service-id>", environmentId: "<environment-id>", input: { rootDirectory: "frontend" }) }'
```

Get both IDs from `railway status`. Verify before deploying:

```powershell
railway api 'query { project(id: "<project-id>") { services { edges { node { name serviceInstances { edges { node { rootDirectory } } } } } } } }'
```

`frontend` must read `"frontend"`. If it reads `null`, the next build is
wrong.

## 7. Deploy

```powershell
railway redeploy --service chatbot  --from-source -y
railway redeploy --service frontend --from-source -y
```

`--from-source` pulls the latest commit from GitHub. Plain `redeploy`
re-runs an existing deployment and fails when there isn't one yet.

Watch them:

```powershell
railway logs --service chatbot --build     # build output
railway logs --service chatbot             # runtime
railway status
```

**What a healthy backend boot looks like:**

```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://[::]:8000
```

`[::]` means the IPv6 bind worked. `Application startup complete` means
`lifespan` opened the Postgres pool — since ADR 0017 made a bad
`DATABASE_URL` a refusal to boot, this line is proof the database
connected and the schema exists.

## 8. Healthcheck (dashboard)

`chatbot` → Settings → Deploy → **Healthcheck Path** = `/health`

Railway then waits for a 200 there before routing traffic to a new
deploy.

## 9. One public domain — on the frontend only

```powershell
railway domain --service frontend --port <port from the deploy log>
railway domain status <domain-id>      # wait for Sync status: ACTIVE
```

Next.js standalone honours Railway's injected `PORT`; read the actual
value from the deploy log (`▲ Next.js ... Network: http://0.0.0.0:8080`)
and pass that.

Never run bare `railway domain --service chatbot`. With no domain present
it creates one, publicly exposing the backend. The read-only form is
`railway domain list`. (See gotcha #2.)

## 10. Verify

```bash
URL=https://<your-app>.up.railway.app

curl -s -o /dev/null -w "%{http_code}\n" $URL                 # 200

R=$(curl -s -X POST $URL/api/chat -H "Content-Type: application/json" \
     -d '{"message":"Hi, my name is Ada."}')
echo $R
SID=$(echo $R | python -c "import sys,json;print(json.load(sys.stdin)['session_id'])")

curl -s -X POST $URL/api/chat -H "Content-Type: application/json" \
     -d "{\"message\":\"What is my name?\",\"session_id\":\"$SID\"}"
```

Turn 2 recalling the name proves the whole chain: proxy → private backend
→ Postgres → history replayed to the model.

Since ADR 0020 those calls need a session cookie, so log in first and
reuse the jar:

```bash
J=$(mktemp)
curl -s -c $J -X POST $URL/api/login \
  -H "Content-Type: application/json" -d '{"password":"<APP_PASSWORD>"}'
curl -s -b $J -X POST $URL/api/chat \
  -H "Content-Type: application/json" -d '{"message":"Hi, my name is Ada."}'
```

And check the gates actually refuse — both should fail:

```bash
curl -s -o /dev/null -w "no cookie      -> %{http_code}\n" \
  -X POST $URL/api/chat -H "Content-Type: application/json" -d '{"message":"hi"}'
curl -s -o /dev/null -w "bad password   -> %{http_code}\n" \
  -X POST $URL/api/login -H "Content-Type: application/json" -d '{"password":"wrong"}'
```

Expect 401 for both. A 200 on the first means the deploy is running code
from before 0020.

Then confirm the backend is not public:

```powershell
railway domain list --service chatbot     # "No domains found" is CORRECT
railway domain list --service frontend    # exactly one, ACTIVE
```

"No domains found" for `chatbot` is the deploy succeeding. If it ever
lists one, that's the bug.

## 11. Tear down when you're finished

```powershell
railway down                 # remove the most recent deployment
railway delete               # delete the whole project
```

Three services bill continuously. See *Cost* below.

---

## Gotchas, in the order they bit

**1. `railway variables --service <name>` prints secrets in full.**
No masking, no flag needed. The `--help` text says `-k/--kv` "prints raw
values," which implies the default doesn't. It does. Setting a secret with
`--set-from-stdin` and then "verifying" it is how you leak it. If this
happens: rotate the key immediately at console.anthropic.com.

**2. `railway domain --service <name>` creates a domain.**
It reads like a query. With no domain present it generates one, and for
the backend that means briefly publishing an unauthenticated endpoint to
the internet. Use `railway domain list` to read, `railway domain delete
<domain> --service <name> --yes` to undo.

**3. GitHub login ≠ repository access.**
`Repository ... not found or is not accessible` means the GitHub App
isn't installed on the repo — see step 2. Private repos always need it.

**4. Root directory has no CLI flag.**
Dashboard or GraphQL only. Silently wrong builds otherwise, and the build
looks successful.

**5. `railway redeploy` without `--from-source` fails on a service that
has never deployed.** There's no previous deployment to re-run.

**6. `railway add --database postgres` gives you `postgres-ssl:18`,**
while `docker-compose.yml` runs `postgres:16-alpine`. Nothing in this
schema is version-sensitive, but dev and prod aren't the same engine
version — worth knowing before you blame something else.

**7. `HOST=::`.** Repeated because it costs an hour if you miss it: the
service is up, healthy-looking, and unreachable.

---

## Cost

Rough idle floor at Railway's rates (~$0.000231/GB-minute of RAM):

| Service | Idle RAM | ≈ /month |
|---|---|---|
| Postgres | ~200 MB | ~$2.00 |
| chatbot | ~120 MB | ~$1.20 |
| frontend | ~100 MB | ~$1.00 |
| | | **≈ $4–5** |

A $5 trial credit and a 30-day trial window expire at roughly the same
time.

**The bill that can actually hurt is Anthropic's, not Railway's.**
`/api/chat` has no authentication and no rate limit — a public URL is an
open path to a paid model for anyone who finds it. `MAX_TOKENS` caps cost
per call, nothing caps calls per hour. Don't post the URL publicly, and
delete the project when you're done experimenting. This is the gap
tracked as backlog §5 in [`decisions/README.md`](README.md), and deploying
is what made it urgent rather than theoretical.
