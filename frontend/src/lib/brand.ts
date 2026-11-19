import { brandAssetUrl } from "@/lib/api";
import type { MonitorBrand } from "@/lib/types";

/** A live preview older than this is re-captured when the monitor page opens. */
export const LIVE_PREVIEW_MAX_AGE_MS = 60 * 60 * 1000;

export type BrandPreviewKind = "live" | "hero" | "logo";

function livePreviewUrl(brand: MonitorBrand | null | undefined): string | null {
  const url = brandAssetUrl(brand?.preview_path);
  if (!url) return null;
  // The object key is stable across captures; version the URL so browsers and
  // CDNs fetch the new screenshot instead of serving the cached one.
  return brand?.preview_at ? `${url}?v=${encodeURIComponent(brand.preview_at)}` : url;
}

/** Which kind of image `brandPreviewUrl` resolves to (live > hero > logo). */
export function brandPreviewKind(
  brand: MonitorBrand | null | undefined,
): BrandPreviewKind | null {
  if (livePreviewUrl(brand)) return "live";
  if (brandAssetUrl(brand?.hero_path) || brand?.hero_url) return "hero";
  if (brandAssetUrl(brand?.logo_path) || brand?.logo_url) return "logo";
  return null;
}

/** True when there is no live preview yet, or it is older than `maxAgeMs`. */
export function isLivePreviewStale(
  brand: MonitorBrand | null | undefined,
  now: number = Date.now(),
  maxAgeMs: number = LIVE_PREVIEW_MAX_AGE_MS,
): boolean {
  if (!brand?.preview_path || !brand.preview_at) return true;
  const at = Date.parse(brand.preview_at);
  return Number.isNaN(at) || now - at > maxAgeMs;
}

/**
 * Best available image for a monitor's hero banner.
 *
 * Prefers a live screenshot of the page itself (works for any site), then the
 * page's og:image hero, then its logo.
 *
 * Some pages (e.g. Hacker News) publish a logo but no og:image/twitter:image.
 * Falling back to the logo keeps the preview useful instead of showing a dead
 * "No product preview image" placeholder.
 */
export function brandPreviewUrl(brand: MonitorBrand | null | undefined): string | null {
  const live = livePreviewUrl(brand);
  if (live) return live;
  const hero = brandAssetUrl(brand?.hero_path) || brand?.hero_url;
  if (hero) return hero;
  return brandAssetUrl(brand?.logo_path) || brand?.logo_url || null;
}
