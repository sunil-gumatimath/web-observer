"use client";

import { useMemo, useState } from "react";
import { brandAssetUrl } from "@/lib/api";
import type { MonitorBrand } from "@/lib/types";

function initials(name: string): string {
  const t = name.trim();
  if (!t) return "W";
  const parts = t.split(/\s+/).slice(0, 2);
  if (parts.length === 1) return parts[0][0]!.toUpperCase();
  return (parts[0][0]! + parts[1][0]!).toUpperCase();
}

/**
 * Last-resort brand mark: the site's favicon via Google's favicon service.
 * The `domain` prop usually holds a full monitor URL, so parse the hostname
 * defensively. Returns null when no usable host exists.
 */
function faviconFor(domain?: string): string | null {
  if (!domain) return null;
  try {
    const host = new URL(domain.includes("://") ? domain : `https://${domain}`)
      .hostname;
    if (!host) return null;
    return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=64`;
  } catch {
    return null;
  }
}

export function BrandLogo({
  brand,
  name,
  domain,
  size = 28,
  className,
}: {
  brand?: MonitorBrand | null;
  name: string;
  domain?: string;
  size?: number;
  className?: string;
}) {
  const primary = brandAssetUrl(brand?.logo_path);
  const fallback = brand?.logo_url || null;
  const favicon = faviconFor(domain);
  const [errStep, setErrStep] = useState(0);
  // 0 -> re-hosted logo, 1 -> origin logo_url, 2 -> domain favicon, 3 -> avatar
  const sources = useMemo(
    () => [primary, fallback, favicon].filter((s): s is string => !!s),
    [primary, fallback, favicon],
  );
  const src = errStep < sources.length ? sources[errStep]! : null;

  if (src) {
    return (
      <img
        src={src}
        alt=""
        width={size}
        height={size}
        onError={() => setErrStep((s) => s + 1)}
        className={
          `shrink-0 rounded-[8px] border border-[var(--hairline)] bg-[var(--surface-1)] object-contain p-0.5 ` +
          (className ?? "")
        }
        style={{ width: size, height: size }}
        loading="lazy"
        referrerPolicy="no-referrer"
      />
    );
  }

  return (
    <span
      aria-hidden
      style={{ width: size, height: size }}
      className={
        `inline-flex shrink-0 items-center justify-center rounded-[8px] border border-[var(--hairline)] bg-[var(--surface-2)] text-[11px] font-medium text-[var(--ink)] select-none ` +
        (className ?? "")
      }
    >
      {initials(name)}
    </span>
  );
}
