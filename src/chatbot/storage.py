from __future__ import annotations

import sqlite3
import uuid
from typing import Protocol

from .models import Message


# ---------------------------------------------------------------------------
# LEARNING NOTE — what this file is:
#
# In conversation.py, state lived inside a Python object (`self.history`)
# and died with the process. This file moves state OUT of objects and
# INTO a "store" with a tiny, deliberate interface:
#
#     create_session() -> session_id
#     load(session_id)  -> full history
#     append(session_id, *messages)
#
# Two implementations of that interface live below:
#     InMemoryStore  — a dict. Same lifetime as before, new shape.
#     SQLiteStore    — a file on disk. Survives restarts.
#
# The service layer (service.py) is written against the INTERFACE, so
# swapping dict -> SQLite -> Postgres later changes ZERO service code.
# This seam is the single most reusable production pattern in this repo.
# ---------------------------------------------------------------------------


class ConversationStore(Protocol):
    """The storage interface the service depends on.

    [LEARNING] Why `Protocol` and not a base class (ABC)?
    Protocol is *structural* typing: any class with these three methods
    satisfies it — no inheritance required. The store implementations
    below don't even mention ConversationStore. This is "duck typing
    with a type checker": the seam exists as a *contract*, not as a
    class hierarchy. In production codebases this keeps storage adapters
    (SQLite, Redis, DynamoDB...) totally decoupled from each other.

    [LEARNING] Why append() instead of save(full_history)?
    1. Efficiency: turn N only writes 2 new rows, not N*2 rows.
    2. Safety: you can never accidentally *shrink* a conversation by
       saving a stale copy — appends are monotonic.
    3. It matches how the data actually changes: conversations only
       ever grow at the end. Let the interface mirror reality.
    """

    def create_session(self) -> str: ...
    def session_exists(self, session_id: str) -> bool: ...
    def load(self, session_id: str) -> list[Message]: ...
    def append(self, session_id: str, *messages: Message) -> None: ...

    # [LEARNING] get_summary/set_summary are a DIFFERENT kind of seam than
    # the four methods above. load/append work with `messages` — an
    # append-only, immutable source of truth (see the docstring above on
    # why append() beats save()). The rolling summary is the opposite: a
    # derived, MUTABLE cache that exists purely to avoid re-summarizing
    # old turns from scratch every call. If it were lost, you could
    # regenerate it by re-summarizing `messages` — it is not itself a
    # record worth protecting, just a speed-up. Keeping it on a separate
    # method pair (rather than folding it into messages) keeps that
    # distinction visible in the interface, not just in a comment.
    def get_summary(self, session_id: str) -> tuple[str | None, int]: ...
    def set_summary(self, session_id: str, summary: str, summarized_through_turn: int) -> None: ...

    # [LEARNING] Added when PostgresStore arrived. A dict and a SQLite file
    # both tolerate never being closed; a CONNECTION POOL does not — it
    # holds real server-side sessions that should be handed back on
    # shutdown. Once one implementation needs a teardown hook, the hook
    # belongs on the seam, not bolted onto one class and special-cased at
    # every call site with hasattr(). The two stores that have nothing to
    # release implement it as a no-op, which is the honest answer rather
    # than an absent method.
    def close(self) -> None: ...


