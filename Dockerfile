# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

# [LEARNING] PORT and HOST are ENV with defaults, not literals in CMD, because
# a deploy platform INJECTS the port it wants the container to bind and routes
# traffic to that port only — a hardcoded `--port 8000` boots fine and then
# fails every healthcheck, which is a confusing way to learn this (ADR 0018).
# HOST is a variable for a narrower reason: some platforms' private networking
# is IPv6-only, where binding `0.0.0.0` listens on the wrong address family and
# the service is simply unreachable. `HOST=::` is the fix there; `0.0.0.0` is
# right for Compose and stays the default.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/app/data/conversations.db \
    PORT=8000 \
    HOST=0.0.0.0

# Install dependencies first, from only the files pip needs to resolve them
# (pyproject.toml + the src/ package it points at). This layer is cached
# and only rebuilds when a dependency actually changes — editing main_api.py
# below won't invalidate it.
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

# Entry point script lives at the repo root, outside the installed package.
COPY main_api.py ./

# Run as non-root; own /app/data so the mounted volume is writable by it.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Same /health route a platform load balancer would poll. Reads $PORT rather
# than assuming 8000, for the same reason CMD does.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import os,urllib.request as u; u.urlopen(f\"http://127.0.0.1:{os.environ['PORT']}/health\", timeout=3)" || exit 1

# [LEARNING] Shell form (not the exec-form JSON array) because $PORT/$HOST have
# to be EXPANDED, and Docker only does that through a shell. But a shell as
# PID 1 does not forward signals to its child: `docker stop` / a platform's
# redeploy sends SIGTERM to sh, uvicorn never sees it, and 30s later everything
# is SIGKILLed — so lifespan's `store.close()` (ADR 0013, main_api.py) silently
# stops running and Postgres connections leak on every deploy. `exec` replaces
# the shell with uvicorn, so uvicorn IS PID 1 and receives the signal itself.
CMD ["sh", "-c", "exec uvicorn main_api:app --host \"$HOST\" --port \"$PORT\""]
