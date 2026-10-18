# Web Observer frontend (Next.js 16) built with Bun.
# NEXT_PUBLIC_* variables are baked into the client bundle at build time,
# so .env.local must be present during the build stage.
FROM oven/bun:1 AS build

WORKDIR /app

# Install exact locked dependency versions first for layer caching.
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

# Full source (includes .env.local, which Next reads during build).
COPY . .

RUN bunx --bun next build

EXPOSE 3000

CMD ["bun", "run", "start", "--port", "3000"]
