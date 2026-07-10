"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, type ReactNode } from "react";
import { setAuthTokenGetter } from "@/lib/auth-token";
import { config } from "@/lib/config";

/**
 * Bridges Clerk session tokens to the FastAPI client.
 * ClerkProvider is provided by root layout (clerk init).
 */
function ClerkTokenBridge({ children }: { children: ReactNode }) {
  const { getToken, isLoaded } = useAuth();

  useEffect(() => {
    if (!isLoaded) return;
    setAuthTokenGetter(async () => {
      try {
        return await getToken();
      } catch {
        return null;
      }
    });
    return () => setAuthTokenGetter(null);
  }, [getToken, isLoaded]);

  return <>{children}</>;
}

export function Providers({ children }: { children: ReactNode }) {
  // Always wrap with token bridge when Clerk keys exist so API calls send Bearer JWT
  if (config.clerkEnabled) {
    return <ClerkTokenBridge>{children}</ClerkTokenBridge>;
  }
  return <>{children}</>;
}
