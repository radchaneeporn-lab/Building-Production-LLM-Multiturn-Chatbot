# 0016: Load inference parameters from the environment, through one loader

**Date:** 2026-09-14
**Status:** Accepted

**Context:**
I changed `max_tokens` on `InferenceConfig` in `models.py` and the running app
ignored it. Twice. The reason turned out to be structural, not a caching
mistake: all four entry points (`main_api.py`, `main_service.py`,
`main_multiturn.py`, `main_plain.py`) each constructed their own
`InferenceConfig` with the *same three literals* copy-pasted by hand, so the
dataclass field defaults were never reached by any real run. On top of that,
the containerised path (0015) makes a Python source edit require an image
rebuild — so "turn one dial" cost a `--build` and a wait, which is what made me
keep editing the wrong file to avoid it.

This is the same twelve-factor gap 0013 named and 0015 closed for `DB_PATH`,
`FRONTEND_ORIGIN`, and `ANTHROPIC_API_KEY` — just never extended to the three
inference knobs (`model`, `max_tokens`, `system`). The constraint isn't "I want
this tidier"; it's that a value I tune during normal work lives in four files
and takes an image rebuild to change.

**Options:**
1. One env-backed loader (`src/chatbot/config.py::load_inference_config()`)
   that every composition root calls instead of writing literals.
2. Put the env reading on `InferenceConfig` itself in `models.py`, as a
   `from_env()` classmethod.
3. Leave the four literal blocks; just make them agree and add a comment
   warning that the dataclass defaults are decorative.
4. A mounted config file (YAML/TOML) read at startup, instead of env vars.

**Chose:** (1). One function decides these three values for every entry point,
reading `MODEL_NAME` / `MAX_TOKENS` / `SYSTEM_PROMPT` with in-code fallbacks.
`docker-compose.yml` supplies them as `${VAR:-default}`, which keeps a
reproducible default in a tracked file *and* allows `MAX_TOKENS=50 docker
compose up -d` for a one-off experiment with no file edit and nothing to
revert. Changing a value is now a container restart, not a rebuild, because env
values are injected at start time rather than baked into the image.

**Rejected:**
(2) is the tempting one and it's wrong for a specific reason: 0001 pins
`models.py` at *zero outgoing imports*, and that invariant is load-bearing for
0002 and 0006. Importing `os` there to read the environment trades a verifiable
property for one saved file. The seam belongs beside the domain type, not
inside it — same shape as `client.py` holding the SDK.
(3) fixes the symptom and none of the cause: four copies still drift, and a
value change still needs `--build`, which is the friction that produced the bug
in the first place.
(4) is more machinery than three scalars justify, and it would sit *next to*
env vars rather than replace them (`ANTHROPIC_API_KEY` can't move into a
tracked file), leaving two config systems and a precedence question between
them. Env vars were already this project's established answer.

**Reverses when:**
- Config stops being a handful of flat scalars — nested or per-tenant settings
  don't map onto environment variables without inventing a encoding.
- A value has to change *without a restart* (live-reloaded flags, an
  admin-tunable setting). Process-start env reading can't do that.
- Config becomes per-request or per-user — "let the caller pick the model"
  moves these out of process-level config entirely and into the request/session
  model, which is a different decision, not a bigger version of this one.
- More secrets join `ANTHROPIC_API_KEY`. A gitignored `.env` plus a tracked
  compose file is adequate for one key on one dev machine and stops being
  adequate quickly after that (backlog item 5).

**What I know:**
- The precedence chain that actually decides the value, verified by running it
  rather than reasoning about it: shell variable > compose `environment:` >
  `env_file:`/`.env` > in-code default. A *hardcoded* `- MAX_TOKENS=712` in
  compose beats the shell; only `${MAX_TOKENS:-712}` lets the shell win. That
  distinction is invisible until you test both.
- An image is a frozen snapshot: a source edit needs `up --build`, an env value
  needs only `up -d`. Which file I edit determines which command I owe.
- `.env` is not a safe home for prose. A `#` truncates the value and `$WORD`
  expands to empty, both silently — I watched a test prompt lose half its text.
  So `SYSTEM_PROMPT` stays in the compose file, not `.env`.
- Why the loader can't live in `models.py`, in terms of a property I can check
  (`grep` for imports) rather than a style preference.
- In-code defaults are only reached when no env var exists at all — i.e. the
  non-Docker entry points. A default left at an experiment's value (50) would
  have shipped a chatbot that truncates every answer, and nothing would have
  flagged it.

**What I don't know yet → fundamentals to learn:**
- **Config validation and failing fast.** `int(os.environ.get("MAX_TOKENS"))`
  raises `ValueError` from inside `lifespan`, at startup, with a traceback that
  doesn't say which variable was wrong. What's the discipline for validating
  the whole config at boot and refusing to start with a readable message?
  (Keywords: settings objects, `pydantic-settings`, schema-validated config,
  fail-fast vs. degrade.)
- **Where config comes from when there's no compose file.** Railway, Kubernetes,
  and a bare `docker run` each have their own answer, and I've only learned
  Compose's. What's the portable mental model — and what is a ConfigMap
  actually doing that `environment:` isn't?
- **Whether the system prompt is config at all.** It's currently an env var,
  which means prompt changes leave no diff and get no review. An argument I
  can't yet settle: prompt text is application *behaviour*, and behaviour
  belongs in version control. Is the right home a tracked file the app reads,
  with env override only for experiments?
- **Typed config as a contract.** Right now nothing stops `MAX_TOKENS=0`,
  `MAX_TOKENS=9999999`, or a `MODEL_NAME` that doesn't exist — the first two
  produce bad output, the third produces a per-request API error at runtime
  rather than a startup failure. Where does range/enum validation belong?

**Pillar pressure:** Operational excellence bought — one place to change, no
rebuild to change it, and a default that survives a fresh clone. Charged mostly
to **cost optimisation and security**, and quietly: `MAX_TOKENS` is now a dial
that anyone who can set an environment variable can turn, with no ceiling and
no validation, and it multiplies directly into the bill (backlog item 6 is
still "I can't answer what a conversation cost"). `SYSTEM_PROMPT` being
env-settable means the model's instructions are now part of the deployment
surface rather than the reviewed codebase — fine while the deploy environment
and I are the same person, and exactly the kind of thing that stops being fine
without announcing itself.
