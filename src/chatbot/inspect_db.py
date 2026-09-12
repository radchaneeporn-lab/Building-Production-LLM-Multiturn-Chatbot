"""Quick read-only peek at conversations.db. Run: python -m src.chatbot.inspect_db"""
# python -m src.chatbot.inspect_db
#   The -m flag runs it as a module using the package's dotted
#   path, which is why it must be run from root (not python
#   src/chatbot/inspect_db.py, which would break the
#   relative import context if the file ever imports siblings
#   via .)



import sqlite3

# [LEARNING] sqlite3.connect() opens (or creates) the .db FILE and hands
# back a Connection object — this IS the database, there's no separate
# server process to talk to (unlike Postgres/MySQL). One process can hold
# many connections to the same file; SQLite itself handles the locking.
conn = sqlite3.connect("conversations.db")

# [LEARNING] conn.execute(sql, params=()) is shorthand for:
#     cursor = conn.cursor()
#     cursor.execute(sql, params)
# It creates a throwaway Cursor under the hood and returns it. A Cursor is
# the thing that actually runs SQL and walks the result rows — the
# Connection just owns the file handle/transaction.
#
# For SELECT, execute() doesn't return data yet — it returns the Cursor,
# which is ITERABLE: each iteration pulls one more row as a tuple
# (col1, col2, ...) in the same order as your SELECT list. `for row in
# conn.execute(...)` streams rows one at a time instead of loading them
# all into memory — same idea as reading a file line by line.
# (Cursor also offers .fetchone() for a single row, .fetchall() to grab
# every row as a list — fine for small tables, wasteful for big ones.)
print("=== sessions ===")
for row in conn.execute("SELECT id, created_at FROM sessions ORDER BY created_at"):
    print(row)

print("\n=== messages ===")
for row in conn.execute(
    "SELECT session_id, turn_index, role, content, created_at FROM messages ORDER BY session_id, turn_index"
):
    print(row)

# [LEARNING] conn.close() releases the file handle. No writes happened
# here, so there's nothing to commit — but for INSERT/UPDATE you must
# either call conn.commit() or use `with conn:` (see storage.py) so the
# transaction actually lands on disk instead of rolling back silently.
conn.close()




#   - sqlite3.connect() — opens/creates the .db file
#   directly; SQLite has no server process, the file is the
#   database.
#   - conn.execute(...) — shorthand for creating a cursor
#   and running SQL on it; for SELECT it returns a Cursor
#   you can iterate directly (streaming rows one-by-one),
#   rather than needing .fetchall() first.
#   - conn.close() — plus a note that since this script
#   only reads, there's no commit needed; for writes you'd
#   need conn.commit() or the with conn: pattern already
#   used in storage.py.


# ❯ why sqlite is a good choice here ? why not prosgresSQL with superbase for production   
#   purpose in the future       

# SQLite is the right choice right now, not forever — and the codebase already says so
#   explicitly in storage.py:26 ("swapping dict → SQLite → Postgres later changes ZERO
#   service code"). The ConversationStore Protocol seam exists precisely so this swap is
#   cheap when you need it.

#   Why SQLite fits this stage: zero setup (no server, no Supabase account, no network
#   hop), the whole DB is one file you can literally open in a VS Code extension, and it
#   teaches the real concepts (schema, rows-per-message, transactions) without
#   cloud-service noise getting in the way of learning.

#   Why you'd move to Postgres/Supabase later: SQLite serializes all writes through one
#   file lock — fine for one process, one user, learning exercises; it falls over once you
#   have concurrent request handlers (the HTTP server step) hitting the same session from
#   multiple workers, or need multiple app instances sharing one database, or want managed
#   backups/auth/row-level security (which is Supabase's actual value-add over raw
#   Postgres).

#   The main tradeoff: SQLite's simplicity is also its ceiling — single-writer concurrency
#   and no network access from another machine. When you build the HTTP server step and
#   need horizontal scaling, that's your signal to swap in a PostgresStore implementing the
#   same three-method interface — the service layer won't even notice.