# ---------------------------------------------------------------------------
# Implementation 1: in-memory dict — the "before" picture
# ---------------------------------------------------------------------------
class InMemoryStore:
    """dict[session_id -> list[Message]]. Dies with the process.

    [LEARNING] Why build this at all if SQLite is the goal?
    1. It's the reference implementation: ~15 lines, obviously correct.
       When SQLiteStore misbehaves, you can diff behavior against this.
    2. It's what your tests will use — fast, no files to clean up.
    3. It proves the seam: the service runs identically on either store.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, list[Message]] = {}
        self._summaries: dict[str, tuple[str | None, int]] = {}

    def create_session(self) -> str:
        # [LEARNING] uuid4 = random, unguessable, no coordination needed.
        # Never use sequential ints for session IDs in production — they
        # are enumerable (attacker increments the ID, reads someone
        # else's conversation).
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = []
        self._summaries[session_id] = (None, 0)
        return session_id

    def session_exists(self, session_id: str) -> bool:
        return session_id in self._sessions

    def load(self, session_id: str) -> list[Message]:
        # list(...) returns a COPY — callers can't mutate our state
        # behind our back. Defensive copying at boundaries is cheap
        # insurance; shared mutable state is the classic source of
        # "works alone, breaks under load" bugs.
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
        """Nothing to release — a dict dies with the process."""


# ---------------------------------------------------------------------------
# Implementation 2: SQLite — the "after" picture, survives restarts
# ---------------------------------------------------------------------------
class SQLiteStore:
    """Same interface, but rows in a .db file instead of a dict.

    [LEARNING] Schema choice — one ROW PER MESSAGE, not one JSON blob
    per session. Both work; rows win because:
      - append = INSERT (cheap); a blob would be read-modify-rewrite
      - you can query across sessions (analytics, debugging, audits)
      - partial reads become possible later ("last 20 turns only" —
        exactly what a truncation strategy needs)
    The `turn_index` column preserves ordering explicitly. Never rely on
    insertion order or rowid for ordering — make ordering DATA.
    """

    def __init__(self, db_path: str = "conversations.db") -> None:
        # [LEARNING] check_same_thread=False lets this connection be used
        # from other threads (an HTTP server will need that). SQLite
        # serializes writes internally; for this learning stage that's
        # enough. Real concurrency care comes with the server step.
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
        # [LEARNING] CREATE TABLE IF NOT EXISTS only helps a BRAND-NEW
        # database file. A conversations.db created before this feature
        # existed already has a `sessions` table WITHOUT these two
        # columns, and IF NOT EXISTS does nothing to an existing table's
        # shape. PRAGMA table_info lists the columns a table actually
        # has, so we can add whatever's missing — a tiny hand-rolled
        # migration, standing in for what alembic/etc. automate for real
        # schema changes on a live production database.
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
        with self._conn:  # [LEARNING] `with conn:` = transaction, auto-commit/rollback
            self._conn.execute("INSERT INTO sessions (id) VALUES (?)", (session_id,))
        return session_id

    def session_exists(self, session_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return row is not None

    def load(self, session_id: str) -> list[Message]:
        if not self.session_exists(session_id):
            # Mirror the dict's KeyError so both stores fail identically.
            # [LEARNING] Implementations of a seam must match on error
            # behavior too, or callers silently depend on one of them.
            raise KeyError(session_id)
        rows = self._conn.execute(
            """
            SELECT role, content, token_count FROM messages
            WHERE session_id = ?
            ORDER BY turn_index
            """,
            (session_id,),
        ).fetchall()
        # [LEARNING] The DB gives us raw strings; we re-wrap them in the
        # domain type (Message) HERE, at the storage boundary. Above this
        # line, nothing knows SQLite exists; below it, nothing knows
        # Message exists. Same translation discipline as client.py does
        # for the Anthropic SDK.
        return [
            Message(role=role, content=content, token_count=token_count)
            for role, content, token_count in rows
        ]

    def append(self, session_id: str, *messages: Message) -> None:
        # next turn_index = current row count for this session
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
        # [LEARNING] Parameterized queries (?) everywhere — NEVER f-string
        # user text into SQL. Message content is user-controlled input;
        # f-stringing it is a SQL injection.

    def get_summary(self, session_id: str) -> tuple[str | None, int]:
        row = self._conn.execute(
            "SELECT summary_text, summarized_through_turn FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return row[0], row[1]

    def set_summary(self, session_id: str, summary: str, summarized_through_turn: int) -> None:
        # UPDATE, not INSERT — this is the mutable-cache half of the store.
        # Compare with append(): messages only ever grow; this overwrites
        # in place, because only the LATEST summary is ever useful.
        with self._conn:
            self._conn.execute(
                "UPDATE sessions SET summary_text = ?, summarized_through_turn = ? WHERE id = ?",
                (summary, summarized_through_turn, session_id),
            )

    def close(self) -> None:
        self._conn.close()


# ---------------------------------------------------------------------------
# Implementation 3: PostgreSQL — the "after the single-writer file" picture
# ---------------------------------------------------------------------------
class PostgresStore:
    """Same interface again, over a real database server.

    [LEARNING] What actually changed versus SQLiteStore, and why each one
    is forced rather than cosmetic:

      CONNECTION -> POOL. SQLite was ONE connection shared across threads
        (`check_same_thread=False`). Postgres is a server reached over a
        socket, and a connection is a real server-side session that can
        only run one statement at a time. FastAPI runs `def` route
        handlers in a thread pool, so concurrent requests genuinely need
        concurrent connections — hence a POOL, sized once at startup.
        Opening a connection per request instead would pay a TCP+auth
        handshake on every /chat call.

      PLACEHOLDERS ? -> %s. Cosmetic, but the discipline behind it is not:
        still parameterized, never f-strings. Message content is
        user-controlled; that hasn't changed just because the engine did.

      COUNT(*) -> MAX(turn_index) + 1, under a ROW LOCK. This is the real
        upgrade, and 0014's open race is why. The SQLite version read a
        count and then inserted; two concurrent appends to one session
        could both read N and both try to write turn N. SQLite hid this
        behind a global write lock on the whole file — correct, but by
        serializing EVERY writer in the process. Postgres locks a single
        session's row instead (`SELECT ... FOR UPDATE`), so two different
        conversations still append in parallel while two appends to the
        SAME conversation take turns. That's the concurrency win that
        motivated the move, made explicit.
    """

    def __init__(self, conninfo: str, min_size: int = 1, max_size: int = 10) -> None:
        # [LEARNING] Imported HERE, not at module top, so that importing
        # this module at all doesn't require a Postgres driver. Someone
        # running main_service.py on SQLite — no database server, no
        # DATABASE_URL — should not need psycopg installed to do it, and a
        # top-level import would make them. The cost of an optional backend
        # is paid by whoever actually asks for that backend.
        try:
            from psycopg_pool import ConnectionPool
        except ModuleNotFoundError as exc:  # pragma: no cover - setup error
            raise RuntimeError(
                "DATABASE_URL is set, which selects PostgresStore, but the "
                "Postgres driver is not installed. Either install it:\n"
                "    pip install 'psycopg[binary,pool]'\n"
                "or unset DATABASE_URL to fall back to SQLite."
            ) from exc

        # [LEARNING] `open=True` then `wait()` is deliberate: it forces the
        # first connection at STARTUP. Without it the pool opens lazily and
        # a bad DATABASE_URL / unreachable database surfaces as a failed
        # request minutes later, instead of a process that refuses to boot.
        # Fail fast, loudly, at the point the operator is still watching.
        self._pool = ConnectionPool(conninfo, min_size=min_size, max_size=max_size, open=True)
        self._pool.wait(timeout=30)
        self._create_schema()

    def _create_schema(self) -> None:
        # [LEARNING] No PRAGMA-style hand-rolled migration here, unlike
        # SQLiteStore — this database starts empty, so the CREATE statements
        # ARE the whole schema. That convenience expires the first time this
        # schema changes while rows already exist in a deployed database;
        # that's the point a real migration tool stops being optional.
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
        # [LEARNING] `with pool.connection()` borrows a connection AND opens
        # a transaction; leaving the block commits, an exception rolls back
        # and the connection goes back to the pool either way.
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
                # Same KeyError all three stores raise — see SQLiteStore.load.
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
            # [LEARNING] FOR UPDATE takes a row-level lock on THIS session
            # that is held until the transaction ends. A second append to
            # the same session blocks right here until the first commits,
            # so it reads a MAX(turn_index) that already includes the first
            # writer's rows. This is PESSIMISTIC locking: take the lock
            # before reading, rather than detecting the collision after the
            # fact (the PRIMARY KEY would catch it, but only as an error to
            # retry). Appends to OTHER sessions are untouched.
            locked = conn.execute(
                "SELECT 1 FROM sessions WHERE id = %s FOR UPDATE", (session_id,)
            ).fetchone()
            if locked is None:
                raise KeyError(session_id)

            (next_index,) = conn.execute(
                "SELECT COALESCE(MAX(turn_index) + 1, 0) FROM messages WHERE session_id = %s",
                (session_id,),
            ).fetchone()

            # [LEARNING] MAX+1, not COUNT(*) as the SQLite version used.
            # They agree only while nothing is ever deleted; MAX+1 stays
            # correct afterwards, and turn_index is the ordering key (0008),
            # so a collision there corrupts message order permanently.
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
        """Hand every pooled connection back to the server."""
        self._pool.close()


# ---------------------------------------------------------------------------
# WHAT'S DELIBERATELY *NOT* HERE YET:
#
# 1. delete_session / list_sessions — trivial to add when a UI needs them.
# 2. A real migration TOOL (alembic etc.). Still absent, and now it matters
#    more, not less: PostgresStore's CREATE TABLE IF NOT EXISTS only helps
#    an empty database. The moment this schema changes while a deployed
#    database holds rows, there is no mechanism here to move it forward.
# 3. Indexes beyond the primary keys. `WHERE session_id = ... ORDER BY
#    turn_index` is served by the (session_id, turn_index) PK, which is why
#    nothing is slow yet — that is luck of column order, not a decision
#    anyone made, and it stops holding the first time a query filters on
#    anything else.
# 4. A data migration from the SQLite file. PostgresStore starts EMPTY;
#    conversations written before the switch still live in conversations.db
#    and are not reachable from a Postgres-backed process.
# 5. Retry/reconnect policy. If Postgres restarts, in-flight pooled
#    connections fail; the pool reopens them, but a request in flight at
#    that moment still surfaces the error to the caller.
# ---------------------------------------------------------------------------
