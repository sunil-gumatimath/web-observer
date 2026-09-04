import Link from "next/link";

export default function NotFound() {
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center gap-6 overflow-hidden px-4 py-12 text-center">
      <div className="pointer-events-none absolute inset-0 hero-grid" />
      <div className="relative z-10">
        <p className="eyebrow">404</p>
        <h1 className="mt-2 font-display text-3xl text-[var(--fg)]">
          Page not found
        </h1>
        <p className="mx-auto mt-2 max-w-md text-sm text-[var(--muted)]">
          The page you’re looking for doesn’t exist or may have moved.
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
          <Link
            href="/dashboard"
            className="btn-cohere btn-cohere-primary"
          >
            Go to dashboard
          </Link>
          <Link
            href="/"
            className="btn-cohere btn-cohere-ghost"
          >
            Back home
          </Link>
        </div>
      </div>
    </div>
  );
}
