# Production-Agentic-Multiturn-Chatbot

## Run with Docker

```
docker compose up --build
```

Requires a `.env` file with `ANTHROPIC_API_KEY=...` in the project root
(read via `env_file:` in `docker-compose.yml`). The API is then at
`http://localhost:8000` — `GET /health`, `POST /chat`. `conversations.db`
lives in the `chatbot-data` named volume, so it survives
`docker compose down` (but not `docker compose down -v`).

Without compose:

```
docker build -t chatbot .
docker run -p 8000:8000 --env-file .env -v chatbot-data:/app/data chatbot
```