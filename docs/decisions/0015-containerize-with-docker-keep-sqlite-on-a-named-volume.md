# 0015: Containerize with Docker; keep SQLite on a named volume

**Date:** 2026-09-12
**Status:** Accepted

**Context:**
Every entry point so far assumes a developer's machine: a `.venv`, a `.env`
file read by `dotenv`, "run from project root" in the docstrings. Getting this
onto any other machine — a teammate's laptop, a deploy target — currently
means reproducing that setup by hand. This is the twelve-factor configuration
gap 0013 already named as unlearned. Containerizing forces the actual
decision: how the process gets packaged, and where its one stateful file
(`conversations.db`) lives once the process is boxed up.

**Options:**
1. Dockerfile + a named Docker volume mounted at the SQLite file's path.
2. Dockerfile + bake the `.db` file into the image, or bind-mount a specific
   host directory into the container.
3. Skip containers; deploy the process directly on a VM/host as today.
4. Containerize and migrate to Postgres in the same step.

**Chose:** (1). Docker packages the process itself — same artifact on my
machine and anywhere else, config supplied by the environment
(`ANTHROPIC_API_KEY`, `DB_PATH`) instead of baked into the image or read from
a file that doesn't exist in a container. `DB_PATH` is now an environment
variable in both `main_api.py` and `main_service.py` (previously a hardcoded
`"conversations.db"` in each) for exactly this reason: the container's
writable layer is discarded on every rebuild and restart, so the store's
location has to be a runtime choice, not a code constant. A *named* volume
(`chatbot-data:/app/data`), not a bind mount, keeps that location addressable
the same way regardless of the host's directory layout — including a Windows
dev machine, where a bind-mounted path needs translation Compose/Docker
Desktop don't always agree on.

**Rejected:**
(2)'s bind-mount variant ties the image to one host's filesystem layout,
which is the exact coupling containerizing is supposed to remove; baking the
`.db` file in is worse — it means "reset the database" and "rebuild the
image" become the same action. (3) reintroduces the works-on-my-machine drift
environment parity exists to kill, for no benefit. (4) bundles two decisions
that don't need to move together — 0007 already scoped the Postgres
migration as its own, separately-triggered record; conflating them here would
bury this decision's actual scope (packaging) inside that one.

**Reverses when:** This is 0007's own `Reverses when:` clause, now literally
true rather than hypothetical:
- More than one replica or worker process runs this container — SQLite's
  single-writer-file model breaks down exactly as 0014 describes, and
  containerizing is what makes `--scale`-ing replicas trivial, so this
  trigger is now one flag away instead of theoretical.
- The volume needs to be visible from more than one Docker host — a named
  volume lives on the one host that created it; that's the same limitation
  local disk always had, just renamed.
- Managed backups or point-in-time recovery become a requirement — a Docker
  volume has neither by default.

None of these have happened yet — this record does not supersede 0007, it's
the record that will make 0007's own trigger fire once one of the above is
true.

**What I know:**
- A container's writable layer is thrown away on every restart/rebuild; only
  volumes and bind mounts survive it. This is what "ephemeral vs. persistent
  storage" — named as a gap in 0007 — concretely means, now that I've watched
  it happen to a test container.
- Config lives in the environment, not the image: `DB_PATH` and
  `ANTHROPIC_API_KEY` are supplied at `docker run`/`docker compose` time, not
  read from a file inside it. The twelve-factor gap 0013 flagged is closed
  for these two values specifically.
- A named volume outlives `docker compose down` but not `docker compose
  down -v` or an explicit `docker volume rm` — "durable" here means relative
  to the container's own lifecycle, not durable in the backup/DR sense.

**What I don't know yet → fundamentals to learn:**
- **Where a named volume actually lives**, and what backing it with anything
  other than the local Docker host's disk would take. This is 0007's
  block/file/object-storage distinction, now with a concrete thing to point
  at instead of a category.
- **Multi-stage builds.** This image installs `pip`/`setuptools` build
  tooling into the same layer it runs from. A builder stage that discards
  those from the final image is the standard next step once image size or
  attack surface starts to matter.
- **Base image pinning and scanning.** `python:3.11-slim` is pinned by tag,
  not digest — the base can change under me on a rebuild I didn't expect to
  change anything. Learning goal: digest pinning, and tools like
  `docker scout`/`trivy` as the container-specific half of dependency
  hygiene 0002 raised for the SDK.
- **Orchestration beyond one host.** Compose proves the container runs; it
  says nothing about restart policy under real failure, rolling deploys, or
  what happens the moment the "more than one replica" trigger above fires —
  that's squarely 0013/0014's territory once it's live instead of hypothetical.
- **Secrets at rest.** `.env` is read via Compose's `env_file:`, which still
  means the API key sits in a plaintext file on the host. Learning goal: what
  a real secrets manager (or at minimum a platform's native secret
  injection) buys over this.

**Pillar pressure:** Operational excellence (one build artifact, identical
config surface in dev and wherever this deploys) bought against reliability
debt this step doesn't pay down — the single-writer-file constraint (0014)
and the no-backup gap (0007) both still stand exactly as before, and
containerizing is precisely what makes it easy to trip the first one by
scaling replicas without noticing.
