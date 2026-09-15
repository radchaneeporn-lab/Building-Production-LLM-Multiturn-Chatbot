# 0009: Use UUID4 session identifiers

**Date:** 2026-08-12 (recorded retroactively)
**Status:** Accepted

**Context:**
Per 0005, the session ID is the caller's entire state — it travels in a URL,
a cookie, or a JSON body. That makes it user-visible, user-modifiable, and
attacker-visible. Its format is a security decision, not a formatting one.

**Options:**
1. Auto-incrementing integer.
2. UUID4 (random).
3. UUID7 / ULID (time-ordered, random suffix).

**Chose:** (2). `str(uuid.uuid4())` in both store implementations. Random,
unguessable, and generated without coordination — no round-trip to the
database to learn what the ID is, so IDs can be minted by any process or
client with no collision risk.

**Rejected:**
(1) is enumerable. An attacker handed session `41` requests `40`, `39`, `38`
and reads other people's conversations. Sequential public identifiers also
leak volume — how many conversations exist, for free. This is the canonical
IDOR vulnerability, and it's created at schema-design time, not at handler
time.

(3) is the better database choice at scale, since random UUIDs scatter
across the index and hurt insert locality on large tables. Not a real cost
yet, and UUID4 has wider library support.

**Reverses when:** The `sessions` table gets large enough that index
fragmentation from random primary keys is measurable, or IDs need to sort by
creation time without a join. UUID7 is then a drop-in with the same
unguessability.

**One thing worth being blunt about:** an unguessable ID is not
authorisation. Right now anyone holding a session ID can read and write that
conversation, and `/chat` has no authentication at all — it's an open,
unmetered proxy to a paid model. Fine on localhost, not fine the moment it
has a public URL. This record doesn't solve that; it shouldn't be mistaken
for solving it.

**What I know:**
- Enumerable identifiers are an access-control vulnerability (IDOR).
- Unguessability is not authorisation.
- Random primary keys carry an index-locality cost at scale.

**What I don't know yet:**
This is the thinnest-covered pillar in the log — one record out of fourteen
mentions security. That's the honest state of the project.

- **Authentication vs. authorisation.** Two different questions: who are
  you, and what may you do. My system answers neither. I should be able to
  state which layer answers each, and why a session ID conflates them today.
- **How a request proves identity.** Opaque session token looked up
  server-side, signed token (JWT) validated without a lookup, or an API key —
  which is revocable, which scales, which leaks what.
- **Rate limiting and quotas.** `/chat` can be called without limit, and
  every call costs money. Token bucket vs. leaky bucket vs. fixed window,
  per-user vs. per-IP, and where the limit gets enforced.
- **Secrets handling.** The API key comes from `.env` via `dotenv`. Correct
  locally, doesn't survive deployment: a container needs the secret injected
  at runtime, never baked into the image or committed.
- **Transport security and data at rest.** HTTPS terminates somewhere — is
  the hop after it encrypted? Conversation content is user data sitting
  unencrypted in a file. Encryption in transit vs. at rest, and what each
  actually protects against.
- **Least privilege and blast radius.** If one component is compromised,
  what else does it reach? Everything currently runs as one process with one
  credential.
- **Data retention.** Conversations are stored forever with no deletion
  path. Once real users exist, that's a policy question with legal weight,
  not just a storage cost.

**Pillar pressure:** Security. Cost is nil.
