import Link from "next/link";
import { Logo } from "@/components/logo";

const features = [
  {
    title: "Precise change detection",
    body: "Nine modes — page content, sitemap links, product prices, JSON payloads, RSS feeds, READMEs, visual diffs and security scans — with zero drift.",
    eyebrow: "Detect",
  },
  {
    title: "Clear before / after diffs",
    body: "Inspect deterministic text diffs and AI summaries with noise triaged away before it hits your inbox.",
    eyebrow: "Compare",
  },
  {
    title: "Alerts where you work",
    body: "Email, Slack, Discord, plus signed HMAC webhooks for your own automation, when something meaningful changes — not on every cookie banner.",
    eyebrow: "Alert",
  },
];

const trustBar = [
  "Software Engineers",
  "Product Teams",
  "Founders",
  "Security Teams",
  "Compliance",
  "E-Commerce",
];

export default function HomePage() {
  return (
    <div
      className="relative min-h-screen bg-[#010102] text-[#f7f8f8] selection:bg-[#5e6ad2]/25 selection:text-white"
      suppressHydrationWarning
    >
      {/* Top Nav: 56px height, #010102 background, hairline border */}
      <header
        className="sticky top-0 z-40 h-14 border-b border-[#23252a] bg-[#010102]/95 backdrop-blur-md"
        suppressHydrationWarning
      >
        <div className="mx-auto flex h-full max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link href="/dashboard" className="flex items-center gap-2.5" aria-label="Web Observer home">
            <Logo iconSize={30} />
          </Link>
          <div className="flex items-center gap-2">
            <Link
              href="/docs"
              className="btn-linear btn-linear-ghost !px-2.5 !py-1 !text-xs text-[#8a8f98] hover:text-[#f7f8f8]"
              suppressHydrationWarning
            >
              Docs
            </Link>
            <Link
              href="/sign-in"
              className="btn-linear btn-linear-secondary !px-2.5 !py-1 !text-xs"
              suppressHydrationWarning
            >
              Sign in
            </Link>
            <Link
              href="/sign-up"
              className="btn-linear btn-linear-primary !px-2.5 !py-1 !text-xs"
              suppressHydrationWarning
            >
              Get started
            </Link>
          </div>
        </div>
      </header>

      <main className="relative z-10 mx-auto max-w-6xl px-4 pb-24 sm:px-6" suppressHydrationWarning>
        {/* Hero Section */}
        <section className="pb-12 pt-16 sm:pb-16 sm:pt-20">
          <div className="max-w-[840px]" suppressHydrationWarning>
            <p className="eyebrow text-[#8a8f98]">Web change detection · high-signal alerts</p>
            <h1
              className="mt-4 font-display text-4xl font-semibold leading-[1.05] tracking-[-1.5px] sm:text-6xl sm:tracking-[-2.2px] lg:text-[76px] lg:tracking-[-3.0px] text-[#f7f8f8]"
              suppressHydrationWarning
            >
              Know the moment pages you care about change.
            </h1>
            <p className="mt-5 max-w-[54ch] text-base leading-[1.5] tracking-[-0.05px] text-[#d0d6e0] sm:text-lg sm:tracking-[-0.1px]" suppressHydrationWarning>
              Track public URLs or CSS selectors, get notified as soon as a change is detected, and review clear
              before-and-after diffs. Built for engineers, analysts, and product teams.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3" suppressHydrationWarning>
              <Link
                href="/sign-up"
                className="btn-linear btn-linear-primary !px-4 !py-2.5"
                suppressHydrationWarning
              >
                Create free account
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>
              </Link>
              <Link
                href="/sign-in"
                className="btn-linear btn-linear-secondary !px-4 !py-2.5"
                suppressHydrationWarning
              >
                Sign in
              </Link>
              <Link
                href="/dashboard"
                className="btn-linear btn-linear-ghost text-[#8a8f98] hover:text-[#f7f8f8]"
                suppressHydrationWarning
              >
                Go to dashboard →
              </Link>
            </div>
          </div>

          {/* Protagonist: High-Fidelity Product UI Screenshot Card (DESIGN.md: product-screenshot-card) */}
          <div className="mt-12 overflow-hidden rounded-[16px] border border-[#23252a] bg-[#0f1011] p-3 sm:p-6">
            <div className="flex items-center justify-between border-b border-[#23252a] pb-3 text-xs text-[#8a8f98]">
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full bg-[#23252a]" />
                <span className="h-2.5 w-2.5 rounded-full bg-[#23252a]" />
                <span className="h-2.5 w-2.5 rounded-full bg-[#23252a]" />
                <span className="ml-2 font-mono text-[11px] text-[#62666d]">app.webobserver.dev/monitors/mon_stripe_pricing</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center gap-1 rounded-full bg-[#141516] px-2 py-0.5 text-[11px] font-medium text-[#d0d6e0] border border-[#23252a]">
                  <span className="h-1.5 w-1.5 rounded-full bg-[#27a644]" />
                  Active · checked 2m ago
                </span>
              </div>
            </div>

            {/* Inner Mockup UI */}
            <div className="mt-4 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-[8px] border border-[#23252a] bg-[#141516] font-mono text-sm font-semibold text-[#f7f8f8]">
                    S
                  </div>
                  <div>
                    <h2 className="font-display text-base font-semibold text-[#f7f8f8]">Stripe · Billing &amp; Pricing Changes</h2>
                    <p className="font-mono text-xs text-[#8a8f98]">https://stripe.com/pricing · every 15m</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="rounded-full border border-[#5e6ad2]/25 bg-[#5e6ad2]/10 px-2 py-0.5 text-[11px] font-medium text-[#828fff]">
                    Product price
                  </span>
                  <span className="rounded-full border border-amber-500/20 bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-300">
                    impact: high
                  </span>
                </div>
              </div>

              {/* AI Triage Banner */}
              <div className="rounded-[8px] border border-[#23252a] bg-[#141516] p-3 text-xs leading-relaxed text-[#d0d6e0]">
                <div className="flex items-center gap-1.5 font-medium text-[#828fff]">
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8L12 2z"/></svg>
                  <span>AI Change Summary</span>
                </div>
                <p className="mt-1 text-[#f7f8f8]">
                  Standard platform fee updated from 2.9% + 30¢ to 2.9% + 35¢ per transaction. Added volume discount tier for Enterprise billing accounts.
                </p>
              </div>

              {/* Code Diff Box */}
              <div className="overflow-hidden rounded-[8px] border border-[#23252a] bg-[#010102] font-mono text-xs">
                <div className="flex items-center justify-between border-b border-[#23252a] bg-[#141516] px-3 py-1.5 text-[11px] text-[#8a8f98]">
                  <span>pricing_table.html</span>
                  <span className="text-[#27a644]">+2 lines</span>
                </div>
                <div className="divide-y divide-[#23252a] p-3 text-[11px] leading-relaxed">
                  <div className="flex items-start gap-3 text-rose-400">
                    <span className="w-6 shrink-0 select-none text-right text-[#62666d]">42</span>
                    <span className="select-none">-</span>
                    <span>&lt;span class=&quot;price&quot;&gt;2.9% + 30¢ per transaction&lt;/span&gt;</span>
                  </div>
                  <div className="flex items-start gap-3 pt-1 text-[#27a644]">
                    <span className="w-6 shrink-0 select-none text-right text-[#62666d]">42</span>
                    <span className="select-none">+</span>
                    <span>&lt;span class=&quot;price&quot;&gt;2.9% + 35¢ per transaction&lt;/span&gt;</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Capabilities Section */}
        <section className="border-t border-[#23252a] pt-16">
          <p className="eyebrow text-[#8a8f98]">Capabilities</p>
          <h2 className="mt-2.5 max-w-[28ch] font-display text-2xl font-semibold tracking-[-0.6px] text-[#f7f8f8] sm:text-3xl">
            Precise monitoring with craft and clarity.
          </h2>
          <div className="mt-8 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {features.map((f) => (
              <article
                key={f.title}
                className="flex flex-col gap-3 rounded-[12px] border border-[#23252a] bg-[#0f1011] p-6 transition hover:border-[#34343a] hover:bg-[#141516]"
              >
                <p className="eyebrow text-[#8a8f98]">{f.eyebrow}</p>
                <h3 className="font-display text-[20px] font-medium leading-[1.25] tracking-[-0.4px] text-[#f7f8f8]">
                  {f.title}
                </h3>
                <p className="text-[14px] leading-[1.5] text-[#8a8f98]">{f.body}</p>
                <Link
                  href="/docs"
                  className="mt-auto text-[13px] font-medium text-[#5e6ad2] hover:text-[#828fff]"
                >
                  Learn more →
                </Link>
              </article>
            ))}
          </div>
        </section>

        {/* Closing CTA Banner (DESIGN.md: cta-banner) */}
        <section className="mt-16 rounded-[12px] border border-[#23252a] bg-[#0f1011] p-8 text-center text-[#f7f8f8] sm:p-12">
          <p className="eyebrow text-[#8a8f98]">Enterprise-ready monitoring</p>
          <h2 className="mx-auto mt-2.5 max-w-[24ch] font-display text-2xl font-semibold leading-[1.20] tracking-[-0.6px] text-[#f7f8f8] sm:text-3xl lg:text-4xl">
            Serious infrastructure for web changes.
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-sm leading-relaxed text-[#d0d6e0]">
            Page content · Site links · Product price · List items · JSON field · RSS feed · GitHub README · Visual diffs · Security scans · AI impact triage
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-2.5">
            <Link href="/sign-up" className="btn-linear btn-linear-primary !px-4 !py-2.5">
              Start monitoring
            </Link>
            <Link href="/docs" className="btn-linear btn-linear-secondary !px-4 !py-2.5">
              Read documentation
            </Link>
          </div>
          <div className="mx-auto mt-8 flex max-w-3xl flex-wrap items-center justify-center gap-x-6 gap-y-2 border-t border-[#23252a] pt-6 font-mono text-[11px] uppercase tracking-[0.1em] text-[#62666d]">
            {trustBar.map((t) => (
              <span key={t}>{t}</span>
            ))}
          </div>
        </section>
      </main>

      {/* Footer (DESIGN.md: footer - 64px 32px padding, #010102 canvas) */}
      <footer
        className="relative z-10 border-t border-[#23252a] bg-[#010102] px-6 py-16 sm:px-8"
        suppressHydrationWarning
      >
        <div className="mx-auto flex max-w-6xl flex-col gap-8 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <Logo compact iconSize={24} />
            <span className="text-xs text-[#8a8f98]">© 2026 Web Observer. Crafted for high-signal web monitoring.</span>
          </div>
          <nav className="flex flex-wrap items-center gap-6 text-xs text-[#8a8f98]" aria-label="Footer">
            <Link href="/docs" className="transition hover:text-[#f7f8f8]">
              Docs
            </Link>
            <Link href="/dashboard" className="transition hover:text-[#f7f8f8]">
              Dashboard
            </Link>
            <Link href="/monitors" className="transition hover:text-[#f7f8f8]">
              Monitors
            </Link>
            <Link href="/alerts" className="transition hover:text-[#f7f8f8]">
              Alerts
            </Link>
            <Link href="/sign-in" className="transition hover:text-[#f7f8f8]">
              Sign in
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
