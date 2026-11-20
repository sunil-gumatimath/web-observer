import { describe, expect, it } from "vitest";

import { brandPreviewKind, brandPreviewUrl, isLivePreviewStale } from "@/lib/brand";
import type { MonitorBrand } from "@/lib/types";

describe("brandPreviewUrl", () => {
  it("prefers the re-hosted hero image", () => {
    const brand: MonitorBrand = {
      hero_path: "brand-assets/a/hero.png",
      hero_url: "https://example.com/fallback.png",
      logo_path: "brand-assets/a/logo.svg",
    };
    expect(brandPreviewUrl(brand)).toContain("brand-assets/a/hero.png");
  });

  it("falls back to the logo when a page has no hero image", () => {
    const brand: MonitorBrand = {
      hero_path: null,
      hero_url: null,
      logo_path: "brand-assets/a/logo.svg",
      logo_url: "https://example.com/logo.svg",
    };
    expect(brandPreviewUrl(brand)).toContain("brand-assets/a/logo.svg");
  });

  it("uses the external logo URL when there is no re-hosted logo", () => {
    const brand: MonitorBrand = {
      logo_path: null,
      logo_url: "https://example.com/logo.png",
    };
    expect(brandPreviewUrl(brand)).toBe("https://example.com/logo.png");
  });

  it("prefers the site's og:image hero over a live screenshot, and versions the screenshot URL by capture time", () => {
    const brand: MonitorBrand = {
      preview_path: "brand-assets/a/preview.png",
      preview_at: "2026-01-01T00:00:00+00:00",
      hero_path: "brand-assets/a/hero.png",
      logo_path: "brand-assets/a/logo.svg",
    };
    const url = brandPreviewUrl(brand);
    expect(url).toContain("brand-assets/a/hero.png");
    expect(brandPreviewKind(brand)).toBe("hero");
    // Without a hero, the live screenshot wins and is cache-busted by capture time.
    const noHero = { ...brand, hero_path: null };
    expect(brandPreviewUrl(noHero)).toContain("brand-assets/a/preview.png?v=");
    expect(brandPreviewUrl(noHero)).toContain(encodeURIComponent("2026-01-01T00:00:00+00:00"));
    expect(brandPreviewKind(noHero)).toBe("live");
  });

  it("classifies hero, logo and empty brands", () => {
    expect(brandPreviewKind({ hero_url: "https://example.com/h.png" })).toBe("hero");
    expect(brandPreviewKind({ logo_url: "https://example.com/l.png" })).toBe("logo");
    expect(brandPreviewKind(null)).toBeNull();
  });

  it("treats a missing or old live preview as stale", () => {
    const now = Date.parse("2026-01-01T12:00:00Z");
    expect(isLivePreviewStale(null, now)).toBe(true);
    expect(isLivePreviewStale({ preview_path: "brand-assets/a/preview.png" }, now)).toBe(true);
    const fresh = { preview_path: "k", preview_at: "2026-01-01T11:30:00Z" };
    const old = { preview_path: "k", preview_at: "2026-01-01T09:00:00Z" };
    expect(isLivePreviewStale(fresh, now)).toBe(false);
    expect(isLivePreviewStale(old, now)).toBe(true);
  });

  it("returns null when there is no preview asset at all", () => {
    expect(brandPreviewUrl(null)).toBeNull();
    expect(brandPreviewUrl({})).toBeNull();
  });
});