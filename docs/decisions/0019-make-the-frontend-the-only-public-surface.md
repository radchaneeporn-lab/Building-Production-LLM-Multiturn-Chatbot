# 0019: Make the frontend the only public surface

With both services on the internet, the browser's copy of the backend's
address gets baked directly into the frontend's JavaScript at build
time — so the backend needs a public URL before the frontend can even be
built.

**Other options considered:**
- The frontend's own server forwards chat requests to the backend
- Next.js `rewrites()` pointing at the backend
- Keep both services public, list allowed origins for CORS
- A separate gateway service in front of both

**Decision:** A server-side route handler on the frontend proxies requests
to the private backend. The backend never needs a public address, and the
browser only ever talks to one place.

**Reverse if:** A client other than this frontend needs to call the
backend directly — a mobile app, a script, someone else's integration.

**Trade-off:** An extra network hop on every message, and the frontend
becomes a hard dependency of the API — a frontend outage is now an API
outage too.
