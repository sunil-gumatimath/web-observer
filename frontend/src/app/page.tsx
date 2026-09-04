import Link from "next/link";
import { Logo } from "@/components/logo";
import { ThemeToggle } from "@/components/theme-toggle";

const features = [
  {
    title: "Precise change detection",
    body: "Watch a page's content, a site's sitemap links, a product's price, or a list of links.",
    eyebrow: "Detect",
  },
  {
    title: "Clear before / after diffs",
    body: "Inspect deterministic text diffs and optional AI summaries so noise stays out of your inbox.",
    eyebrow: "Compare",
  },
  {
    title: "Alerts where you work",
    body: "Email, Slack, or Discord when something meaningful changes — not every cookie banner.",
    eyebrow: "Alert",
  },
];

const trustBar = ["Product teams", "Founders", "Researchers", "Agencies", "E-commerce", "Compliance"];

export default function HomePage() {
  // suppressHydrationWarning: browser extensions (e.g. Retriever) inject attrs
  // like `rtrvr-ls` into the DOM before React hydrates — not an app bug.
  return (
    <div className="relative min-h-screen bg-[var(--bg)] text-[var(--fg)]" suppressHydrationWarning>
      <header
        className="relative z-10 mx-auto flex max-w-[1440px] items-center justify-between px-8 py-5"
        suppressHydrationWarning
      >
        <Link href="/dashboard" className="flex items-center gap-2.5" aria-label="Web Observer home">
          <Logo iconSize={36} />
        </Link>
        <div className="flex items-center gap-1">
          <ThemeToggle />
          <Link
            href="/docs"
            className="btn-cohere btn-cohere-ghost !px-3 !py-1.5 !text-sm"
            suppressHydrationWarning
          >
            Docs
          </Link>
          <Link
            href="/sign-in"
            className="btn-cohere btn-cohere-ghost !px-3 !py-1.5 !text-sm"
            suppressHydrationWarning
          >
            Sign in
          </Link>
          <Link
            href="/sign-up"
            className="btn-cohere btn-cohere-primary !px-[18px] !py-2.5 !text-sm"
            suppressHydrationWarning
          >
            Get started
          </Link>
        </div>
      </header>

      <main className="relative z-10 mx-auto max-w-[1440px] px-8 pb-24" suppressHydrationWarning>
        <section className="grid gap-12 pt-[60px] lg:grid-cols-[1.4fr_1fr] lg:items-end">
          <div suppressHydrationWarning>
            <p className="eyebrow">Web change detection · high-signal alerts</p>
            <h1
              className="mt-4 font-display text-[48px] leading-[1.0] tracking-[-0.02em] sm:text-[60px] lg:text-[72px]"
              suppressHydrationWarning
            >
              Know the moment pages you care about change.
            </h1>
            <p className="lead mt-6 max-w-[52ch]" suppressHydrationWarning>
              Track public URLs or precise sections, get email and webhook alerts, and review clear
              before-and-after diffs. Built for product teams, founders, and researchers.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3" suppressHydrationWarning>
              <Link
                href="/sign-up"
                className="btn-cohere btn-cohere-primary"
                suppressHydrationWarning
              >
                Create free account
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
              </Link>
              <Link
                href="/sign-in"
                className="btn-cohere btn-cohere-ghost"
                suppressHydrationWarning
              >
                Sign in
              </Link>
              <Link
                href="/dashboard"
                className="btn-cohere btn-cohere-ghost !text-sm"
                suppressHydrationWarning
              >
                Go to dashboard →
              </Link>
            </div>
          </div>
          <aside className="rounded-[22px] border border-[var(--border-soft)] bg-[var(--surface)] p-4" aria-label="System status">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm text-[var(--muted)]">Platform status</span>
              <span className="inline-flex items-center gap-2 rounded-full px-2.5 py-1 text-xs font-medium text-emerald-700 dark:text-emerald-300">
                <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
                Operational
              </span>
            </div>
            <p className="mt-3 text-sm text-[var(--muted)]">Deterministic diffs · AI summaries · ⌘K search</p>
            <p className="mt-1 text-xs text-[var(--muted)]">Press <kbd>⌘</kbd> <kbd>K</kbd> anywhere in the app.</p>
          </aside>
        </section>

        <section className="border-t border-[var(--border-soft)] pt-[60px]">
          <p className="eyebrow">What this does</p>
          <h2 className="mt-3 max-w-[28ch] text-[32px] font-normal leading-[1.2] tracking-[-0.01em]">
            Precise monitoring with enterprise clarity.
          </h2>
          <div className="mt-8 grid gap-5 md:grid-cols-2 lg:grid-cols-3">
            {features.map((f) => (
              <article
                key={f.title}
                className="flex flex-col gap-3 rounded-[22px] border border-[var(--border-soft)] bg-[var(--bg)] p-6"
              >
                <p className="eyebrow">{f.eyebrow}</p>
                <h3 className="text-2xl font-normal leading-[1.3]">{f.title}</h3>
                <p className="text-sm leading-relaxed text-[var(--muted)]">{f.body}</p>
                <Link href="/docs" className="mt-auto text-sm">Learn more →</Link>
              </article>
            ))}
          </div>
        </section>

        <section className="mt-[60px] rounded-[22px] bg-[#17171c] px-8 py-14 text-center text-white dark:border dark:border-[var(--border)]">
          <p className="font-mono text-sm uppercase tracking-[0.028em] text-neutral-400">Enterprise-ready monitoring</p>
          <h2 className="mx-auto mt-3 max-w-[24ch] font-display text-[32px] leading-[1.1] sm:text-[60px]">
            Serious infrastructure for page changes.
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-[18px] leading-[1.4] text-neutral-400">
            Page content · Site links · Product price · List items
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Link href="/sign-up" className="inline-flex items-center gap-2 rounded-full bg-white px-[18px] py-2.5 text-base text-black hover:bg-neutral-200">
              Start monitoring
            </Link>
            <Link href="/docs" className="inline-flex items-center gap-2 rounded-full px-[18px] py-2.5 text-base text-white hover:text-[#6b9bff]">
              Read docs
            </Link>
          </div>
          <div className="mx-auto mt-10 flex max-w-3xl flex-wrap items-center justify-center gap-x-6 gap-y-2 border-t border-white/10 pt-6 text-xs uppercase tracking-[0.14em] text-neutral-500">
            {trustBar.map((t) => (
              <span key={t}>{t}</span>
            ))}
          </div>
          <p className="mt-6 text-xs text-neutral-500">
            Auth powered by Clerk. After sign-in you land on the dashboard.
          </p>
        </section>
      </main>
    </div>
  );
}
