# Production-Agentic-Multiturn-Chatbot

A multi-turn chatbot built up in deliberate steps — from a single API call to a
deployed, password-gated, rate-limited service — where **the reasoning is the
artifact**. Every non-obvious choice has a decision record; every failure that
forced a choice is written down.

Live: a Next.js chat UI in front of a FastAPI service and PostgreSQL, deployed
on Railway, with the backend and database on a private network.

## Documentation

| | |
|---|---|
| [**Implementation**](docs/decisions/implementation.md) | How it's built, what runs where, what it does *not* do |
| [**Decision log**](docs/decisions/README.md) | ADRs 0001–0020 — why each choice, and what would reverse it |
| [**Failure chain**](docs/decisions/failure-chain.md) | 59 things that broke, in causal order, and the concept each taught |
| [**Deploy runbook**](docs/decisions/deploy-railway.md) | Reproducing the deployment, with the gotchas that actually bit |

New here? Read the implementation doc, then the failure chain.

## Run it

### Everything, in containers

```bash
docker compose up -d --build
```

- UI: http://localhost:3000 — password `letmein` (a dev default; see below)
- API: http://localhost:8000 — `/health`, `/docs` (Swagger), `POST /chat`
- Postgres: private to the Compose network, on the `chatbot-pgdata` volume

Requires `.env` in the project root with `ANTHROPIC_API_KEY=...`.

The other values (`APP_PASSWORD`, `COOKIE_SECRET`, `INTERNAL_API_KEY`) have
**dev-only defaults in `docker-compose.yml`**, which is safe only because
nothing there is published beyond localhost. A real deployment supplies real
random values and has no fallback — `main_api.py` refuses to start without
`INTERNAL_API_KEY`.

### Just the API, no containers

```bash
python main_service.py      # stdin loop, SQLite, no server needed
uvicorn main_api:app --reload
```

With `DATABASE_URL` unset the app uses SQLite and a no-op rate limiter, so a
laptop needs no database server. That's the `Protocol` seam in
[ADR 0006](docs/decisions/0006-define-the-store-seam-as-a-protocol.md) doing its
job.

## Shape

```
browser ──▶ frontend (Next.js)  PUBLIC   cookie auth, proxies to:
                 │
                 ▼
            chatbot (FastAPI)   private  shared-header auth, rate limits
                 │
                 ▼
            PostgreSQL          private  sessions, messages, usage
```

One public surface; two independent credentials; every environment-specific
value read at runtime rather than baked into an image.

## Status

Deployed and working. Known gaps, kept deliberately visible rather than tidied
away — no per-person identity, no schema migrations, no tested backups, no
tests, no streaming, single replica. Each is tracked in the
[decision log's learning backlog](docs/decisions/README.md#learning-backlog)
with the record that raised it.
