"use client";

import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import { cn } from "@/components/ui";

/**
 * Light/dark theme toggle. Presentation only — no app logic.
 * All theme-dependent output is gated behind `mounted` so the server
 * and the client's first render produce identical markup (no hydration
 * mismatch). `next-themes` sets `resolvedTheme` from the inline script
 * before React hydrates, which would otherwise diverge from the server
 * (where it is undefined).
 */
export function ThemeToggle({ className }: { className?: string }) {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const isDark = mounted && resolvedTheme === "dark";

  return (
    <button
      type="button"
      aria-label="Toggle color theme"
      title={mounted ? (isDark ? "Switch to light mode" : "Switch to dark mode") : "Toggle color theme"}
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className={cn(
        "inline-flex h-9 w-9 items-center justify-center rounded-lg border transition",
        "border-[var(--border)] text-[var(--text)] hover:bg-[var(--nav-active-bg)]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]",
        className,
      )}
    >
      {mounted ? (
        isDark ? (
          /* Sun icon — shown in dark mode to switch to light */
          <svg
            className="h-[18px] w-[18px]"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={1.75}
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
          </svg>
        ) : (
          /* Moon icon — shown in light mode to switch to dark */
          <svg
            className="h-[18px] w-[18px]"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={1.75}
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
          </svg>
        )
      ) : (
        <span className="h-[18px] w-[18px]" />
      )}
    </button>
  );
}
