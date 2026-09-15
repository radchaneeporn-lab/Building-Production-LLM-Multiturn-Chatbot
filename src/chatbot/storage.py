from __future__ import annotations

import sqlite3
import uuid
from typing import Protocol

from .models import Message


class ConversationStore(Protocol):
    """Storage seam the service layer depends on. Structural typing
    (Protocol, not ABC) — implementations below don't inherit from or
    import this at all, so storage backends stay decoupled from each
    other.

    append() rather than save(full_history): cheaper (2 new rows, not the
    whole conversation rewritten), and a stale caller can never shrink a
    conversation by accident.
    """

    def create_session(self) -> str: ...
    def session_exists(self, session_id: str) -> bool: ...
    def load(self, session_id: str) -> list[Message]: ...
    def append(self, session_id: str, *messages: Message) -> None: ...

    # A different kind of field from the four above: messages are an
    # append-only record, but the summary is a mutable, regenerable cache.
    def get_summary(self, session_id: str) -> tuple[str | None, int]: ...
    def set_summary(self, session_id: str, summary: str, summarized_through_turn: int) -> None: ...

    def close(self) -> None: ...


class InMemoryStore:
    """dict[session_id -> list[Message]]. Dies with the process. Used for
    tests and as the reference to check other stores' behaviour against."""

    def __init__(self) -> None:
        self._sessions: dict[str, list[Message]] = {}
        self._summaries: dict[str, tuple[str | None, int]] = {}

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = []
        self._summaries[session_id] = (None, 0)
        return session_id

    def session_exists(self, session_id: str) -> bool:
        return session_id in self._sessions

    def load(self, session_id: str) -> list[Message]:
        # Copy, so callers can't mutate our state behind our back.
        return list(self._sessions[session_id])

    def append(self, session_id: str, *messages: Message) -> None:
        self._sessions[session_id].extend(messages)

    def get_summary(self, session_id: str) -> tuple[str | None, int]:
        if session_id not in self._summaries:
            raise KeyError(session_id)
        return self._summaries[session_id]

    def set_summary(self, session_id: str, summary: str, summarized_through_turn: int) -> None:
        self._summaries[session_id] = (summary, summarized_through_turn)

    def close(self) -> None:
        pass


class SQLiteStore:
    """Same interface, backed by a .db file — survives process restarts.

    One row per message, ordered by an explicit turn_index column (never
    insertion order or rowid).
    """

    def __init__(self, db_path: str = "conversations.db") -> None:
        # check_same_thread=False: this connection is used from multiple
        # threads under an HTTP server. SQLite serialises writes internally.
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id                      TEXT PRIMARY KEY,
                created_at              TEXT NOT NULL DEFAULT (datetime('now')),
                summary_text            TEXT,
                summarized_through_turn INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                session_id TEXT    NOT NULL REFERENCES sessions(id),
                turn_index INTEGER NOT NULL,
                role       TEXT    NOT NULL,
                content    TEXT    NOT NULL,
                token_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT    NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (session_id, turn_index)
            )
            """
        )
        self._conn.commit()
        self._migrate_add_summary_columns()
        self._migrate_add_token_count_column()

    def _migrate_add_summary_columns(self) -> None:
        # CREATE TABLE IF NOT EXISTS only helps a brand-new file; an
        # existing sessions table needs these columns added by hand.
        existing_cols = {row[1] for row in self._conn.execute("PRAGMA table_info(sessions)")}
        if "summary_text" not in existing_cols:
            self._conn.execute("ALTER TABLE sessions ADD COLUMN summary_text TEXT")
        if "summarized_through_turn" not in existing_cols:
            self._conn.execute(
                "ALTER TABLE sessions ADD COLUMN summarized_through_turn INTEGER NOT NULL DEFAULT 0"
            )
        self._conn.commit()

    def _migrate_add_token_count_column(self) -> None:
        existing_cols = {row[1] for row in self._conn.execute("PRAGMA table_info(messages)")}
        if "token_count" not in existing_cols:
            self._conn.execute(
                "ALTER TABLE messages ADD COLUMN token_count INTEGER NOT NULL DEFAULT 0"
            )
        self._conn.commit()

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        with self._conn:
            self._conn.execute("INSERT INTO sessions (id) VALUES (?)", (session_id,))
        return session_id

    def session_exists(self, session_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return row is not None

    def load(self, session_id: str) -> list[Message]:
        if not self.session_exists(session_id):
            raise KeyError(session_id)
        rows = self._conn.execute(
            """
            SELECT role, content, token_count FROM messages
            WHERE session_id = ?
            ORDER BY turn_index
            """,
            (session_id,),
        ).fetchall()
        return [
            Message(role=role, content=content, token_count=token_count)
            for role, content, token_count in rows
        ]

    def append(self, session_id: str, *messages: Message) -> None:
        (count,) = self._conn.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
        ).fetchone()
        with self._conn:
            self._conn.executemany(
                """
                INSERT INTO messages (session_id, turn_index, role, content, token_count)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (session_id, count + i, m.role, m.content, m.token_count or 0)
                    for i, m in enumerate(messages)
                ],
            )
        # Parameterized queries only — message content is user input.

    def get_summary(self, session_id: str) -> tuple[str | None, int]:
        row = self._conn.execute(
            "SELECT summary_text, summarized_through_turn FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return row[0], row[1]

    def set_summary(self, session_id: str, summary: str, summarized_through_turn: int) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE sessions SET summary_text = ?, summarized_through_turn = ? WHERE id = ?",
                (summary, summarized_through_turn, session_id),
            )

    def close(self) -> None:
        self._conn.close()


