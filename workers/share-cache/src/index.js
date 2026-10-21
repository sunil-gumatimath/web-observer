/**
 * Cloudflare Worker edge cache for Web Observer share pages (Phase 6).
 *
 * Complements the Zone-level Cache Rules (Phase 2) with *control*: explicit
 * cache key scope, on-change cache warming, and TTL trimming before the edge
 * cache sees the response. Deployed standalone today (workers.dev); wire the
 * `routes` in wrangler.toml when this project has a public hostname again.
 *
 * Free-tier Worker limits (100k req/day, 10 ms CPU) are far beyond what a
 * read-only cache interceptor needs.
 */
const CACHEABLE_PREFIXES = ["/share/", "/_next/static/"];

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // When routed via a custom domain (see wrangler.toml), only cache the
    // public, read-only paths of that host. On workers.dev everything is
    // public, so all paths pass the scope check.
    const hostOk =
      url.hostname === env.CACHE_HOST ||
      url.hostname.includes("workers.dev") ||
      !env.CACHE_HOST;
    const cacheable =
      hostOk && CACHEABLE_PREFIXES.some((p) => url.pathname.startsWith(p));
    if (!cacheable) return fetch(request);

    const cache = caches.default;
    let res = await cache.match(request);
    if (res) return res;

    res = await fetch(request); // origin = the tunnel / deployed app
    if (res.status === 200) {
      const cacheRes = res.clone();
      cacheRes.headers.append("Cache-Control", "public, max-age=300");
      ctx.waitUntil(cache.put(request, cacheRes));
    }
    return res;
  },
};
