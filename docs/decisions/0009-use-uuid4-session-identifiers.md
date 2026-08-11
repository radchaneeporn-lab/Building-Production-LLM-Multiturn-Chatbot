# 0009: Use UUID4 session identifiers

**Date:** 2026-08-12 (recorded retroactively)
**Status:** Accepted

**Context:**
Per 0005 the session ID is the caller's entire state — it travels in a URL, a
cookie, or a JSON body. That means it is user-visible, user-modifiable, and
attacker-visible. Its format is a security decision, not a formatting one.

**Options:**
1. Auto-incrementing integer.
2. UUID4 (random).
3. UUID7 / ULID (time-ordered, random suffix).

**Chose:** (2). `str(uuid.uuid4())` in both store implementations. Random,
unguessable, and generated without coordination — no round-trip to the database
to find out what the ID is, which also means IDs can be minted by any process
or client without collision risk.

**Rejected:**
(1) is enumerable. An attacker who receives session `41` requests `40`, `39`,
`38` and reads other people's conversations. Sequential public identifiers also
leak volume — competitor arithmetic on how many conversations exist. This is the
canonical IDOR vulnerability and it is created at schema-design time, not at
handler time.

(3) is the better *database* choice at scale, because random UUIDs scatter
across the index and hurt insert locality on large tables. Not a real cost yet,
and UUID4 has the wider library support.

**Reverses when:** The `sessions` table gets large enough that index
fragmentation from random primary keys is measurable, or IDs need to be sortable
by creation time without a join. UUID7 is then a drop-in with the same
unguessability property.

**Critically:** an unguessable ID is **not** authorisation. Right now anyone
holding a session ID can read and write that conversation, and `/chat` has no
authentication at all — it is an open, unmetered proxy to a paid model. That is
acceptable on localhost and unacceptable the moment it has a public URL. This
record does not solve it; it should not be mistaken for solving it.

**Pillar pressure:** Security. Cost is nil.
