/**
 * Cloudflare Browser Rendering failover for Web Observer (Phase 7).
 *
 * Free-tier edge Chromium used ONLY as a failover: the backend runs local
 * Playwright as primary and calls this Worker when a local browser fetch
 * actually failed. Free quota is ~10 min of browser time per UTC day, so
 * never wire this as the primary path.
 *
 * Contract:
 *   POST / JSON  { url, timeout_ms? }
 *   Header       X-CF-Failover-Token: <SHARED_TOKEN secret binding>
 *   200 -> { status_code, final_url, html }
 *   4xx/5xx -> { error }
 * The caller enforces SSRF validation on `url` and on `final_url`, size caps,
 * and bot-challenge detection after the response arrives.
 */
const SECRET_HEADER = "X-CF-Failover-Token";

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return Response.json({ error: "method not allowed" }, { status: 405 });
    }
    if ((request.headers.get(SECRET_HEADER) || "") !== (env.SHARED_TOKEN || "")) {
      return Response.json({ error: "unauthorized" }, { status: 401 });
    }
    let body;
    try {
      body = await request.json();
    } catch {
      return Response.json({ error: "invalid json" }, { status: 400 });
    }
    const url = String(body.url || "");
    // Workers free tier browser timeout is 60s; stay under it.
    const timeoutMs = Math.min(Math.max(Number(body.timeout_ms) || 30000, 5000), 55000);
    let parsed;
    try {
      parsed = new URL(url);
    } catch {
      return Response.json({ error: "invalid url" }, { status: 400 });
    }
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return Response.json({ error: "unsupported scheme" }, { status: 400 });
    }
    let browser;
    try {
      browser = await env.BROWSER.launch();
      const page = await browser.newPage();
      try {
        const resp = await page.goto(parsed.toString(), {
          waitUntil: "networkidle",
          timeout: timeoutMs,
        });
        const html = await page.content();
        return Response.json({
          status_code: resp ? resp.status : 200,
          final_url: page.url(),
          html: html,
        });
      } finally {
        await page.close().catch(() => {});
      }
    } catch (err) {
      const message = err && err.message ? err.message : String(err);
      return Response.json({ error: message }, { status: 502 });
    } finally {
      if (browser) {
        await browser.close().catch(() => {});
      }
    }
  },
};
