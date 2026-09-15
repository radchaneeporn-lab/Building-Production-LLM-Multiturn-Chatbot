"""Quick read-only peek at conversations.db.

Run from the project root: python -m src.chatbot.inspect_db
"""

import sqlite3

conn = sqlite3.connect("conversations.db")

print("=== sessions ===")
for row in conn.execute("SELECT id, created_at FROM sessions ORDER BY created_at"):
    print(row)

print("\n=== messages ===")
for row in conn.execute(
    "SELECT session_id, turn_index, role, content, created_at FROM messages ORDER BY session_id, turn_index"
):
    print(row)

conn.close()
