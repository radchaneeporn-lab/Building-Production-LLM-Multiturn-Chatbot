# 0008: Store one row per message, with explicit ordering

A conversation is a list. Relational storage offers two obvious shapes for
a list: serialize it into one column, or normalize it into rows.

**Other options considered:**
- One row per conversation, with a JSON blob column holding every message
- One row per message, ordered by an explicit column

**Decision:** One row per message. Appending is a cheap insert, not a
rewrite of the whole conversation. Ordering is stored explicitly as a
`turn_index` column, never assumed from insertion order.

**Reverse if:** Nothing foreseeable — this row shape survives the move to
Postgres unchanged.

**Trade-off:** Slightly more rows in the table, in exchange for cheap
appends and the ability to query across conversations at all.
