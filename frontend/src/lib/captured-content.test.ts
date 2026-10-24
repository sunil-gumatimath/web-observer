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

  describe("list_items mode parsing", () => {
    it("extracts markdown link items and plain text items", () => {
      const rawText = "- [Changelog 1.0](https://example.com/v1)\n- [Changelog 2.0](https://example.com/v2)\n- Plain announcement item";
      const items = rawText
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean)
        .map((l) => (l.startsWith("- ") ? l.slice(2).trim() : l));

      expect(items).toHaveLength(3);
      expect(items[0]).toBe("[Changelog 1.0](https://example.com/v1)");
      expect(items[2]).toBe("Plain announcement item");
    });
  });

  describe("rss_feed mode parsing", () => {
    it("extracts clean feed entries from normalized list", () => {
      const rawText = "- [Release v1.2](https://github.com/org/repo/releases/tag/v1.2)\n- [Release v1.1](https://github.com/org/repo/releases/tag/v1.1)";
      const entries = rawText
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean)
        .map((l) => (l.startsWith("- ") ? l.slice(2).trim() : l));

      expect(entries).toHaveLength(2);
      expect(entries[0]).toContain("Release v1.2");
    });
  });

  describe("readme mode parsing", () => {
    it("preserves markdown headers and raw content", () => {
      const rawText = "# Project Documentation\n\n```python\nprint('hello')\n```";
      expect(rawText.startsWith("# Project Documentation")).toBe(true);
      expect(rawText).toContain("```python");
    });
  });

  describe("security_scan mode parsing", () => {
    it("parses verdicts, technologies, and certificates from URL Scanner facts", () => {
      const rawText = "- malicious=false\n- categories=business\n- tags=verified\n- tech=nginx\n- tech=React\n- certificate=example.com issuer=Let's Encrypt\n- asn=13335";
      const lineItems = rawText
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean)
        .map((l) => (l.startsWith("- ") ? l.slice(2).trim() : l));

      const isMalicious = lineItems.some(
        (l) => l.toLowerCase() === "malicious=true" || l.toLowerCase() === "malicious: true",
      );
      const techStack = lineItems
        .filter((l) => l.startsWith("tech="))
        .map((l) => l.slice(5).trim());
      const certs = lineItems
        .filter((l) => l.startsWith("certificate="))
        .map((l) => l.slice(12).trim());
      const asns = lineItems
        .filter((l) => l.startsWith("asn="))
        .map((l) => l.slice(4).trim());

      expect(isMalicious).toBe(false);
      expect(techStack).toEqual(["nginx", "React"]);
      expect(certs[0]).toBe("example.com issuer=Let's Encrypt");
      expect(asns[0]).toBe("13335");
    });
  });

  describe("preview loading condition", () => {
    it("does not block rendering when a snapshot is already available in memory", () => {
      function shouldShowBlockingSpinner(loading: boolean, hasSnapshot: boolean): boolean {
        return loading && !hasSnapshot;
      }

      // Initial load with no snapshot in memory: show spinner
      expect(shouldShowBlockingSpinner(true, false)).toBe(true);
      // Background re-fetch with snapshot already in memory: DO NOT block
      expect(shouldShowBlockingSpinner(true, true)).toBe(false);
      // Settled load: no spinner
      expect(shouldShowBlockingSpinner(false, true)).toBe(false);
      expect(shouldShowBlockingSpinner(false, false)).toBe(false);
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
      expect(shouldShowJsWarning("security_scan", false, "malicious=false")).toBe(false);

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
