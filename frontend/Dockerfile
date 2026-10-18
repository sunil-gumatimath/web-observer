# Web Observer frontend (Next.js 16) run with Bun.
#
# This is a DEVELOPMENT-mode image on purpose. The app's internal-token auth
# mode (frontend/.env.local with no Clerk publishable key) is gated on
# NODE_ENV !== "production" (src/lib/config.ts, src/proxy.ts), so a production
# build fails closed with "@clerk/nextjs: Missing publishableKey" on every
# route. Running `next dev` keeps that local workflow working inside Docker.
#
# `next build` is deliberately omitted: it would only produce output that
# `next dev` discards. For production-style deploys switch to a build/start
# image and supply Clerk keys.
FROM oven/bun:1

WORKDIR /app

# Install exact locked dependency versions first for layer caching.
# Dev dependencies are required here (tailwind/postcss run at compile time).
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

# Full source (includes .env.local, which Next reads at startup in dev mode).
COPY . .

# Keep the internal-token dev path active inside the container.
ENV NODE_ENV=development

EXPOSE 3000

CMD ["bun", "run", "dev", "--port", "3000"]
