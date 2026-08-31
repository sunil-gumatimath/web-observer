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
  "from-sky-500 to-indigo-500",
  "from-emerald-500 to-teal-500",
  "from-amber-500 to-orange-500",
  "from-violet-500 to-fuchsia-500",
  "from-rose-500 to-pink-500",
];

function gradientFor(key: string): string {
  let h = 0;
  for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
  return GRADIENTS[h % GRADIENTS.length];
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
  const [errStep, setErrStep] = useState(0);
  // 0 -> primary, 1 -> fallback, 2 -> avatar
  const src = useMemo(() => {
    if (errStep === 0 && primary) return primary;
    if (errStep <= 1 && fallback) return fallback;
    return null;
  }, [errStep, primary, fallback]);

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
