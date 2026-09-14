from __future__ import annotations

import os
from typing import Protocol

# ---------------------------------------------------------------------------
# LEARNING NOTE — closing backlog §5's "Done when: /chat is no longer an open,
# unmetered proxy to a paid model." See ADR 0020.
#
# Two DIFFERENT limits live here, and conflating them is the classic mistake:
#
#   1. REQUESTS per identity per hour  — stops one caller hammering the API.
#      Bounds abuse. Does NOT bound cost: 20 short messages and 20 messages
#      that each generate 712 tokens cost very different amounts.
#
#   2. OUTPUT TOKENS per day, globally — bounds the bill. This is the only
#      control here that maps onto money, because tokens are the unit
#      Anthropic charges for. A request limit is a proxy for cost; a token
#      budget IS cost.
#
# Rate limiting is usually taught as (1) alone. For an app whose marginal cost
# is a model call, (1) alone lets twenty well-behaved users spend a fortune
# while staying under every limit.
# ---------------------------------------------------------------------------


class RateLimitExceeded(Exception):
    """Raised when a call must be refused. Carries the HTTP shape with it.

    [LEARNING] Two different refusals, deliberately different status codes:

      429 Too Many Requests — YOU are going too fast. Retry later and it
          will work. A per-identity problem.
      503 Service Unavailable — the SERVICE is out of budget. Retrying
          sooner changes nothing; nobody gets served until tomorrow. A
          global problem that is not the caller's fault.

    Returning 429 for both would tell a user "slow down" when the true
    answer is "come back tomorrow" — a status code is a machine-readable
    claim about what happens if the client retries, so getting it wrong
    makes well-behaved clients misbehave.
    """

    def __init__(self, detail: str, status_code: int = 429, retry_after: int | None = None):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.retry_after = retry_after


class RateLimiter(Protocol):
    """The seam, defined the same way ConversationStore was in ADR 0006.

    [LEARNING] A Protocol again, for the same reason: `main_service.py` and
    `main_plain.py` run on a laptop with no database and must not need a
    rate limiter to exist. NullRateLimiter satisfies this and does nothing,
    so the CLI paths keep working untouched — the seam is what lets one
    concern be present in one deployment and absent in another without an
    `if` in the calling code.
    """

    def check(self, key: str) -> None:
        """Raise RateLimitExceeded if this call must not proceed."""
        ...

    def record(self, input_tokens: int, output_tokens: int) -> None:
        """Record what a completed call actually cost."""
        ...

    def close(self) -> None: ...


class NullRateLimiter:
    """No limits. The laptop/CLI default, and the InMemoryStore of this seam."""

    def check(self, key: str) -> None:
        return None

    def record(self, input_tokens: int, output_tokens: int) -> None:
        return None

    def close(self) -> None:
        return None


