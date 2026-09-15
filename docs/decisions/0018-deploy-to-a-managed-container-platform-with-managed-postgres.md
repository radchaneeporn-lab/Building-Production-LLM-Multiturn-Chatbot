# 0018: Deploy to a managed container platform, with managed Postgres

**Date:** 2026-09-14
**Status:** Accepted

**Context:**
0015 packaged the process into an image; 0017 turned the store into a
network service in its own container. Both records end with the same
unfired trigger — 0015's "orchestration beyond one host" and 0017's "one
Postgres container becomes the single point of failure I actually care
about." Compose proved the containers run together; it says nothing about
running them anywhere but this laptop.

The constraint forcing the choice now is not scale and not uptime. It's
that three things a deployment needs have no Compose answer at all:

- a URL that exists when my machine is off,
- a database that isn't a named volume on one desktop's disk (0007's and
  0017's backup gap, still unpaid),
- somewhere to put `ANTHROPIC_API_KEY` that isn't a plaintext `.env` read
  via `env_file:` (0015's "secrets at rest" gap, verbatim).

**Options:**
1. Railway — both existing Dockerfiles as services, plus its managed
   Postgres, with `DATABASE_URL` injected into the app service. (Render is
   near-identical; the reasoning below applies to either.)
2. Vercel (frontend) + Render/Railway (backend) + Neon (Postgres) — each
   piece on the platform built for it.
3. Fly.io for both containers, with Postgres on Fly.
4. AWS ECS Fargate + RDS behind an ALB.
5. One VM (Hetzner/DO), running `docker compose up -d` exactly as today.

**Chose:** (1). It deploys the artifacts I already have and already tested
— both Dockerfiles, unchanged in substance — and it's the first step where
0017's deferred option (4) finally pays off: following the `DATABASE_URL`
convention means attaching a managed database is a variable the platform
sets, not a class I write. Likewise `/health` (`main_api.py:188`) was
written for a platform poller before any platform existed; nothing new is
needed to satisfy the healthcheck. Secrets become platform-injected
environment values, closing 0015's last named gap. One vendor, one bill,
one log stream, and the frontend/backend/database split I debugged locally
maps onto three services without redrawing it.

**Rejected:**
(2) is the better-engineered split and the wrong trade here: Vercel doesn't
build `frontend/Dockerfile`, so the artifact I tested stops being the
artifact I ship — precisely the property 0015 existed to buy. Three
vendors for a project with no tests and no migrations is more operational
surface than the deployment itself. (3) is the most Docker-native option
and would work, but Postgres on Fly is an app I operate. That ships 0017's
unanswered backup question into production while feeling managed, which is
worse than shipping it knowingly. (4) is the career-relevant option and the
only one that teaches VPCs, ALBs, task definitions and IAM — and the only
one where I write substantial infrastructure before the first request
succeeds. Same shape of mistake 0017 rejected as its own option (4): the
right destination, the wrong step. Stays on the list for when the reason is
"I need a VPC," not "I need a URL." (5) is the cheapest and truest to what
I tested, and buys none of the three things in Context — it's 0015's
one-host limitation renamed, with the same plaintext `.env` and the same
absent backups.

**Reverses when:**
- **The platform's config becomes the thing I can't reproduce.** The
  container is portable; a dashboard full of service settings is not. The
  day I need a second environment (staging) identical to the first, this
  wants to be infrastructure-as-code — the real lock-in here, not the
  runtime.
- **The first schema change lands against a database holding real rows.**
  `CREATE TABLE IF NOT EXISTS` covers an empty database and nothing else
  (0017). Deploying is what turns this from a dev annoyance into an
  incident, and 0017 already predicted this trigger arrives before the HA
  one. It now arrives before this record's other triggers too.
- **Replica count goes above one.** It's a slider on this platform, and
  0017's logical race — two `send()`s on one session both loading the same
  history — is still open. Deploy at one replica deliberately, not by
  default.
- **Cost stops being noise.** `/chat` is an unauthenticated, unmetered path
  to a paid model, now reachable from the internet. The first surprising
  invoice is a security finding, not a billing one.
- **Connection count outgrows direct pooling** — unchanged from 0017;
  managed Postgres moves the `max_connections` ceiling, it doesn't remove
  it.

**What I know:**
- The two conventions I followed for their own sake both paid off on this
  step with no code changes: `DATABASE_URL` (0017) and `/health` (0015).
  Following a convention I had no immediate use for is the cheapest thing
  in this log.
- `PORT` is injected by the platform, not chosen by me. A hardcoded
  `--port 8000` in `CMD` is a deploy bug, not a preference — the container
  has to bind what it's told.
- Managed Postgres means someone else runs the backups. It doesn't mean I
  know what they guarantee, which is a different sentence.
- The image is the portable unit; everything around it (service graph,
  secrets, domains, scaling) is platform state that doesn't live in this
  repo.

**What I don't know yet:**
- **RPO and RTO, still.** 0007 asked, 0017 didn't answer, and buying
  managed Postgres hasn't answered it either — it's only moved the question
  from "who runs `pg_dump`" to "what does this platform's backup tier
  actually promise, how do I restore from it, and have I ever tried." A
  backup nobody has restored is a belief.
- **Graceful shutdown as a real contract.** `lifespan`'s `store.close()`
  (0013, `main_api.py:120`) runs on SIGTERM. I don't know whether this
  platform sends SIGTERM, how long it waits before SIGKILL, or whether an
  in-flight `/chat` — which can hold a connection for a whole generation
  (0003) — survives a deploy.
- **Migrations against live data.** Named in 0017, unchanged, now urgent.
  Expand/contract, and running a migration while old code still serves
  traffic.
- **Which of the several timeouts is now the platform's.** 0003 listed
  four independent clocks on one request and admitted I couldn't name the
  numbers. A deployed edge proxy adds its own, and it's the one most likely
  to kill a long generation, and to buffer the SSE response I eventually
  want.
- **What a private network actually is here.** Service-to-service traffic
  not crossing the public internet is the security claim 0019 depends on,
  and I'm taking it on the platform's word. Some platforms' private
  networking is IPv6-only, which makes `--host 0.0.0.0` silently
  unreachable — worth verifying, not assuming.
- **The base image is still pinned by tag**, not digest (0015's gap), and
  it's now pinned-by-tag in production.

**Pillar pressure:** Reliability and operational excellence bought — a URL
that outlives my laptop, a database with someone else's backups, and
secrets injected rather than filed on a host. Charged to cost, which until
now was zero: there's a standing monthly bill, and an open `/chat` in front
of a metered API with no rate limit (backlog §5) and no unit-cost
instrumentation (backlog §6) — the two pillars whose failures the README
calls silent, now both live at once. Also charged, quietly, back to
operational excellence: the one part of this system no longer reproducible
from the repository is the part that decides how it runs.

---

**Postscript — 2026-09-14, after actually deploying.** The decision stands
unchanged; this records what stopped being hypothetical. Steps are in
[`docs/deploy-railway.md`](deploy-railway.md).

*Live at `frontend-production-e086.up.railway.app`; `chatbot` and Postgres
have no public domain.*

Four things moved from "don't know" to "know":

- **Private networking is IPv6-only here.** Written above as "worth
  verifying, not assuming" — it was real. `HOST=::` is why the backend logs
  `Uvicorn running on http://[::]:8000`; bound to `0.0.0.0` it starts,
  looks healthy, and is unreachable from the frontend with no error on
  either side.
- **`PORT` injection is real and differs per service.** Railway gave the
  backend 8000 (pinned) and the frontend 8080. Both honoured it without
  code changes. A hardcoded `--port 8000` would have failed every
  healthcheck.
- **Identity and repository access are two separate GitHub grants.**
  Logging into Railway with GitHub doesn't let it read a private repo; the
  GitHub App has to be installed on the repo, a different screen from the
  OAuth App authorization. `Repository not found or is not accessible` is
  what that looks like three steps later.
- **The managed engine is `postgres-ssl:18`**, against `postgres:16-alpine`
  in Compose. Environment parity (0015's whole claim) doesn't extend to a
  managed database's version — the container I control is identical, the
  service I rent isn't.

Two new entries for "What I don't know yet":

- **What a "read-only-looking" command actually does.** Two commands
  surprised me by writing: `railway variables <service>` printed a live
  API key in full, forcing a rotation, and `railway domain --service
  chatbot` created a domain, publishing the backend for about thirty
  seconds before I deleted it, briefly falsifying 0019 in production. The
  general lesson isn't about this CLI: I don't have a habit of checking
  whether a verification step can mutate, and the blast radius of "just
  checking" was a leaked credential and an exposed endpoint.
- **RPO/RTO is still unanswered** (asked in 0007, deferred in 0017,
  deferred above). Railway offers Postgres point-in-time recovery as a
  feature I haven't enabled, read about, or tested a restore from.

One addition to "Reverses when" — **identity federation.** Creating the
replacement API key surfaced that Anthropic supports OIDC federation for
GCP, AWS, Azure and GitHub Actions: the platform proves who it is and
receives a token that expires in minutes, so there's no long-lived secret
to store, leak, or rotate. Railway isn't a supported provider, so this
deployment can't use it. That's a concrete capability AWS buys that this
platform can't, and given that a leaked static key is exactly what went
wrong today, it's a stronger argument for the ECS option than anything in
the Rejected section above.
