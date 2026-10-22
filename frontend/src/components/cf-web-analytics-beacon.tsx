"use client";

import Script from "next/script";

/**
 * Cloudflare Web Analytics beacon — free, cookie-less, no individual-visitor
 * tracking (see docs/guides/cloudflare-free-features.md §3).
 *
 * Renders nothing when no beacon token is configured, so the app makes zero
 * analytics calls until the token is set. Loads after interaction to stay out
 * of the app's own critical path, matching the defer-first spirit of the
 * official snippet.
 */
export function CfWebAnalyticsBeacon({ token }: { token: string }) {
  if (!token) return null;
  return (
    <Script
      id="cf-web-analytics-beacon"
      src="https://static.cloudflareinsights.com/beacon.min.js"
      data-cf-beacon={JSON.stringify({ token })}
      strategy="lazyOnload"
    />
  );
}
