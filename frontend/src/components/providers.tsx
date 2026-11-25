"use client";

import { ToastProvider } from "@/components/toasts";
import { useAuth } from "@clerk/nextjs";
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import { getClerkUserId, setAuthTokenGetter, setClerkUserId } from "@/lib/auth-token";
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
  const { getToken, isLoaded, isSignedIn, userId } = useAuth();
  const prevUserIdRef = useRef<string | null>(null);
  const [sessionGeneration, setSessionGeneration] = useState(0);

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
    if (!isLoaded) return;
    if (!isSignedIn || !userId) {
      const hadUser = prevUserIdRef.current !== null || getClerkUserId() !== null;
      prevUserIdRef.current = null;
      invalidateWorkspace();
      // invalidateWorkspace() already clears it, but make the sign-out path
      // explicit here so a future change to that helper cannot regress it.
      setClerkUserId(null);
      if (hadUser) {
        setSessionGeneration((g) => g + 1);
      }
      return;
    }

    const tracked = getClerkUserId();
    const switchedUser =
      (prevUserIdRef.current !== null && prevUserIdRef.current !== userId) ||
      (tracked !== null && tracked !== userId);
    prevUserIdRef.current = userId;
    if (switchedUser) {
      invalidateWorkspace();
      setClerkUserId(userId);
      setSessionGeneration((g) => g + 1);
    } else {
      setClerkUserId(userId);
    }
  }, [isLoaded, isSignedIn, userId]);

  return <Fragment key={sessionGeneration}>{children}</Fragment>;
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
