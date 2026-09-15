# Production-Agentic-Multiturn-Chatbot

A multi-turn chatbot backed by Claude, with a password-gated Next.js frontend,
a FastAPI backend, and PostgreSQL for storage — the same stack you'd reach for
in a real deployment, not a toy demo. Clone it, run it locally in a few
minutes, and deploy your own copy when you're ready.

Every non-obvious decision along the way is written down, so if you want to
know *why* something is built the way it is, that's in [`docs/decisions`](docs/decisions/README.md) — this README is just about getting it running.

## What you get

```
browser ──▶ frontend (Next.js)  PUBLIC   cookie auth, proxies to:
                 │
                 ▼
            chatbot (FastAPI)   private  shared-header auth, rate limits
                 │
                 ▼
            PostgreSQL          private  sessions, messages, usage
```

One public URL (the frontend). The backend and database are never exposed
directly — the frontend forwards requests to the backend over a private
network, and the backend won't even start without its own internal secret.

## Before you start

You need:

- [Docker](https://docs.docker.com/get-docker/) and Docker Compose (comes
  bundled with Docker Desktop)
- An Anthropic API key — get one at [console.anthropic.com](https://console.anthropic.com)

That's it. Docker builds and runs everything else — Python, Node, and
Postgres included.

## Run it locally

1. Clone the repo and copy the example environment file:

   ```bash
   git clone <your-fork-url>
   cd Production-Multiturn-LLM-Chatbot
   cp .env.example .env
   ```

2. Open `.env` and paste in your Anthropic API key:

   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```

   Everything else in `.env.example` already has a working default for
   local use — you don't need to touch it yet.

3. Build and start everything:

   ```bash
   docker compose up -d --build
   ```

4. Open [http://localhost:3000](http://localhost:3000) and log in with the
   password `letmein` (that's the dev default — see below for changing it).

That's a working chatbot: a Next.js UI, talking to a FastAPI backend, backed
by a real Postgres database, all on your machine.

A few other things worth knowing while it's running:

- The API itself is at [http://localhost:8000](http://localhost:8000), with
  interactive docs at `/docs` and a health check at `/health`. You won't be
  able to call `/chat` on it directly without the internal key the frontend
  sends automatically.
- `docker compose logs -f chatbot` (or `frontend`) shows what each service
  is doing.
- `docker compose down` stops everything; add `-v` if you also want to wipe
  the database volume and start fresh.

## Running without Docker

If you'd rather run the Python side directly — say, while you're editing
code — you don't need Postgres or a container at all:

```bash
pip install -e .
export ANTHROPIC_API_KEY=sk-ant-...
python main_service.py      # a stdin chat loop, using a local SQLite file
```

Or run just the API server the same way:

```bash
uvicorn main_api:app --reload
```

With no `DATABASE_URL` set, the app quietly falls back to SQLite and skips
rate limiting — there's nothing extra to install or configure for local
development.

## Configuration

Everything the app needs comes from environment variables — nothing is
hardcoded into the Docker images, so the same build runs anywhere. The two
you must set are your API key and a shared internal secret; everything else
has a working default.

| Variable | Used by | Required? | What it does |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | backend | **yes** | Your Claude API key. |
| `INTERNAL_API_KEY` | both | **yes** | Shared secret between frontend and backend — must be identical on both. The backend refuses to start without it. |
| `APP_PASSWORD` | frontend | no (default: `letmein`) | The password visitors use to log into the chat UI. |
| `COOKIE_SECRET` | frontend | no | Signs the login cookie. Use a real random value outside local dev. |
| `DATABASE_URL` | backend | no | If set, uses Postgres. If unset, falls back to a local SQLite file. |
| `MODEL_NAME` | backend | no (default: `claude-haiku-4-5-20251001`) | Which Claude model to call. |
| `MAX_TOKENS` | backend | no (default: `712`) | Max reply length, in tokens. |
| `SYSTEM_PROMPT` | backend | no | The assistant's system prompt. |
| `RATE_LIMIT_PER_HOUR` | backend | no (default: `20`) | Requests allowed per visitor per hour. Only enforced when `DATABASE_URL` is set. |
| `DAILY_OUTPUT_TOKEN_BUDGET` | backend | no (default: `50000`) | A global daily cap on output tokens, so a single day can't run away with your bill. |

See [`.env.example`](.env.example) for all of these in one file, ready to copy.

## Deploying it for real

The version above is fine for trying things out, but it's running on your
laptop with dev-only secrets and no public URL. To put a real copy online:

1. Generate real random values for `INTERNAL_API_KEY`, `COOKIE_SECRET`, and
   `APP_PASSWORD` — don't reuse the local defaults.
2. Deploy the two Dockerfiles (`Dockerfile` for the backend,
   `frontend/Dockerfile` for the frontend) plus a Postgres database to
   whatever platform you like. We deployed to [Railway](https://railway.app),
   and [`docs/decisions/deploy-railway.md`](docs/decisions/deploy-railway.md)
   is the exact, step-by-step runbook we followed — including the mistakes
   that cost us time, so you don't have to repeat them.
3. Keep the backend off the public internet. Only the frontend needs a
   public domain; the backend should only be reachable from the frontend,
   over the platform's private network.

If you're deploying somewhere other than Railway, the runbook's reasoning
still applies even if the exact commands don't — the important parts are:
inject secrets as environment variables (never bake them into the image),
give the backend no public domain, and point the frontend at the backend's
private address.

## What's under the hood

```
src/chatbot/            the core logic — no HTTP, no framework
  client.py             talks to the Anthropic API
  storage.py            saves and loads conversations (SQLite or Postgres)
  service.py            ties a turn together: load, ask the model, save
  truncation.py         keeps long conversations affordable
  limits.py             rate limiting and a daily spending cap

main_api.py             the HTTP server (FastAPI)
main_service.py         a local command-line version, no server needed

frontend/               the Next.js chat UI and its login/proxy routes
```

If you want the reasoning behind any of this — why Postgres and not just a
file, why the backend requires a shared secret, why long conversations get
summarized instead of just cut off — it's all in
[`docs/decisions`](docs/decisions/README.md):

| | |
|---|---|
| [**Implementation**](docs/decisions/implementation.md) | How it's built, what runs where, what it doesn't do yet |
| [**Decision log**](docs/decisions/README.md) | Every non-obvious choice, why it was made, and what would change it |
| [**Failure chain**](docs/decisions/failure-chain.md) | 59 things that broke, in order, and what each one taught |
| [**Deploy runbook**](docs/decisions/deploy-railway.md) | The exact steps to deploy this, gotchas included |

## Known limitations

This is deployed and working, but it's honest about what it isn't yet:
everyone who logs in shares one identity (no per-person accounts), there's
no schema migration tooling, backups exist but have never been tested by
actually restoring one, there are no automated tests, replies aren't
streamed to the browser, and it runs as a single instance. See
[`docs/decisions/failure-chain.md`](docs/decisions/failure-chain.md#still-open)
for the details behind each of these.