class PostgresStore:
    """Same interface again, over a real database server — the fix for
    SQLiteStore's single-writer-file limit under concurrent requests."""

    def __init__(self, conninfo: str, min_size: int = 1, max_size: int = 10) -> None:
        # Imported here, not at module level, so running on SQLite doesn't
        # require the Postgres driver to be installed.
        try:
            from psycopg_pool import ConnectionPool
        except ModuleNotFoundError as exc:  # pragma: no cover - setup error
            raise RuntimeError(
                "DATABASE_URL is set, which selects PostgresStore, but the "
                "Postgres driver is not installed. Either install it:\n"
                "    pip install 'psycopg[binary,pool]'\n"
                "or unset DATABASE_URL to fall back to SQLite."
            ) from exc

        # open=True + wait(): force the first connection now, so a bad
        # DATABASE_URL fails the boot instead of the first request.
        self._pool = ConnectionPool(conninfo, min_size=min_size, max_size=max_size, open=True)
        self._pool.wait(timeout=30)
        self._create_schema()

    def _create_schema(self) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id                      TEXT PRIMARY KEY,
                    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
                    summary_text            TEXT,
                    summarized_through_turn INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    session_id  TEXT    NOT NULL REFERENCES sessions(id),
                    turn_index  INTEGER NOT NULL,
                    role        TEXT    NOT NULL,
                    content     TEXT    NOT NULL,
                    token_count INTEGER NOT NULL DEFAULT 0,
                    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
                    PRIMARY KEY (session_id, turn_index)
                )
                """
            )

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        with self._pool.connection() as conn:
            conn.execute("INSERT INTO sessions (id) VALUES (%s)", (session_id,))
        return session_id

    def session_exists(self, session_id: str) -> bool:
        with self._pool.connection() as conn:
            row = conn.execute("SELECT 1 FROM sessions WHERE id = %s", (session_id,)).fetchone()
        return row is not None

    def load(self, session_id: str) -> list[Message]:
        with self._pool.connection() as conn:
            exists = conn.execute(
                "SELECT 1 FROM sessions WHERE id = %s", (session_id,)
            ).fetchone()
            if exists is None:
                raise KeyError(session_id)
            rows = conn.execute(
                """
                SELECT role, content, token_count FROM messages
                WHERE session_id = %s
                ORDER BY turn_index
                """,
                (session_id,),
            ).fetchall()
        return [
            Message(role=role, content=content, token_count=token_count)
            for role, content, token_count in rows
        ]

    def append(self, session_id: str, *messages: Message) -> None:
        if not messages:
            return
        with self._pool.connection() as conn:
            # FOR UPDATE locks this session's row until the transaction
            # ends, so a second concurrent append waits and reads a
            # turn_index that already accounts for the first one. Other
            # sessions are unaffected.
            locked = conn.execute(
                "SELECT 1 FROM sessions WHERE id = %s FOR UPDATE", (session_id,)
            ).fetchone()
            if locked is None:
                raise KeyError(session_id)

            (next_index,) = conn.execute(
                "SELECT COALESCE(MAX(turn_index) + 1, 0) FROM messages WHERE session_id = %s",
                (session_id,),
            ).fetchone()

            conn.cursor().executemany(
                """
                INSERT INTO messages (session_id, turn_index, role, content, token_count)
                VALUES (%s, %s, %s, %s, %s)
                """,
                [
                    (session_id, next_index + i, m.role, m.content, m.token_count or 0)
                    for i, m in enumerate(messages)
                ],
            )

    def get_summary(self, session_id: str) -> tuple[str | None, int]:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT summary_text, summarized_through_turn FROM sessions WHERE id = %s",
                (session_id,),
            ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return row[0], row[1]

    def set_summary(self, session_id: str, summary: str, summarized_through_turn: int) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "UPDATE sessions SET summary_text = %s, summarized_through_turn = %s WHERE id = %s",
                (summary, summarized_through_turn, session_id),
            )

    def close(self) -> None:
        self._pool.close()
