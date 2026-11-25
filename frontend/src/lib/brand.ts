import { brandAssetUrl } from "@/lib/api";
import type { MonitorBrand, MonitorMode } from "@/lib/types";

/** Normalize a monitor URL input for pre-save brand-info lookup (including GitHub shorthands). */
export function normalizeBrandLookupUrl(
  input: string,
  mode?: MonitorMode,
): string | null {
  const trimmed = input.trim();
  if (!trimmed) return null;
  if (mode === "readme") {
    if (/^[\w.\-]+\/[\w.\-]+$/.test(trimmed)) {
      return `https://github.com/${trimmed}`;
    }
    if (/^github\.com\/[\w.\-]+\/[\w.\-]+/i.test(trimmed)) {
      return `https://${trimmed}`;
    }
    if (/^https?:\/\/(www\.)?github\.com\/[\w.\-]+\/[\w.\-]+/i.test(trimmed)) {
      return trimmed;
    }
    return null;
  }
  const candidate = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
  if (candidate.length < 8 || !candidate.includes(".")) return null;
  return candidate;
}

/** A live preview older than this is re-captured when the monitor page opens. */
export const LIVE_PREVIEW_MAX_AGE_MS = 60 * 60 * 1000;

export type BrandPreviewKind = "hero" | "live";

const DEAD_LOGO_HOSTS = ["logo.clearbit.com"];

/** Filter out known-defunct external logo providers left in legacy monitor records. */
export function sanitizeExternalBrandUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  const trimmed = url.trim();
  if (!trimmed) return null;
  try {
    const host = new URL(trimmed).hostname.toLowerCase();
    if (DEAD_LOGO_HOSTS.some((dead) => host === dead || host.endsWith(`.${dead}`))) {
      return null;
    }
  } catch {
    return null;
  }
  return trimmed;
}

export function livePreviewUrl(brand: MonitorBrand | null | undefined): string | null {
  const url = brandAssetUrl(brand?.preview_path);
  if (!url) return null;
  // The object key is stable across captures; version the URL so browsers and
  // CDNs fetch the new screenshot instead of serving the cached one.
  return brand?.preview_at ? `${url}?v=${encodeURIComponent(brand.preview_at)}` : url;
}

/** The site's own social/brand image (og:image) — the best brand preview. */
export function brandHeroUrl(brand: MonitorBrand | null | undefined): string | null {
  const rehosted = brandAssetUrl(brand?.hero_path);
  if (rehosted) return rehosted;
  // Never prefer an un-rehosted upstream hero_url over our own captured screenshot.
  if (brand?.preview_path) return null;
  return brand?.hero_url || null;
}

/** The brand mark (shown in the header, never used as the banner preview). */
export function brandLogoUrl(brand: MonitorBrand | null | undefined): string | null {
  return brandAssetUrl(brand?.logo_path) || sanitizeExternalBrandUrl(brand?.logo_url) || null;
}

/** True once brand discovery has produced anything usable for this monitor. */
export function hasBrandData(brand: MonitorBrand | null | undefined): boolean {
  return Boolean(
    brand &&
      (brand.title ||
        brand.logo_path ||
        sanitizeExternalBrandUrl(brand.logo_url) ||
        brand.hero_path ||
        brand.hero_url ||
        brand.preview_path),
  );
}

/**
 * True when an existing monitor's brand record has stale/broken legacy fields
 * (e.g. dead Clearbit logo, un-rehosted hero_url, or pre-fallback feed/sitemap
 * without title/hero) and should be refreshed in the background.
 */
export function needsBrandRefresh(
  brand: MonitorBrand | null | undefined,
  mode?: MonitorMode,
): boolean {
  if (!hasBrandData(brand)) return true;
  if (brand?.logo_url && !sanitizeExternalBrandUrl(brand.logo_url)) return true;
  if (brand?.hero_url && !brand.hero_path) return true;
  if ((mode === "site_links" || mode === "rss_feed") && !brand?.title && !brand?.hero_path) {
    return true;
  }
  return false;
}

/** Which kind of image `brandPreviewUrl` resolves to (hero > live). */
export function brandPreviewKind(
  brand: MonitorBrand | null | undefined,
): BrandPreviewKind | null {
  if (brandHeroUrl(brand)) return "hero";
  if (livePreviewUrl(brand)) return "live";
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
 * screenshot of the page. A logo is never used as the banner; sites with no
 * hero or screenshot get a brand card (title + hostname) instead.
 */
export function brandPreviewUrl(brand: MonitorBrand | null | undefined): string | null {
  const hero = brandHeroUrl(brand);
  if (hero) return hero;
  const live = livePreviewUrl(brand);
  if (live) return live;
  return null;
}
