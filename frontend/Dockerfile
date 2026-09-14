# syntax=docker/dockerfile:1

# [LEARNING] Multi-stage build — three named stages (deps, builder, runner),
# each `FROM node:...` starting a fresh layer set. Only the LAST stage ends
# up in the final image; the others exist purely to produce artifacts that
# get COPY --from=<stage>'d forward. This is the "discard the build tooling
# from the final image" pattern ADR 0015 named as a learning goal for the
# backend Dockerfile — applied here from the start instead of retrofitted.

FROM node:22-slim AS deps
WORKDIR /app
# Installing from the lockfile alone, before any app code, means this
# layer is cached and only rebuilds when package.json/package-lock.json
# actually change — same reasoning as the backend Dockerfile's
# pyproject.toml-before-src copy.
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# [LEARNING] There is deliberately NO build ARG here any more. This stage
# used to take NEXT_PUBLIC_API_URL, because NEXT_PUBLIC_* vars are inlined
# into the CLIENT bundle at `next build` time rather than read when the
# container starts — which meant the backend's URL was compiled into the
# image, and one image could serve exactly one environment.
#
# ADR 0019 moved that lookup server-side (app/api/chat/route.js reads a
# plain API_URL at request time), so this build no longer needs to know
# anything about where the backend lives. The image is now environment-
# independent: build once, run anywhere, configure at `docker run` /
# platform level — which is what ADR 0015 claimed containers bought and
# this was quietly breaking.
RUN npm run build

FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# [LEARNING] Same non-root goal as the backend Dockerfile, but node:*-slim
# images already ship a built-in `node` user at UID 1000 — creating
# another one at that same UID (as the backend does with `useradd`)
# collides and fails the build (`useradd: UID 1000 is not unique`).
# Reuse the image's own user instead of adding one.

# [LEARNING] "standalone" output (see next.config.mjs) is a self-contained
# server — public/ and .next/static/ are NOT included in it and must be
# copied alongside separately, or static assets 404 at runtime.
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

RUN chown -R node:node /app
USER node

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD node -e "fetch('http://127.0.0.1:3000').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

# [LEARNING] standalone output's entry point is server.js, not `next
# start` — `next start` expects the full node_modules this image
# deliberately doesn't have.
CMD ["node", "server.js"]
