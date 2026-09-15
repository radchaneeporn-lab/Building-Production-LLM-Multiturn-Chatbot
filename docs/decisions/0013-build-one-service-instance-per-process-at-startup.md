# 0013: Build one service instance per process, at startup

Under an HTTP server, the process doesn't build its objects once and throw
them away like a script does — it runs continuously and needs a defined
startup and shutdown point.

**Other options considered:**
- Build the client/store/service inside each request handler
- Module-level globals created at import time
- Build once at startup, inside a defined lifespan hook

**Decision:** One `ChatService`, built once at process startup, serves
every concurrent request.

**Reverse if:** A dependency needs per-request scope — a request-scoped
transaction, a per-user credential.

**Trade-off:** None meaningful — this only works because the service holds
no state of its own (0005), which is exactly what makes sharing it safe.