class PostgresRateLimiter:
    """Counters in Postgres, so limits survive redeploys and extra replicas.

    [LEARNING] Why not a dict in the process? Two reasons, both of which
    ADR 0017 already argued once for `turn_index`:

      - A redeploy resets it. This app redeploys on every push to main, so
        an in-memory limit is a limit anyone can clear by waiting for you
        to ship something.
      - It protects exactly one replica. Solving a shared-state problem
        with a local primitive is the trap 0017 named; it would be strange
        to reject an in-process lock for the store and then accept an
        in-process counter for the thing guarding the money.
    """

    def __init__(
        self,
        conninfo: str,
        requests_per_hour: int = 20,
        daily_output_token_budget: int = 50_000,
    ) -> None:
        try:
            from psycopg_pool import ConnectionPool
        except ModuleNotFoundError as exc:  # pragma: no cover - setup error
            raise RuntimeError(
                "PostgresRateLimiter needs the Postgres driver:\n"
                "    pip install 'psycopg[binary,pool]'"
            ) from exc

        self.requests_per_hour = requests_per_hour
        self.daily_output_token_budget = daily_output_token_budget

        # [LEARNING] Its own SMALL pool rather than sharing PostgresStore's.
        # Honest tradeoff: it keeps this class independent of which store is
        # in use (it works with SQLiteStore too), at the cost of more open
        # connections — and 0017 flagged total connection count as a real
        # capacity limit. max_size=3 because every request touches this at
        # most twice and the queries are single-row upserts.
        self._pool = ConnectionPool(conninfo, min_size=1, max_size=3, open=True)
        self._pool.wait(timeout=30)
        self._create_schema()

    def _create_schema(self) -> None:
        with self._pool.connection() as conn:
            # [LEARNING] The window is part of the PRIMARY KEY, not a column
            # to be reset. Nothing ever deletes or zeroes a counter: a new
            # hour is simply a new row. That removes the "who resets the
            # counter, and what if two processes reset it at once" problem
            # entirely — the same append-only reasoning as ADR 0008.
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS rate_limit_counters (
                    key          TEXT        NOT NULL,
                    window_start TIMESTAMPTZ NOT NULL,
                    count        INTEGER     NOT NULL DEFAULT 0,
                    PRIMARY KEY (key, window_start)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS usage_daily (
                    day           DATE   PRIMARY KEY,
                    input_tokens  BIGINT NOT NULL DEFAULT 0,
                    output_tokens BIGINT NOT NULL DEFAULT 0,
                    requests      BIGINT NOT NULL DEFAULT 0
                )
                """
            )

    def check(self, key: str) -> None:
        with self._pool.connection() as conn:
            # [LEARNING] THE important line in this file. One statement that
            # inserts-or-increments and hands back the new value:
            #
            #   INSERT ... ON CONFLICT ... DO UPDATE SET count = count + 1
            #   RETURNING count
            #
            # Compare what ADR 0017 had to fix in append(): SELECT COUNT(*),
            # then INSERT — two statements, so two callers could both read N
            # and both write N+1. Here the read and the write are the SAME
            # statement, so the database serialises them on the row and the
            # count cannot be lost. No FOR UPDATE needed, because there is no
            # gap between reading and writing to race in.
            row = conn.execute(
                """
                INSERT INTO rate_limit_counters (key, window_start, count)
                VALUES (%s, date_trunc('hour', now()), 1)
                ON CONFLICT (key, window_start)
                DO UPDATE SET count = rate_limit_counters.count + 1
                RETURNING count
                """,
                (key,),
            ).fetchone()
            count = row[0]

            if count > self.requests_per_hour:
                # [LEARNING] Counted BEFORE deciding, and the increment stands
                # even on refusal. That means hammering a 429 keeps the number
                # climbing rather than letting a caller probe the boundary for
                # free — refusals are cheap for us and should not be free for
                # them.
                raise RateLimitExceeded(
                    f"Rate limit: {self.requests_per_hour} messages per hour. "
                    "Try again in a little while.",
                    status_code=429,
                    retry_after=self._seconds_to_next_hour(conn),
                )

            spent = conn.execute(
                "SELECT output_tokens FROM usage_daily WHERE day = CURRENT_DATE"
            ).fetchone()
            if spent and spent[0] >= self.daily_output_token_budget:
                raise RateLimitExceeded(
                    "This service has reached its daily usage budget. "
                    "It will reset tomorrow.",
                    status_code=503,
                )

    def record(self, input_tokens: int, output_tokens: int) -> None:
        # [LEARNING] Called AFTER a successful call, because until the model
        # answers nobody knows what it cost — output tokens are not knowable
        # in advance. That is why the budget check above is "has the budget
        # ALREADY been exceeded" and not "would this call exceed it": the
        # cap can overshoot by up to one call per concurrent request.
        #
        # That is a deliberate accepted inaccuracy, not an oversight. Making
        # it exact would need a reservation before the call and a settlement
        # after it (the pattern hotels use for a card pre-authorisation),
        # which is a lot of machinery to avoid overshooting a soft budget by
        # a few hundred tokens.
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO usage_daily (day, input_tokens, output_tokens, requests)
                VALUES (CURRENT_DATE, %s, %s, 1)
                ON CONFLICT (day) DO UPDATE SET
                    input_tokens  = usage_daily.input_tokens  + EXCLUDED.input_tokens,
                    output_tokens = usage_daily.output_tokens + EXCLUDED.output_tokens,
                    requests      = usage_daily.requests      + 1
                """,
                (input_tokens, output_tokens),
            )

    @staticmethod
    def _seconds_to_next_hour(conn) -> int:
        row = conn.execute(
            "SELECT EXTRACT(EPOCH FROM (date_trunc('hour', now()) "
            "+ INTERVAL '1 hour' - now()))::int"
        ).fetchone()
        return int(row[0]) if row else 3600

    def close(self) -> None:
        self._pool.close()


def load_rate_limiter() -> RateLimiter:
    """Pick a limiter from the environment, same shape as load_store().

    DATABASE_URL set   -> PostgresRateLimiter (the deployed path)
    DATABASE_URL unset -> NullRateLimiter (a laptop; nothing to protect)
    """
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return NullRateLimiter()
    return PostgresRateLimiter(
        database_url,
        requests_per_hour=int(os.environ.get("RATE_LIMIT_PER_HOUR", 20)),
        daily_output_token_budget=int(os.environ.get("DAILY_OUTPUT_TOKEN_BUDGET", 50_000)),
    )
