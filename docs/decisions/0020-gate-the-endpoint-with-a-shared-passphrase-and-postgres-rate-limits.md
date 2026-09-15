# 0020: Gate the endpoint with a shared passphrase and Postgres rate limits

A public chat endpoint in front of a paid model needs two separate
protections: who's allowed to use it, and how much any of them can spend.

**Other options considered:**
- A shared passphrase, a signed cookie, and rate limits stored in Postgres
- Real per-user accounts with hashed passwords
- No login at all, rate limit by IP only
- API keys issued by hand
- An authenticating reverse proxy in front of everything

**Decision:** A shared password (checked by the frontend, which issues a
signed cookie), a required secret between frontend and backend so the
backend can't be called directly, and two Postgres-backed limits: a
per-visitor hourly request cap, and a global daily token budget.

**Reverse if:** More than one person needs their own separate
conversations, or the passphrase needs to be revoked per person.

**Trade-off:** Still no per-person identity, and failed logins aren't rate
limited yet — this narrows the risk, it doesn't fully close it.
