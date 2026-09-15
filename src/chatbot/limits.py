from __future__ import annotations

import os
from typing import Protocol


class RateLimitExceeded(Exception):
    """Raised when a call must be refused.

    429 means the caller is going too fast and a retry will work. 503
    means the service is out of budget and retrying sooner won't help —
    different status codes because a retrying client needs to know which
    one it's dealing with.
    """

    def __init__(self, detail: str, status_code: int = 429, retry_after: int | None = None):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.retry_after = retry_after


class RateLimiter(Protocol):
    """Same seam pattern as ConversationStore. NullRateLimiter lets the
    CLI entry points run with no database and no limits."""

    def check(self, key: str) -> None:
        """Raise RateLimitExceeded if this call must not proceed."""
        ...

    def record(self, input_tokens: int, output_tokens: int) -> None:
        """Record what a completed call actually cost."""
        ...

    def close(self) -> None: ...


class NullRateLimiter:
    """No limits — the local/CLI default."""

    def check(self, key: str) -> None:
        return None

    def record(self, input_tokens: int, output_tokens: int) -> None:
        return None

    def close(self) -> None:
        return None


class PostgresRateLimiter:
    """Counters in Postgres, not memory, so limits survive redeploys and
    hold across replicas. Enforces two separate limits: requests per
    identity per hour (bounds abuse) and output tokens per day, globally
    (bounds the bill — tokens are the billed unit, requests aren't)."""

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

        # Its own small pool, independent of whichever store is in use.
        self._pool = ConnectionPool(conninfo, min_size=1, max_size=3, open=True)
        self._pool.wait(timeout=30)
        self._create_schema()

    def _create_schema(self) -> None:
        with self._pool.connection() as conn:
            # The window is part of the primary key — a new hour is a new
            # row, so nothing ever resets or zeroes a counter.
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
            # Insert-or-increment and return the new count in one
            # statement, so there's no read-then-write gap to race in.
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
                # The increment stands even on refusal, so hammering a 429
                # isn't a free way to probe the limit.
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
        # Called after the call succeeds, since output tokens aren't known
        # beforehand — the budget check above can overshoot by up to one
        # concurrent call, which is accepted.
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
    """DATABASE_URL set -> PostgresRateLimiter; unset -> NullRateLimiter."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return NullRateLimiter()
    return PostgresRateLimiter(
        database_url,
        requests_per_hour=int(os.environ.get("RATE_LIMIT_PER_HOUR", 20)),
        daily_output_token_budget=int(os.environ.get("DAILY_OUTPUT_TOKEN_BUDGET", 50_000)),
    )
