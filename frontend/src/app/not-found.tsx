import Link from "next/link";

export default function NotFound() {
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center gap-6 overflow-hidden px-4 py-12 text-center">
      <div className="pointer-events-none absolute inset-0 hero-grid" />
      <div className="relative z-10">
        <p className="section-label">404</p>
        <h1 className="mt-2 text-2xl font-semibold text-[var(--text)]">
          Page not found
        </h1>
        <p className="mx-auto mt-2 max-w-md text-sm text-[var(--muted)]">
          The page you’re looking for doesn’t exist or may have moved.
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <Link
            href="/dashboard"
            className="rounded-xl bg-gradient-to-b from-sky-500 to-sky-600 px-6 py-3 text-sm font-semibold text-white shadow-glow transition hover:from-sky-400 hover:to-sky-500"
          >
            Go to dashboard
          </Link>
          <Link
            href="/"
            className="rounded-xl border border-[var(--border)] bg-[var(--bg-elevated)]/60 px-6 py-3 text-sm font-semibold text-[var(--text)] backdrop-blur transition hover:bg-[var(--bg-elevated)]"
          >
            Back home
          </Link>
        </div>
      </div>
    </div>
  );
}
