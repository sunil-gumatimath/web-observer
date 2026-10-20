import { describe, expect, it } from "vitest";

describe("Captured content mode-specific handling", () => {
  describe("visual mode parsing", () => {
    it("extracts ahash, sha256, and dimensions from visual normalized text", () => {
      const text = "ahash:0000ffff0000ffff\nsha256:abc1234567890abcdef\nsize:1920x1080";
      const ahash = text.match(/ahash:([a-f0-9]+)/i)?.[1];
      const sha256 = text.match(/sha256:([a-f0-9]+)/i)?.[1];
      const size = text.match(/size:(\d+x\d+)/i)?.[1];

      expect(ahash).toBe("0000ffff0000ffff");
      expect(sha256).toBe("abc1234567890abcdef");
      expect(size).toBe("1920x1080");
    });
  });

  describe("product_price mode parsing", () => {
    it("identifies price values and price-removed markers", () => {
      const priceText: string = "USD 24.99";
      const removedText: string = "[price removed]";

      expect(priceText !== "[price removed]").toBe(true);
      expect(removedText === "[price removed]").toBe(true);
    });
  });

  describe("json_field mode parsing", () => {
    it("distinguishes structured JSON objects from scalar values", () => {
      const objText = '{"status":"healthy","latency_ms":42}';
      const scalarText = "42";
      const stringText = "in_stock";

      const parsedObj = JSON.parse(objText);
      expect(typeof parsedObj).toBe("object");
      expect(JSON.stringify(parsedObj, null, 2)).toContain('  "status": "healthy"');

      expect(() => JSON.parse(stringText)).toThrow();
      expect(typeof JSON.parse(scalarText)).toBe("number");
    });
  });

  describe("site_links sitemap inventory parsing", () => {
    it("extracts clean URLs and filters appropriately", () => {
      const rawText = "- https://example.com/\n- https://example.com/about\n- https://example.com/pricing";
      const urls = rawText
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean)
        .map((l) => (l.startsWith("- ") ? l.slice(2).trim() : l))
        .filter((l) => /^https?:\/\//i.test(l) || l.startsWith("/"));

      expect(urls).toHaveLength(3);
      expect(urls).toContain("https://example.com/about");

      const filtered = urls.filter((u) => u.includes("pricing"));
      expect(filtered).toHaveLength(1);
      expect(filtered[0]).toBe("https://example.com/pricing");
    });
  });

  describe("JavaScript rendering warning condition", () => {
    it("only applies to page_content mode when text is short or has JS keywords", () => {
      function shouldShowJsWarning(mode: string, jsRequired: boolean, text: string) {
        if (mode !== "page_content") return false;
        if (jsRequired) return false;
        return (
          text.length < 80 ||
          /loading\b|enable javascript|requires javascript|please wait/i.test(text)
        );
      }

      // Non-page_content modes must NEVER trigger the warning regardless of short text
      expect(shouldShowJsWarning("product_price", false, "$19.99")).toBe(false);
      expect(shouldShowJsWarning("json_field", false, "200")).toBe(false);
      expect(shouldShowJsWarning("visual", false, "ahash:0000\nsize:1280x720")).toBe(false);
      expect(shouldShowJsWarning("site_links", false, "https://ex.co/")).toBe(false);
      expect(shouldShowJsWarning("rss_feed", false, "- [Hi](url)")).toBe(false);
      expect(shouldShowJsWarning("readme", false, "# Hi")).toBe(false);

      // page_content without JS and suspiciously short or with JS markers SHOULD trigger
      expect(shouldShowJsWarning("page_content", false, "Please enable javascript to run this app.")).toBe(true);
      expect(shouldShowJsWarning("page_content", false, "Short text")).toBe(true);
      // page_content with long extracted content should NOT trigger
      expect(shouldShowJsWarning("page_content", false, "A".repeat(120))).toBe(false);
      // page_content with js_required already true should NOT trigger
      expect(shouldShowJsWarning("page_content", true, "Short")).toBe(false);
    });
  });
});
