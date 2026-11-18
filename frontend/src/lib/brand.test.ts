import { describe, expect, it } from "vitest";

import { brandPreviewUrl } from "@/lib/brand";
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

  it("returns null when there is no preview asset at all", () => {
    expect(brandPreviewUrl(null)).toBeNull();
    expect(brandPreviewUrl({})).toBeNull();
  });
});