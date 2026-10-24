"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { Badge, Button, Card, ModeBadge, SegmentedControl } from "@/components/ui";
import { ReadableContent } from "@/components/readable-content";
import { MarkdownContent } from "@/components/markdown-content";
import { brandAssetUrl, screenshotUrl } from "@/lib/api";
import type { Monitor, MonitorRun, SnapshotAccess } from "@/lib/types";

interface CapturedContentPreviewProps {
  monitor: Monitor;
  snapshot: SnapshotAccess | null;
  run?: MonitorRun | null;
  loading?: boolean;
  onEnableJs?: () => void;
}

export function CapturedContentPreview({
  monitor,
  snapshot,
  run,
  loading,
  onEnableJs,
}: CapturedContentPreviewProps) {
  const [copied, setCopied] = useState<string | null>(null);
  const [filterQuery, setFilterQuery] = useState("");
  const [imgError, setImgError] = useState(false);
  const [readmeView, setReadmeView] = useState<"rendered" | "raw">("rendered");

  const rawText = snapshot?.normalized_text || "";
  const mode = monitor.mode;

  // Hooks must run on every render, before any early return below.
  const lineItems = useMemo(
    () =>
      rawText
        .split("\n")
        .map((l) => l.trim())
        .filter(Boolean)
        .map((l) => (l.startsWith("- ") ? l.slice(2).trim() : l)),
    [rawText],
  );
  const urls = useMemo(
    () => lineItems.filter((l) => /^https?:\/\//i.test(l) || l.startsWith("/")),
    [lineItems],
  );
  const filtered = useMemo(() => {
    if (!filterQuery) return urls;
    const q = filterQuery.toLowerCase();
    return urls.filter((u) => u.toLowerCase().includes(q));
  }, [urls, filterQuery]);

  function copyToClipboard(text: string, label: string = "default") {
    if (!text) return;
    navigator.clipboard?.writeText(text).then(() => {
      setCopied(label);
      setTimeout(() => setCopied(null), 2000);
    });
  }

  if (loading && !snapshot) {
    return (
      <div className="rounded-lg border border-[var(--hairline)] bg-[var(--surface-1)] p-6">
        <div className="flex items-center gap-3">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
          <p className="text-sm text-[var(--ink-subtle)]">Loading captured content…</p>
        </div>
      </div>
    );
  }

  if (!snapshot) {
    return (
      <Card>
        <p className="text-sm text-[var(--ink-subtle)]">
          No text preview available yet. Run a check — preview appears after the first successful run.
        </p>
      </Card>
    );
  }

  // ---------------------------------------------------------------------------
  // 1) VISUAL MODE
  // ---------------------------------------------------------------------------
  if (mode === "visual") {
    const ahash = rawText.match(/ahash:([a-f0-9]+)/i)?.[1];
    const sha256 = rawText.match(/sha256:([a-f0-9]+)/i)?.[1];
    const size = rawText.match(/size:(\d+x\d+)/i)?.[1];

    // Priority 1: presigned/direct raw_download_url
    // Priority 2: public screenshot asset path
    const fallbackAsset = run?.id
      ? screenshotUrl(`screenshots/${monitor.id}/${run.id}.png`)
      : null;
    const resolvedUrl = snapshot.raw_download_url
      ? brandAssetUrl(snapshot.raw_download_url)
      : fallbackAsset;

    return (
      <div className="overflow-hidden rounded-lg border border-[var(--hairline)] bg-[var(--surface-1)]">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--hairline)] bg-[var(--surface-1)] px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--ink)]">
              <svg className="size-4 text-[var(--primary)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <polyline points="21 15 16 10 5 21" />
              </svg>
              Full Visual Capture
            </span>
            {size ? (
              <Badge tone="neutral">{size.replace("x", " × ")} px</Badge>
            ) : null}
            {monitor.css_selector ? (
              <span className="font-mono text-xs text-[var(--ink-subtle)]">
                clip: {monitor.css_selector}
              </span>
            ) : null}
          </div>

          <div className="flex items-center gap-2">
            {resolvedUrl ? (
              <a
                href={resolvedUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 rounded-[6px] border border-[var(--hairline)] bg-[var(--surface-2)] px-2.5 py-1 text-xs font-medium text-[var(--ink)] hover:bg-[var(--surface-3)] transition"
              >
                Open original ↗
              </a>
            ) : null}
            {ahash ? (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => copyToClipboard(ahash, "ahash")}
                className="text-xs"
              >
                {copied === "ahash" ? "✓ Copied aHash" : "Copy aHash"}
              </Button>
            ) : null}
          </div>
        </div>

        {/* Screenshot Viewport */}
        <div className="bg-[var(--surface-2)] p-4 sm:p-6 flex flex-col items-center justify-center min-h-[280px]">
          {resolvedUrl && !imgError ? (
            <div className="relative max-h-[580px] w-full max-w-4xl overflow-auto rounded-lg border border-[var(--hairline)] bg-[var(--canvas)] shadow-xs">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={resolvedUrl}
                alt={`Captured screenshot for ${monitor.name}`}
                className="w-full h-auto object-contain mx-auto block"
                onError={() => setImgError(true)}
              />
            </div>
          ) : (
            <div className="rounded-lg border border-[var(--hairline)] bg-[var(--surface-1)] p-6 text-center max-w-md">
              <p className="text-sm font-medium text-[var(--fg)]">
                Screenshot captured &amp; hashed
              </p>
              <p className="mt-1 text-xs text-[var(--ink-muted)]">
                Perceptual hash computed successfully. In local development without object storage, raw PNG bytes are preserved on the check worker.
              </p>
              {size ? (
                <p className="mt-2 font-mono text-xs text-[var(--ink-subtle)]">
                  Resolution: {size}
                </p>
              ) : null}
            </div>
          )}
        </div>

        {/* Technical Telemetry Footer */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--hairline)] bg-[var(--surface-1)] px-4 py-2.5 text-xs font-mono text-[var(--ink-subtle)]">
          <div className="flex flex-wrap items-center gap-3">
            {ahash ? <span>aHash: <span className="text-[var(--fg)]">{ahash}</span></span> : null}
            {sha256 ? <span>sha256: <span className="text-[var(--fg)]">{sha256.slice(0, 16)}…</span></span> : null}
          </div>
          {snapshot.created_at ? (
            <span>Captured {new Date(snapshot.created_at).toLocaleTimeString()}</span>
          ) : null}
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // 2) PRODUCT PRICE MODE
  // ---------------------------------------------------------------------------
  if (mode === "product_price") {
    const isRemoved = rawText === "[price removed]" || rawText.includes("price_removed");

    return (
      <div className="overflow-hidden rounded-lg border border-[var(--hairline)] bg-[var(--surface-1)]">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--hairline)] bg-[var(--surface-1)] px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--ink)]">
              <svg className="size-4 text-[var(--semantic-success)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="12" y1="1" x2="12" y2="23" />
                <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
              </svg>
              Detected Price
            </span>
            <ModeBadge mode="product_price" />
            {monitor.css_selector ? (
              <span className="rounded bg-[var(--surface-2)] px-2 py-0.5 font-mono text-[11px] text-[var(--ink-subtle)] border border-[var(--hairline)]">
                selector: {monitor.css_selector}
              </span>
            ) : null}
          </div>

          {!isRemoved && rawText ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => copyToClipboard(rawText, "price")}
              className="text-xs"
            >
              {copied === "price" ? "✓ Copied" : "Copy price"}
            </Button>
          ) : null}
        </div>

        {/* Content Body */}
        <div className="p-6">
          {isRemoved ? (
            <div className="rounded-lg border border-[var(--warning)]/30 bg-[var(--warning)]/10 p-5">
              <div className="flex items-start gap-3">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-[var(--warning)]/20 text-sm font-bold text-[var(--warning)]">
                  !
                </span>
                <div>
                  <h4 className="text-sm font-semibold text-[var(--fg)]">
                    Price removed or out of stock
                  </h4>
                  <p className="mt-1 text-xs leading-relaxed text-[var(--ink-muted)]">
                    The price token was not found on the page in the latest check. If the item was discontinued or the site changed layout, check the product page.
                  </p>
                </div>
              </div>
            </div>
          ) : rawText ? (
            <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-4">
              <div>
                <p className="text-xs font-medium uppercase tracking-wider text-[var(--ink-subtle)]">
                  Latest Active Value
                </p>
                <div className="mt-1.5 flex items-baseline gap-2">
                  <span className="text-3xl sm:text-4xl font-extrabold tracking-tight text-[var(--fg)] font-mono">
                    {rawText}
                  </span>
                  <Badge tone="success">detected</Badge>
                </div>
                <p className="mt-2 text-xs text-[var(--ink-muted)]">
                  Extracted via automatic currency normalization
                  {monitor.css_selector ? ` targeting ${monitor.css_selector}` : ""}.
                </p>
              </div>

              {snapshot.created_at ? (
                <div className="text-right sm:self-end text-xs text-[var(--ink-subtle)]">
                  Updated {new Date(snapshot.created_at).toLocaleString()}
                </div>
              ) : null}
            </div>
          ) : (
            <p className="text-sm text-[var(--ink-subtle)]">No price value detected in snapshot.</p>
          )}
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // 3) JSON FIELD MODE
  // ---------------------------------------------------------------------------
  if (mode === "json_field") {
    let formattedJson: string | null = null;
    let isScalar = false;

    try {
      const parsed = JSON.parse(rawText);
      if (typeof parsed === "object" && parsed !== null) {
        formattedJson = JSON.stringify(parsed, null, 2);
      } else {
        isScalar = true;
      }
    } catch {
      isScalar = true;
    }

    return (
      <div className="overflow-hidden rounded-lg border border-[var(--hairline)] bg-[var(--surface-1)]">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--hairline)] bg-[var(--surface-1)] px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--ink)]">
              <svg className="size-4 text-[var(--primary)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="16 18 22 12 16 6" />
                <polyline points="8 6 2 12 8 18" />
              </svg>
              Extracted JSON Field
            </span>
            <ModeBadge mode="json_field" />
            {monitor.css_selector ? (
              <span className="rounded bg-[var(--surface-2)] px-2 py-0.5 font-mono text-[11px] font-medium text-[var(--primary)] border border-[var(--hairline)]">
                query: {monitor.css_selector}
              </span>
            ) : null}
          </div>

          <Button
            size="sm"
            variant="ghost"
            onClick={() => copyToClipboard(formattedJson || rawText, "json")}
            className="text-xs"
          >
            {copied === "json" ? "✓ Copied" : "Copy value"}
          </Button>
        </div>

        {/* Content Body */}
        <div className="p-5">
          {formattedJson ? (
            <div>
              <p className="mb-2 text-xs font-medium text-[var(--ink-subtle)]">
                Structured Result ({formattedJson.split("\n").length} lines)
              </p>
              <pre className="max-h-96 overflow-auto rounded-lg border border-[var(--hairline)] bg-[var(--surface-2)] p-4 font-mono text-xs leading-relaxed text-[var(--fg)]">
                <code>{formattedJson}</code>
              </pre>
            </div>
          ) : isScalar ? (
            <div>
              <p className="text-xs font-medium uppercase tracking-wider text-[var(--ink-subtle)]">
                Resolved Value
              </p>
              <div className="mt-2 rounded-lg border border-[var(--hairline)] bg-[var(--surface-2)] px-4 py-3 font-mono text-lg font-bold text-[var(--fg)] break-all">
                {rawText || "null"}
              </div>
              <p className="mt-2 text-xs text-[var(--ink-muted)]">
                Queried from {monitor.url} using path &ldquo;{monitor.css_selector}&rdquo;.
              </p>
            </div>
          ) : (
            <p className="text-sm text-[var(--ink-subtle)]">Empty JSON field value.</p>
          )}
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // 4) SITE LINKS (SITEMAP INVENTORY) MODE
  // ---------------------------------------------------------------------------
  if (mode === "site_links") {
    return (
      <div className="overflow-hidden rounded-lg border border-[var(--hairline)] bg-[var(--surface-1)]">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--hairline)] bg-[var(--surface-1)] px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--ink)]">
              <svg className="size-4 text-[var(--primary)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
                <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
              </svg>
              Sitemap Inventory
            </span>
            <Badge tone="neutral">{urls.length.toLocaleString()} URLs</Badge>
          </div>

          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => copyToClipboard(urls.join("\n"), "all_urls")}
              className="text-xs"
            >
              {copied === "all_urls" ? "✓ Copied all" : `Copy all (${urls.length})`}
            </Button>
          </div>
        </div>

        {/* Filter Input */}
        {urls.length > 5 ? (
          <div className="border-b border-[var(--hairline)] bg-[var(--surface-2)] px-4 py-2">
            <input
              type="text"
              placeholder={`Filter ${urls.length} URLs…`}
              value={filterQuery}
              onChange={(e) => setFilterQuery(e.target.value)}
              className="w-full rounded-md border border-[var(--hairline)] bg-[var(--surface-1)] px-3 py-1.5 text-xs text-[var(--fg)] placeholder:text-[var(--ink-subtle)] focus:outline-hidden focus:border-[var(--primary)]"
            />
          </div>
        ) : null}

        {/* URL List */}
        <div className="max-h-96 overflow-y-auto divide-y divide-[var(--hairline)]">
          {filtered.length > 0 ? (
            filtered.map((url, idx) => (
              <div
                key={idx}
                className="flex items-center justify-between gap-3 px-4 py-2 hover:bg-[var(--surface-2)] transition"
              >
                <a
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  className="min-w-0 flex-1 truncate font-mono text-xs text-[var(--ink)] hover:text-[var(--primary)]"
                  title={url}
                >
                  {url}
                </a>
                <div className="flex items-center gap-1.5 shrink-0">
                  <a
                    href={url}
                    target="_blank"
                    rel="noreferrer"
                    className="p-1 text-[var(--ink-subtle)] hover:text-[var(--primary)] text-xs"
                    title="Open link"
                  >
                    ↗
                  </a>
                  <button
                    type="button"
                    onClick={() => copyToClipboard(url, `url-${idx}`)}
                    className="p-1 text-[var(--ink-subtle)] hover:text-[var(--ink)] text-xs"
                    title="Copy URL"
                  >
                    {copied === `url-${idx}` ? "✓" : "📋"}
                  </button>
                </div>
              </div>
            ))
          ) : (
            <div className="p-6 text-center text-xs text-[var(--ink-subtle)]">
              {urls.length === 0 ? "No URLs discovered in sitemap." : "No URLs matching filter."}
            </div>
          )}
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // 5) LIST ITEMS MODE
  // ---------------------------------------------------------------------------
  if (mode === "list_items") {
    const rawItems = lineItems;

    return (
      <div className="overflow-hidden rounded-lg border border-[var(--hairline)] bg-[var(--surface-1)]">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--hairline)] bg-[var(--surface-1)] px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--ink)]">
              <svg className="size-4 text-[var(--primary)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="8" y1="6" x2="21" y2="6" />
                <line x1="8" y1="12" x2="21" y2="12" />
                <line x1="8" y1="18" x2="21" y2="18" />
                <line x1="3" y1="6" x2="3.01" y2="6" />
                <line x1="3" y1="12" x2="3.01" y2="12" />
                <line x1="3" y1="18" x2="3.01" y2="18" />
              </svg>
              Matched Elements
            </span>
            <Badge tone="neutral">{rawItems.length} items</Badge>
            {monitor.css_selector ? (
              <span className="rounded bg-[var(--surface-2)] px-2 py-0.5 font-mono text-[11px] text-[var(--ink-subtle)] border border-[var(--hairline)]">
                selector: {monitor.css_selector}
              </span>
            ) : null}
          </div>

          <Button
            size="sm"
            variant="ghost"
            onClick={() => copyToClipboard(rawItems.join("\n"), "list")}
            className="text-xs"
          >
            {copied === "list" ? "✓ Copied" : "Copy items"}
          </Button>
        </div>

        {/* Items List */}
        <div className="p-4">
          {rawItems.length > 0 ? (
            <ReadableContent
              text={rawText}
              maxChars={25000}
              baseUrl={monitor.url}
            />
          ) : (
            <div className="p-4 text-center text-xs text-[var(--ink-subtle)]">
              No items matched selector &ldquo;{monitor.css_selector}&rdquo;.
            </div>
          )}
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // 6) RSS FEED MODE
  // ---------------------------------------------------------------------------
  if (mode === "rss_feed") {
    const feedItems = lineItems;

    return (
      <div className="overflow-hidden rounded-lg border border-[var(--hairline)] bg-[var(--surface-1)]">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--hairline)] bg-[var(--surface-1)] px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--ink)]">
              <svg className="size-4 text-[var(--warning)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 11a9 9 0 0 1 9 9" />
                <path d="M4 4a16 16 0 0 1 16 16" />
                <circle cx="5" cy="19" r="1" />
              </svg>
              Feed Entries
            </span>
            <Badge tone="neutral">{feedItems.length} entries</Badge>
          </div>

          <Button
            size="sm"
            variant="ghost"
            onClick={() => copyToClipboard(rawItemsToString(feedItems), "rss")}
            className="text-xs"
          >
            {copied === "rss" ? "✓ Copied" : "Copy feed"}
          </Button>
        </div>

        <div className="p-4">
          <ReadableContent
            text={rawText}
            maxChars={25000}
            baseUrl={monitor.url}
          />
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // 7) README MODE
  // ---------------------------------------------------------------------------
  if (mode === "readme") {
    return (
      <div className="overflow-hidden rounded-lg border border-[var(--hairline)] bg-[var(--surface-1)]">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--hairline)] bg-[var(--surface-1)] px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--ink)]">
              <svg className="size-4 text-[var(--ink)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22" />
              </svg>
              GitHub README.md
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <SegmentedControl<"rendered" | "raw">
              ariaLabel="README view mode"
              value={readmeView}
              onChange={setReadmeView}
              options={[
                { value: "rendered", label: "Rendered" },
                { value: "raw", label: "Raw markdown" },
              ]}
            />
            <Button
              size="sm"
              variant="ghost"
              onClick={() => copyToClipboard(rawText, "readme")}
              className="text-xs"
            >
              {copied === "readme" ? "✓ Copied" : "Copy markdown"}
            </Button>
          </div>
        </div>

        <div className="max-h-[min(75vh,42rem)] overflow-y-auto px-6 py-5">
          {readmeView === "raw" ? (
            <pre className="whitespace-pre-wrap break-words rounded-lg border border-[var(--hairline)] bg-[var(--surface-2)] p-4 font-mono text-xs leading-relaxed text-[var(--ink-muted)]">
              {rawText}
            </pre>
          ) : (
            <MarkdownContent text={rawText} baseUrl={monitor.url} />
          )}
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // 8) SECURITY SCAN (CLOUDFLARE URL SCANNER)
  // ---------------------------------------------------------------------------
  if (mode === "security_scan") {
    const isMalicious = lineItems.some(
      (l) => l.toLowerCase() === "malicious=true" || l.toLowerCase() === "malicious: true",
    );
    const techStack = lineItems
      .filter((l) => l.startsWith("tech="))
      .map((l) => l.slice(5).trim())
      .filter(Boolean);
    const certs = lineItems
      .filter((l) => l.startsWith("certificate="))
      .map((l) => l.slice(12).trim())
      .filter(Boolean);
    const asns = lineItems
      .filter((l) => l.startsWith("asn="))
      .map((l) => l.slice(4).trim())
      .filter(Boolean);
    const categories = lineItems
      .find((l) => l.startsWith("categories="))
      ?.slice(11)
      .split(",")
      .map((c) => c.trim())
      .filter(Boolean);

    return (
      <div className="overflow-hidden rounded-lg border border-[var(--hairline)] bg-[var(--surface-1)]">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--hairline)] bg-[var(--surface-1)] px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--ink)]">
              <svg className="size-4 text-[var(--primary)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
              Cloudflare Security Scan
            </span>
            <ModeBadge mode="security_scan" />
            <Badge tone={isMalicious ? "danger" : "success"}>
              {isMalicious ? "Malicious Detected" : "Clean Verdict"}
            </Badge>
          </div>

          <Button
            size="sm"
            variant="ghost"
            onClick={() => copyToClipboard(rawText, "security_scan")}
            className="text-xs"
          >
            {copied === "security_scan" ? "✓ Copied" : "Copy scan facts"}
          </Button>
        </div>

        {/* Content Body */}
        <div className="p-5 space-y-4">
          {/* Tech Stack */}
          {techStack.length > 0 ? (
            <div>
              <p className="text-xs font-medium uppercase tracking-wider text-[var(--ink-subtle)] mb-2">
                Detected Technologies ({techStack.length})
              </p>
              <div className="flex flex-wrap gap-1.5">
                {techStack.map((tech, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center rounded-md border border-[var(--hairline)] bg-[var(--surface-2)] px-2.5 py-1 font-mono text-xs text-[var(--ink)]"
                  >
                    {tech}
                  </span>
                ))}
              </div>
            </div>
          ) : null}

          {/* Certificates */}
          {certs.length > 0 ? (
            <div>
              <p className="text-xs font-medium uppercase tracking-wider text-[var(--ink-subtle)] mb-2">
                SSL / TLS Certificates
              </p>
              <div className="space-y-1.5">
                {certs.map((cert, idx) => (
                  <div
                    key={idx}
                    className="rounded-md border border-[var(--hairline)] bg-[var(--surface-2)] px-3 py-1.5 font-mono text-xs text-[var(--ink)]"
                  >
                    🔒 {cert}
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {/* Network ASNs & Categories */}
          <div className="flex flex-wrap items-center gap-4 text-xs text-[var(--ink-muted)]">
            {asns.length > 0 ? (
              <span>ASN: <span className="font-mono text-[var(--fg)]">{asns.join(", ")}</span></span>
            ) : null}
            {categories && categories.length > 0 ? (
              <span>Categories: <span className="text-[var(--fg)]">{categories.join(", ")}</span></span>
            ) : null}
          </div>

          {/* Raw Facts Fallback/Detail */}
          <div className="pt-2 border-t border-[var(--hairline)]">
            <details className="text-xs group">
              <summary className="cursor-pointer font-medium text-[var(--ink-subtle)] hover:text-[var(--ink)] select-none">
                Raw Scan Facts ({lineItems.length} lines)
              </summary>
              <pre className="mt-2 max-h-60 overflow-auto rounded-lg border border-[var(--hairline)] bg-[var(--surface-2)] p-3 font-mono text-xs leading-relaxed text-[var(--ink-muted)]">
                {rawText}
              </pre>
            </details>
          </div>
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------------------
  // 9) PAGE CONTENT (DEFAULT)
  // ---------------------------------------------------------------------------
  const showJsWarning =
    mode === "page_content" &&
    !monitor.js_required &&
    (rawText.length < 80 ||
      /loading\b|enable javascript|requires javascript|please wait/i.test(rawText));

  return (
    <div>
      {showJsWarning ? (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--warning)]/30 bg-[var(--warning)]/10 p-3.5 text-xs text-[var(--ink)]">
          <p className="leading-relaxed">
            <strong>Note:</strong> This website may require client-side JavaScript to render its full content. If text looks incomplete, enable <em>JavaScript rendering (Playwright)</em>.
          </p>
          {onEnableJs ? (
            <Button
              size="sm"
              variant="secondary"
              onClick={onEnableJs}
              className="shrink-0 text-xs"
            >
              Enable JS rendering
            </Button>
          ) : (
            <Link href={`/monitors/${monitor.id}/edit`}>
              <Button size="sm" variant="secondary" className="shrink-0 text-xs">
                Enable JS rendering
              </Button>
            </Link>
          )}
        </div>
      ) : null}

      {rawText.length > 0 ? (
        <ReadableContent
          text={rawText}
          maxChars={25000}
          baseUrl={monitor.url}
        />
      ) : (
        <Card>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-[var(--ink-subtle)]">
              Captured snapshot is empty — page had no extractable text. If this is a Single-Page App (SPA) or client-rendered site, enable JavaScript rendering.
            </p>
            {!monitor.js_required ? (
              onEnableJs ? (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={onEnableJs}
                  className="shrink-0 text-xs"
                >
                  Enable JS rendering
                </Button>
              ) : (
                <Link href={`/monitors/${monitor.id}/edit`}>
                  <Button size="sm" variant="secondary" className="shrink-0 text-xs">
                    Enable JS rendering
                  </Button>
                </Link>
              )
            ) : null}
          </div>
        </Card>
      )}
    </div>
  );
}

function rawItemsToString(items: string[]): string {
  return items.join("\n");
}
