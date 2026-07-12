"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { type ReactNode, useEffect, useState } from "react";
import { Button, Card, Spinner } from "@/components/ui";
import { config } from "@/lib/config";

/**
 * Prevents app pages from spinning forever when Clerk never finishes or the
 * user is signed out. Data loaders only mount after a session is ready.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { isLoaded, isSignedIn } = useAuth();
  const [waitedTooLong, setWaitedTooLong] = useState(false);

  useEffect(() => {
    if (!config.clerkEnabled || isLoaded) return;
    const t = setTimeout(() => setWaitedTooLong(true), 12_000);
    return () => clearTimeout(t);
  }, [isLoaded]);

  // Dev mode without Clerk: pages use X-Internal-Token
  if (!config.clerkEnabled) {
    return <>{children}</>;
  }

  if (!isLoaded) {
    if (waitedTooLong) {
      return (
        <Card className="mx-auto max-w-lg p-6">
          <h1 className="text-lg font-semibold text-slate-900 dark:text-white">
            Sign-in is taking too long
          </h1>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
            Clerk did not finish loading a session. Check your network, disable blockers for{" "}
            <code className="text-xs">clerk.accounts.dev</code>, then retry.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Link href="/sign-in">
              <Button type="button">Go to sign in</Button>
            </Link>
            <Button type="button" variant="secondary" onClick={() => window.location.reload()}>
              Reload page
            </Button>
          </div>
        </Card>
      );
    }
    return <Spinner label="Checking session…" />;
  }

  if (!isSignedIn) {
    return (
      <Card className="mx-auto max-w-lg p-6">
        <h1 className="text-lg font-semibold text-slate-900 dark:text-white">Sign in required</h1>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
          You need a Clerk session to load workspaces and monitors. API calls cannot use the
          internal token while Clerk is enabled.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Link href="/sign-in">
            <Button type="button">Sign in</Button>
          </Link>
          <Link href="/sign-up">
            <Button type="button" variant="secondary">
              Create account
            </Button>
          </Link>
        </div>
      </Card>
    );
  }

  return <>{children}</>;
}
