"use client";

import { useEffect } from "react";
import Link from "next/link";
import { Button } from "@/components/ui";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Surface the error to your observability provider if you have one.
    console.error(error);
  }, [error]);

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center gap-6 overflow-hidden px-4 py-12 text-center">
      <div className="pointer-events-none absolute inset-0 hero-grid" />
      <div className="relative z-10">
        <p className="eyebrow">Something went wrong</p>
        <h1 className="mt-2 font-display text-3xl text-[var(--fg)]">
          This page hit an error
        </h1>
        <p className="mx-auto mt-2 max-w-md text-sm text-[var(--muted)]">
          The issue has been logged. You can retry, or head back to your monitors.
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <Button type="button" onClick={reset}>
            Try again
          </Button>
          <Link
            href="/dashboard"
            className="btn-cohere btn-cohere-ghost"
          >
            Go to dashboard
          </Link>
        </div>
      </div>
    </div>
  );
}
