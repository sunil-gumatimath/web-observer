import { describe, expect, it } from "vitest";

import {
  brandHeroUrl,
  brandPreviewKind,
  brandPreviewUrl,
  hasBrandData,
  isLivePreviewStale,
  needsBrandRefresh,
  normalizeBrandLookupUrl,
  sanitizeExternalBrandUrl,
} from "@/lib/brand";
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

  it("does not use the logo as a preview when a page has no hero image", () => {
    const brand: MonitorBrand = {
      hero_path: null,
      hero_url: null,
      logo_path: "brand-assets/a/logo.svg",
      logo_url: "https://example.com/logo.svg",
    };
    expect(brandPreviewUrl(brand)).toBeNull();
  });

  it("does not use an external logo URL as a preview", () => {
    const brand: MonitorBrand = {
      logo_path: null,
      logo_url: "https://example.com/logo.png",
    };
    expect(brandPreviewUrl(brand)).toBeNull();
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

  it("classifies hero and non-preview brands", () => {
    expect(brandPreviewKind({ hero_url: "https://example.com/h.png" })).toBe("hero");
    expect(brandPreviewKind({ logo_url: "https://example.com/l.png" })).toBeNull();
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

  it("detects whether brand discovery produced anything", () => {
    expect(hasBrandData(null)).toBe(false);
    expect(hasBrandData({})).toBe(false);
    expect(hasBrandData({ title: null, logo_url: null, hero_url: null })).toBe(false);
    expect(hasBrandData({ title: "Example" })).toBe(true);
    expect(hasBrandData({ logo_url: "https://example.com/l.png" })).toBe(true);
    expect(hasBrandData({ preview_path: "brand-assets/a/preview.png" })).toBe(true);
  });

  it("returns null when there is no preview asset at all", () => {
    expect(brandPreviewUrl(null)).toBeNull();
    expect(brandPreviewUrl({})).toBeNull();
  });

  it("normalizes GitHub shorthands and URLs for brand lookup", () => {
    expect(normalizeBrandLookupUrl("vercel/next.js", "readme")).toBe(
      "https://github.com/vercel/next.js",
    );
    expect(normalizeBrandLookupUrl("github.com/vercel/next.js", "readme")).toBe(
      "https://github.com/vercel/next.js",
    );
    expect(normalizeBrandLookupUrl("https://github.com/vercel/next.js", "readme")).toBe(
      "https://github.com/vercel/next.js",
    );
    expect(normalizeBrandLookupUrl("invalid", "readme")).toBeNull();
    expect(normalizeBrandLookupUrl("example.com/pricing", "page_content")).toBe(
      "https://example.com/pricing",
    );
    expect(normalizeBrandLookupUrl("abc", "page_content")).toBeNull();
  });

  it("prefers live preview over un-rehosted hero_url when hero_path is missing", () => {
    const brand: MonitorBrand = {
      hero_path: null,
      hero_url: "https://upload.wikimedia.org/403.png",
      preview_path: "brand-assets/w/preview.png",
      preview_at: "2026-01-01T00:00:00Z",
    };
    expect(brandHeroUrl(brand)).toBeNull();
    expect(brandPreviewUrl(brand)).toContain("brand-assets/w/preview.png");
    expect(brandPreviewKind(brand)).toBe("live");
  });

  it("filters defunct Clearbit logo URLs and flags stale brands for refresh", () => {
    expect(sanitizeExternalBrandUrl("https://logo.clearbit.com/example.com?size=256")).toBeNull();
    expect(sanitizeExternalBrandUrl("https://example.com/favicon.ico")).toBe(
      "https://example.com/favicon.ico",
    );

    expect(
      needsBrandRefresh({
        title: "Example Domain",
        logo_url: "https://logo.clearbit.com/example.com?size=256",
        logo_path: null,
      }),
    ).toBe(true);
    expect(
      needsBrandRefresh({
        title: "Wikipedia",
        hero_url: "https://upload.wikimedia.org/403.png",
        hero_path: null,
      }),
    ).toBe(true);
    expect(
      needsBrandRefresh({ logo_path: "brand-assets/a/logo.png" }, "site_links"),
    ).toBe(true);
    expect(
      needsBrandRefresh({
        title: "Healthy",
        logo_path: "brand-assets/a/logo.png",
        hero_path: "brand-assets/a/hero.png",
        hero_url: "https://example.com/hero.png",
      }),
    ).toBe(false);
  });
});