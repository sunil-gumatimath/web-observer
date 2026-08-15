"use client";

import { useSyncExternalStore } from "react";
import { useTheme } from "next-themes";
import { cn } from "@/components/ui";

/**
 * Three-state theme toggle: light → dark → system (cycles).
 * Presentation only — no app logic. `next-themes` persists the chosen
 * value to localStorage under the `theme` key and re-applies it before
 * React hydrates, so the selection survives reloads.
 *
 * - `theme` is the *stored* value ("light" | "dark" | "system").
 * - `resolvedTheme` is the *effective* value after system resolution
 *   ("light" | "dark"), used to pick the icon.
 *
 * All output is gated behind `mounted` so the server and the client's
 * first render produce identical markup (no hydration mismatch).
 */
export function ThemeToggle({ className }: { className?: string }) {
  const { theme, setTheme } = useTheme();
  const mounted = useSyncExternalStore(
    () => () => undefined,
    () => true,
    () => false,
  );

  // The currently stored choice (before mount we don't know it yet).
  const current = mounted ? (theme ?? "system") : "system";

  // Icon reflects the effective appearance; clicking advances the cycle.
  const icon =
    current === "system" ? (
      // Monitor / system icon — explicit "follow OS" choice
      <svg
        className="h-[18px] w-[18px]"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={1.75}
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <rect x="2.5" y="4" width="19" height="13" rx="2" />
        <path d="M8 21h8M12 17v4" />
      </svg>
    ) : current === "dark" ? (
      // Sun icon — shown in dark mode to advance to system
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
      // Moon icon — shown in light mode to advance to dark
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
    );

  const title =
    current === "system"
      ? "Following system theme — click for light"
      : current === "dark"
        ? "Dark mode — click for system"
        : "Light mode — click for dark";

  return (
    <button
      type="button"
      aria-label="Toggle color theme"
      title={mounted ? title : "Toggle color theme"}
      onClick={() =>
        setTheme(current === "light" ? "dark" : current === "dark" ? "system" : "light")
      }
      className={cn(
        "inline-flex h-9 w-9 items-center justify-center rounded-lg border transition",
        "border-[var(--border)] text-[var(--text)] hover:bg-[var(--nav-active-bg)]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]",
        className,
      )}
    >
      {mounted ? icon : <span className="h-[18px] w-[18px]" />}
    </button>
  );
}
