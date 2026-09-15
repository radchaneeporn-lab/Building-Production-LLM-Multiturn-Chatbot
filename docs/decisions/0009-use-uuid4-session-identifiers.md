# 0009: Use UUID4 session identifiers

The session ID is handed to the browser and travels in a URL, a cookie, or
a request body — so it's visible to an attacker too, and its format is a
security decision.

**Other options considered:**
- An auto-incrementing integer
- A random UUID4
- A time-ordered UUID7 / ULID

**Decision:** Random UUID4 for every session, generated locally with no
coordination needed.

**Reverse if:** The sessions table gets large enough that random-ID index
fragmentation becomes measurable, or IDs need to sort by creation time —
UUID7 is a drop-in replacement at that point.

**Trade-off:** Random IDs scatter across a database index and hurt insert
performance at large scale — not a real cost yet. Worth remembering: an
unguessable ID is not the same as authentication.
