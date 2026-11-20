# syntax=docker/dockerfile:1
#
# Single all-in-one image for the whole Web Observer stack:
#
#   * Next.js frontend          :3000
#   * FastAPI API               :8002
#   * Dramatiq worker (http)    (background)
#   * Dramatiq worker (browser) (background)
#   * Scheduler                 (background)
#   * Redis                     (127.0.0.1:6379, inside the container)
#
# All six processes are supervised by supervisord, so one `docker run` brings
# the stack up. Postgres is NOT included: DATABASE_URL in backend/.env points at
# a managed Neon database.

########## 1. Frontend build #################################################
FROM node:22-bookworm-slim AS frontend-build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

# NEXT_PUBLIC_* values are inlined into the client bundle at build time.
ARG NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8002
ARG NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=
ARG NEXT_PUBLIC_CF_BEACON_TOKEN=
ARG NEXT_PUBLIC_SCREENSHOT_CDN_URL=
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL \
    NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY \
    NEXT_PUBLIC_CF_BEACON_TOKEN=$NEXT_PUBLIC_CF_BEACON_TOKEN \
    NEXT_PUBLIC_SCREENSHOT_CDN_URL=$NEXT_PUBLIC_SCREENSHOT_CDN_URL

RUN npm run build

########## 2. Frontend runtime dependencies ##################################
FROM node:22-bookworm-slim AS frontend-deps
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --omit=dev

########## 3. Runtime ########################################################
FROM python:3.12-slim-bookworm

# Keep this block identical to the previous backend image so the expensive
# pip + Chromium layers stay cached across rebuilds.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Playwright ships its own Node binary, which links against libatomic. The slim
# image does not include it, and `playwright install --with-deps` cannot run
# before it is present.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libatomic1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Chromium plus the OS libraries it needs. Versions always match the
# `playwright` wheel installed above, so no separate pinning is required.
RUN python -m playwright install --with-deps chromium

# Process supervision, the bundled Redis and a health probe client.
RUN apt-get update \
    && apt-get install -y --no-install-recommends redis-server supervisor curl \
    && rm -rf /var/lib/apt/lists/*

# Node.js 22 runtime for the Next.js server. Copied from the official image so
# the version matches the one that produced the build above.
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production \
    REDIS_URL=redis://127.0.0.1:6379/0

# Backend source
COPY backend/ ./backend/

# Frontend runtime
WORKDIR /app/frontend
COPY --from=frontend-deps /app/node_modules ./node_modules
COPY --from=frontend-build /app/.next ./.next
COPY --from=frontend-build /app/public ./public
COPY --from=frontend-build /app/package.json ./package.json
COPY --from=frontend-build /app/next.config.ts ./next.config.ts

# Supervision
COPY docker/supervisord.conf /etc/supervisor/conf.d/web-observer.conf
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
COPY docker/wait-for-redis.sh /usr/local/bin/wait-for-redis.sh
RUN chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/wait-for-redis.sh

# Redis persistence lives here.
VOLUME ["/data"]

EXPOSE 3000 8002

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8002/health >/dev/null \
        && curl -fsS -o /dev/null http://127.0.0.1:3000/ \
        || exit 1

CMD ["/usr/local/bin/entrypoint.sh"]
