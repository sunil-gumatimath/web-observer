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

const GRADIENTS = [
  "from-neutral-800 to-black",
  "from-[#1863dc] to-[#4c6ee6]",
  "from-neutral-500 to-neutral-700",
  "from-[#17171c] to-[#34343c]",
  "from-neutral-900 to-neutral-600",
];

function gradientFor(key: string): string {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return GRADIENTS[h % GRADIENTS.length];
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
          `shrink-0 rounded-lg border border-[var(--border)] bg-white object-contain p-0.5 dark:bg-slate-900 ` +
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
        `inline-flex shrink-0 items-center justify-center rounded-lg bg-gradient-to-br text-[11px] font-bold text-white shadow-sm ` +
        gradientFor(domain || name) +
        " " +
        (className ?? "")
      }
    >
      {initials(name)}
    </span>
  );
}
