# 0014: Concurrency safety for the SQLite store

*Status: Open*

Two requests hitting the same conversation at the exact same moment can
each read the same "next message number" and try to write the same one —
rare, and the kind of bug that only shows up under real traffic.

**Other options considered:**
- A per-session lock inside the app — simple, but doesn't survive more than one process
- Give every request its own connection, plus an atomic "next index" query
- Push the fix into the database with a conditional update
- Leave it open and fix it properly during the Postgres migration

**Decision:** Left open here. Resolved by moving to Postgres (0017), which
has real row-level locking.

**Reverse if:** n/a — this is the record that stayed open until 0017
closed it.

**Trade-off:** Leaving it open meant accepting a real, if rare, risk of
corrupted message order under concurrent use.
