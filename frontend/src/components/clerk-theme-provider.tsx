"use client";

import { ClerkProvider } from "@clerk/nextjs";
import { useTheme } from "next-themes";
import { useSyncExternalStore, type ReactNode } from "react";
import { clerkAppearance } from "@/lib/clerk-appearance";

export function ThemedClerkProvider({ children }: { children: ReactNode }) {
  const { resolvedTheme } = useTheme();
  const mounted = useSyncExternalStore(
    () => () => undefined,
    () => true,
    () => false,
  );
  const isDark = mounted && resolvedTheme === "dark";
  return (
    <ClerkProvider
      signInUrl="/sign-in"
      signUpUrl="/sign-up"
      signInFallbackRedirectUrl="/dashboard"
      signUpFallbackRedirectUrl="/dashboard"
      afterSignOutUrl="/"
      appearance={clerkAppearance(isDark)}
    >
      {children}
    </ClerkProvider>
  );
}
