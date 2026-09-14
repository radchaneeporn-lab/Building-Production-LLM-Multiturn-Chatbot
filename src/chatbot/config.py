from __future__ import annotations

import os

from .models import InferenceConfig
from .storage import ConversationStore, PostgresStore, SQLiteStore

# ---------------------------------------------------------------------------
# LEARNING NOTE — closing the same twelve-factor gap 0015 already closed for
# DB_PATH / FRONTEND_ORIGIN / ANTHROPIC_API_KEY, now for the three inference
# knobs (model, max_tokens, system prompt).
#
# Before this file existed, every composition root (main_api.py,
# main_service.py, main_multiturn.py, main_plain.py) built its own
# InferenceConfig with the SAME THREE LITERALS copy-pasted by hand:
#
#     InferenceConfig(
#         model="claude-haiku-4-5-20251001",
#         max_tokens=1024,
#         system="You are a helpful assistant. Be concise.",
#     )
#
# Two problems that caused, discovered the hard way:
#   1. Changing a value meant editing (at least) four files and hoping you
#      caught all of them — nothing enforced they stayed in sync.
#   2. InferenceConfig's own field defaults in models.py (max_tokens=16_000)
#      looked like "the" default but were never actually used by any real
#      entry point — every one of them overrode it explicitly. Editing that
#      dataclass default and expecting the running app to change is the
#      trap this file exists to remove.
#
# load_inference_config() is now the ONE place these three values are
# decided. Every entry point calls it instead of re-typing literals, and
# each value can be overridden per-deployment via the environment —
# docker-compose.yml's `environment:` block, or a local .env — with NO
# code change and NO image rebuild. Only a container/process restart is
# needed to pick up a new env value (`docker compose up -d`, no `--build`).
#
# [LEARNING] Why not put this ON InferenceConfig itself (in models.py)?
# ADR 0001 pins an explicit invariant: "models.py has zero outgoing
# imports." Reading os.environ there would break that guarantee for the
# one file this codebase deliberately keeps pure/provider-agnostic. This
# module is allowed to import both `os` and `.models` — it's the seam
# between "the environment" and "the domain type," same job client.py does
# for "the Anthropic SDK" and "the domain type."
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_MAX_TOKENS = 712
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant. Be concise."


def load_inference_config() -> InferenceConfig:
    """Build the InferenceConfig every entry point should use.

    Reads MODEL_NAME / MAX_TOKENS / SYSTEM_PROMPT from the environment,
    falling back to this project's long-standing defaults when unset —
    exactly the same "env var with a fallback" shape as
    `os.environ.get("DB_PATH", "conversations.db")` elsewhere in this repo.
    """
    return InferenceConfig(
        model=os.environ.get("MODEL_NAME", DEFAULT_MODEL),
        max_tokens=int(os.environ.get("MAX_TOKENS", DEFAULT_MAX_TOKENS)),
        system=os.environ.get("SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
    )


def load_store() -> ConversationStore:
    """Pick the store implementation from the environment.

    DATABASE_URL set  -> PostgresStore (the containerised/deployed path)
    DATABASE_URL unset -> SQLiteStore at DB_PATH (a bare `python
                          main_service.py` on a laptop, no server required)

    [LEARNING] Why this function exists at all, rather than each entry
    point calling SQLiteStore(...) itself the way they used to: that is the
    exact duplication 0016 removed for inference config, and store
    construction had the same shape — the same `os.environ.get("DB_PATH",
    ...)` line copy-pasted into main_api.py and main_service.py. Adding a
    second backend would have made it three lines in two files.

    [LEARNING] DATABASE_URL (one string carrying driver, credentials, host,
    port, database) is the near-universal convention — Heroku, Railway,
    Django, Rails, SQLAlchemy all read this variable. Following it means a
    deploy platform that injects DATABASE_URL automatically just works, and
    it keeps a PASSWORD out of this source file: the value arrives from the
    environment like ANTHROPIC_API_KEY does, not from a literal here.

    [LEARNING] The fallback is deliberate, not laziness. Requiring Postgres
    for every entry point would mean you cannot run main_plain.py or
    main_service.py without starting a database server first — the exact
    setup friction 0015 was trying to remove. The Protocol seam (0006) is
    what makes "two backends, chosen at startup" cost one function instead
    of a rewrite.
    """
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return PostgresStore(database_url)
    return SQLiteStore(os.environ.get("DB_PATH", "conversations.db"))
