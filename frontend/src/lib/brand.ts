import { brandAssetUrl } from "@/lib/api";
import type { MonitorBrand } from "@/lib/types";

/**
 * Best available image for a monitor's hero banner.
 *
 * Some pages (e.g. Hacker News) publish a logo but no og:image/twitter:image.
 * Falling back to the logo keeps the preview useful instead of showing a dead
 * "No product preview image" placeholder.
 */
export function brandPreviewUrl(brand: MonitorBrand | null | undefined): string | null {
  const hero = brandAssetUrl(brand?.hero_path) || brand?.hero_url;
  if (hero) return hero;
  return brandAssetUrl(brand?.logo_path) || brand?.logo_url || null;
}