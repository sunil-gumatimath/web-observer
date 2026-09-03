"use client";

import { ToastProvider } from "@/components/toasts";
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
  const inner = config.clerkEnabled ? (
    <ClerkTokenBridge>{children}</ClerkTokenBridge>
  ) : (
    <>{children}</>
  );
  // Toasts are global — mounted once so any page can call useToast().
  return <ToastProvider>{inner}</ToastProvider>;
}
