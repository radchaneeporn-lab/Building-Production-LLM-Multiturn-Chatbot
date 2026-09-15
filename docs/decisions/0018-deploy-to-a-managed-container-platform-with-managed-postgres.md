# 0018: Deploy to a managed container platform, with managed Postgres

Docker Compose proves the app runs — it doesn't give it a public URL, a
database that isn't just a file on a laptop, or anywhere safe to put an API
key.

**Other options considered:**
- Railway — both existing Docker images, plus its managed Postgres
- Split across three vendors, each built for its piece (Vercel, Render, Neon)
- Fly.io for both containers
- AWS ECS + RDS
- One VM, running `docker compose up -d` as today

**Decision:** Railway, because it runs the exact images already built and
tested, rather than requiring a different build process for a hosting
platform. See [`deploy-railway.md`](deploy-railway.md) for the steps.

**Reverse if:** A second, identical environment (staging) is needed, or
replica count goes above one.

**Trade-off:** A standing monthly bill, and a chunk of configuration that
now lives in a dashboard instead of the repo.
