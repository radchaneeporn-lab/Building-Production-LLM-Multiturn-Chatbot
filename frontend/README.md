# Frontend

Minimal chat UI (Next.js App Router) for the FastAPI backend at the repo root.
One page (`app/page.js`): a message list, an input box, and a session_id
carried in React state exactly the way `main_api.py`'s `ChatRequest` expects
it — omitted on the first message, then echoed back on every message after.

## Run locally (no Docker)

Backend running separately on `http://localhost:8000` (see the repo root
README), then:

```bash
npm install
npm run dev
```

Open http://localhost:3000. `NEXT_PUBLIC_API_URL` defaults to
`http://localhost:8000` if unset — override it with a `.env.local` here if
your backend runs elsewhere.

## Run via Docker Compose

From the repo root:

```bash
docker compose up --build
```

Starts both `chatbot` (backend, :8000) and `frontend` (:3000) together — see
the root `docker-compose.yml` for how `NEXT_PUBLIC_API_URL` (build-time) and
`FRONTEND_ORIGIN` (backend CORS) are wired between them.
