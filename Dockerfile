# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DB_PATH=/app/data/conversations.db

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

# Same /health route a platform load balancer would poll.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

CMD ["uvicorn", "main_api:app", "--host", "0.0.0.0", "--port", "8000"]
