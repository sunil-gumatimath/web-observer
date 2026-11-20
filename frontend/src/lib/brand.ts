import { brandAssetUrl } from "@/lib/api";
import type { MonitorBrand } from "@/lib/types";

/** A live preview older than this is re-captured when the monitor page opens. */
export const LIVE_PREVIEW_MAX_AGE_MS = 60 * 60 * 1000;

export type BrandPreviewKind = "live" | "hero" | "logo";

export function livePreviewUrl(brand: MonitorBrand | null | undefined): string | null {
  const url = brandAssetUrl(brand?.preview_path);
  if (!url) return null;
  // The object key is stable across captures; version the URL so browsers and
  // CDNs fetch the new screenshot instead of serving the cached one.
  return brand?.preview_at ? `${url}?v=${encodeURIComponent(brand.preview_at)}` : url;
}

/** The site's own social/brand image (og:image) — the best brand preview. */
export function brandHeroUrl(brand: MonitorBrand | null | undefined): string | null {
  return brandAssetUrl(brand?.hero_path) || brand?.hero_url || null;
}

/** The brand mark, used for the fallback brand card when there is no hero. */
export function brandLogoUrl(brand: MonitorBrand | null | undefined): string | null {
  return brandAssetUrl(brand?.logo_path) || brand?.logo_url || null;
}

/** Which kind of image `brandPreviewUrl` resolves to (hero > live > logo). */
export function brandPreviewKind(
  brand: MonitorBrand | null | undefined,
): BrandPreviewKind | null {
  if (brandHeroUrl(brand)) return "hero";
  if (livePreviewUrl(brand)) return "live";
  if (brandLogoUrl(brand)) return "logo";
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
 * Prefers the page's own og:image (a real brand/social image), then a live
 * screenshot of the page, then the logo. Sites that publish no og:image (e.g.
 * Hacker News) still get a useful banner from the screenshot or logo.
 */
export function brandPreviewUrl(brand: MonitorBrand | null | undefined): string | null {
  const hero = brandHeroUrl(brand);
  if (hero) return hero;
  const live = livePreviewUrl(brand);
  if (live) return live;
  return brandLogoUrl(brand);
}
