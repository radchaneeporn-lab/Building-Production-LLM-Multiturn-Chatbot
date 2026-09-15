# 0006: Define the store seam as a Protocol

Storage was always going to change — a dict today, SQLite tomorrow,
Postgres after that. The service shouldn't have to care which.

**Other options considered:**
- No interface at all — construct `SQLiteStore` directly wherever it's needed
- An abstract base class every store inherits from
- A `Protocol` — structural typing, no inheritance required

**Decision:** `ConversationStore` declares the methods a store needs to
have. Implementations don't import or mention it at all — they just happen
to match.

**Reverse if:** Nothing foreseeable.

**Trade-off:** One extra layer of indirection, in exchange for swapping the
storage backend later being a one-line change instead of a rewrite.
