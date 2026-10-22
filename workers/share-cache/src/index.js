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

    // Only cache when routed via the configured public hostname. An unset or
    // empty CACHE_HOST disables caching entirely (fail closed) — never cache
    // everything on workers.dev just because no host is configured.
    const hostOk = !!env.CACHE_HOST && url.hostname === env.CACHE_HOST;
    const cacheable =
      hostOk && CACHEABLE_PREFIXES.some((p) => url.pathname.startsWith(p));
    if (!cacheable) return fetch(request);

    const cache = caches.default;
    let res = await cache.match(request);
    if (res) return res;

    res = await fetch(request); // origin = the tunnel / deployed app
    if (res.status === 200) {
      // Never cache a response that sets cookies (e.g. the Clerk session
      // cookie): the edge would hand one visitor's Set-Cookie to everyone.
      if (res.headers.get("set-cookie")) return res;
      // Headers on a fetch() response are immutable, so build a mutable copy
      // for the cache entry. .set() replaces any origin Cache-Control instead
      // of appending a malformed second value.
      const cacheRes = new Response(res.clone().body, res);
      cacheRes.headers.set("Cache-Control", "public, max-age=300");
      ctx.waitUntil(cache.put(request, cacheRes));
    }
    return res;
  },
};
