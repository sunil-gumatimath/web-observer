import Link from "next/link";
import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";

const features = [
  {
    title: "Precise change detection",
    body: "Watch a page's content, a site's sitemap links, a product's price, or a list of links with zero drift.",
    eyebrow: "Detect",
  },
  {
    title: "Clear before / after diffs",
    body: "Inspect deterministic text diffs and optional AI summaries so noise stays out of your inbox.",
    eyebrow: "Compare",
  },
  {
    title: "Alerts where you work",
    body: "Email, Slack, Discord, or signed webhooks when something meaningful changes — not every cookie banner.",
    eyebrow: "Alert",
  },
];

const trustBar = ["Product teams", "Founders", "Researchers", "Agencies", "E-commerce", "Compliance"];

export default function HomePage() {
  return (
    <div className="relative min-h-screen bg-[var(--bg)] text-[var(--fg)]" suppressHydrationWarning>
      <header
        className="sticky top-0 z-40 h-14 border-b border-[var(--hairline)] bg-[var(--bg)]/90 backdrop-blur-md"
        suppressHydrationWarning
      >
        <div className="mx-auto flex h-full max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link href="/dashboard" className="flex items-center gap-2.5" aria-label="Web Observer home">
            <Logo iconSize={30} />
          </Link>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <Link
              href="/docs"
              className="btn-linear btn-linear-ghost !px-2.5 !py-1 !text-xs text-[var(--ink-subtle)] hover:text-[var(--fg)]"
              suppressHydrationWarning
            >
              Docs
            </Link>
            <Link
              href="/sign-in"
              className="btn-linear btn-linear-secondary !px-3 !py-1 !text-xs"
              suppressHydrationWarning
            >
              Sign in
            </Link>
            <Link
              href="/sign-up"
              className="btn-linear btn-linear-primary !px-3 !py-1 !text-xs"
              suppressHydrationWarning
            >
              Get started
            </Link>
          </div>
        </div>
      </header>

      <main className="relative z-10 mx-auto max-w-6xl px-4 pb-24 sm:px-6" suppressHydrationWarning>
        <section className="max-w-[840px] pb-16 pt-16 sm:pb-20 sm:pt-20">
          <div suppressHydrationWarning>
            <p className="eyebrow">Web change detection · high-signal alerts</p>
            <h1
              className="mt-4 font-display text-4xl font-semibold leading-[1.08] tracking-[-0.03em] sm:text-5xl lg:text-6xl text-[var(--ink)]"
              suppressHydrationWarning
            >
              Know the moment pages you care about change.
            </h1>
            <p className="lead mt-5 max-w-[52ch] text-base sm:text-lg" suppressHydrationWarning>
              Track public URLs or precise CSS sections, get instant notifications, and review clear
              before-and-after diffs. Built for software engineers, product teams, and researchers.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3" suppressHydrationWarning>
              <Link
                href="/sign-up"
                className="btn-linear btn-linear-primary !px-4 !py-2 !text-sm"
                suppressHydrationWarning
              >
                Create free account
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
              </Link>
              <Link
                href="/sign-in"
                className="btn-linear btn-linear-secondary !px-4 !py-2 !text-sm"
                suppressHydrationWarning
              >
                Sign in
              </Link>
              <Link
                href="/dashboard"
                className="btn-linear btn-linear-ghost !px-3 !py-2 !text-sm text-[var(--ink-subtle)] hover:text-[var(--fg)]"
                suppressHydrationWarning
              >
                Go to dashboard →
              </Link>
            </div>
          </div>
        </section>

        <section className="border-t border-[var(--hairline)] pt-14">
          <p className="eyebrow">Capabilities</p>
          <h2 className="mt-2.5 max-w-[28ch] font-display text-2xl font-semibold tracking-tight text-[var(--ink)] sm:text-3xl">
            Precise monitoring with craft and clarity.
          </h2>
          <div className="mt-8 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {features.map((f) => (
              <article
                key={f.title}
                className="flex flex-col gap-3 rounded-[12px] border border-[var(--hairline)] bg-[var(--surface-1)] p-5 hover:border-[var(--hairline-strong)] hover:bg-[var(--surface-2)]/50 transition"
              >
                <p className="eyebrow">{f.eyebrow}</p>
                <h3 className="font-display text-lg font-medium tracking-tight text-[var(--ink)]">{f.title}</h3>
                <p className="text-xs leading-relaxed text-[var(--ink-subtle)]">{f.body}</p>
                <Link href="/docs" className="mt-auto text-xs text-[var(--primary)] hover:text-[var(--primary-hover)] font-medium">Learn more →</Link>
              </article>
            ))}
          </div>
        </section>

        <section className="mt-16 rounded-[16px] border border-[var(--hairline)] bg-[var(--surface-1)] px-6 py-12 text-center text-[var(--ink)] shadow-2xl sm:px-12 sm:py-16">
          <p className="eyebrow">Enterprise-ready monitoring</p>
          <h2 className="mx-auto mt-2.5 max-w-[24ch] font-display text-2xl font-semibold leading-tight text-[var(--ink)] sm:text-4xl">
            Serious infrastructure for web changes.
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-sm leading-relaxed text-[var(--ink-muted)]">
            Page content · Site links · Product price · List items · Visual diffs · AI impact triage
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-2.5">
            <Link href="/sign-up" className="btn-linear btn-linear-primary !px-4 !py-2 !text-sm">
              Start monitoring
            </Link>
            <Link href="/docs" className="btn-linear btn-linear-secondary !px-4 !py-2 !text-sm">
              Read documentation
            </Link>
          </div>
          <div className="mx-auto mt-8 flex max-w-3xl flex-wrap items-center justify-center gap-x-6 gap-y-2 border-t border-[var(--hairline)] pt-6 text-[11px] uppercase tracking-[0.1em] text-[var(--ink-tertiary)] font-mono">
            {trustBar.map((t) => (
              <span key={t}>{t}</span>
            ))}
          </div>
        </section>
      </main>

      <footer className="relative z-10 mx-auto max-w-6xl px-4 pb-10 sm:px-6" suppressHydrationWarning>
        <div className="flex flex-col gap-4 border-t border-[var(--hairline)] pt-6 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2.5">
            <Logo compact iconSize={22} />
            <span className="text-xs text-[var(--ink-subtle)]">© 2026 Web Observer</span>
          </div>
          <nav className="flex items-center gap-4 text-xs text-[var(--ink-subtle)]" aria-label="Footer">
            <Link href="/docs" className="transition hover:text-[var(--fg)]">
              Docs
            </Link>
            <Link href="/dashboard" className="transition hover:text-[var(--fg)]">
              Dashboard
            </Link>
            <Link href="/sign-in" className="transition hover:text-[var(--fg)]">
              Sign in
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
