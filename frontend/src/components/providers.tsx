"use client";

import { useAuth } from "@clerk/nextjs";
import { useEffect, type ReactNode } from "react";
import { setAuthTokenGetter } from "@/lib/auth-token";
import { config } from "@/lib/config";
import { invalidateWorkspace } from "@/lib/workspace";

/**
 * Bridges Clerk session tokens to the FastAPI client.
 * ClerkProvider is provided by root layout (clerk init).
 *
 * Important: do not return a different tree based on `isLoaded` during render.
 * That causes React hydration mismatches (and browser extensions often make
 * them worse by injecting attributes on the temporary Loading DOM node).
 * API calls already wait for a token in `lib/api.ts`.
 */
function ClerkTokenBridge({ children }: { children: ReactNode }) {
  const { getToken, isLoaded, isSignedIn } = useAuth();

  useEffect(() => {
    if (!isLoaded) return;
    // getAuthToken() also races a timeout; keep this thin.
    setAuthTokenGetter(async () => {
      try {
        return (await getToken()) ?? null;
      } catch {
        return null;
      }
    });
    return () => setAuthTokenGetter(null);
  }, [getToken, isLoaded]);

  useEffect(() => {
    if (isLoaded && !isSignedIn) {
      invalidateWorkspace();
    }
  }, [isLoaded, isSignedIn]);

  return <>{children}</>;
}

export function Providers({ children }: { children: ReactNode }) {
  // Always wrap with the token bridge when Clerk auth is in use (configured, or
  // any non-dev build) so API calls send a Bearer JWT and never the internal token.
  if (config.useClerkAuth) {
    return <ClerkTokenBridge>{children}</ClerkTokenBridge>;
  }
  return <>{children}</>;
}
