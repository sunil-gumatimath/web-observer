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
        <p className="section-label">Something went wrong</p>
        <h1 className="mt-2 text-2xl font-semibold text-[var(--text)]">
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
            className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)]/60 px-6 py-3 text-sm font-semibold text-[var(--text)] backdrop-blur transition hover:bg-[var(--bg-elevated)]"
          >
            Go to dashboard
          </Link>
        </div>
      </div>
    </div>
  );
}
