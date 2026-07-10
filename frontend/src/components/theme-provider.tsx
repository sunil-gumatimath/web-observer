"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ReactNode } from "react";

/**
 * Class-based light/dark theme provider.
 * Applies `class="dark"` on <html>; respects OS preference by default,
 * persisted in localStorage under the `theme` key. No app logic changes.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
      storageKey="theme"
    >
      {children}
    </NextThemesProvider>
  );
}
