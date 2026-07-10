import Link from "next/link";

const features = [
  {
    title: "Precise change detection",
    body: "Watch whole pages, CSS sections, JSON fields, list items, or visual screenshots.",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M2.25 12 9 5.25l4.5 4.5L21.75 3M21.75 12v6.75a2.25 2.25 0 0 1-2.25 2.25H4.5A2.25 2.25 0 0 1 2.25 18.75V12"
        />
      </svg>
    ),
  },
  {
    title: "Clear before / after diffs",
    body: "Inspect deterministic text diffs and optional AI summaries so noise stays out of your inbox.",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z"
        />
      </svg>
    ),
  },
  {
    title: "Alerts where you work",
    body: "Email, Slack, or Discord when something meaningful changes — not every cookie banner.",
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0"
        />
      </svg>
    ),
  },
];

export default function HomePage() {
  return (
    <div className="relative min-h-screen overflow-hidden text-slate-100">
      <div className="pointer-events-none absolute inset-0 hero-grid" />

      <header className="relative z-10 mx-auto flex max-w-6xl items-center justify-between px-4 py-5">
        <div className="flex items-center gap-2.5 font-semibold tracking-tight">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-sky-400 to-indigo-500 text-sm font-bold text-white shadow-glow-sm">
            M
          </span>
          <span>
            Monitor<span className="text-slate-400">-the-</span>Web
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/sign-in"
            className="rounded-lg px-3 py-1.5 text-sm font-medium text-slate-300 transition hover:text-white"
          >
            Sign in
          </Link>
          <Link
            href="/sign-up"
            className="rounded-lg bg-gradient-to-b from-sky-500 to-sky-600 px-3.5 py-1.5 text-sm font-medium text-white shadow-glow-sm transition hover:from-sky-400 hover:to-sky-500"
          >
            Get started
          </Link>
        </div>
      </header>

      <main className="relative z-10 mx-auto max-w-6xl px-4 pb-24 pt-12 sm:pt-20">
        <div className="mx-auto max-w-3xl text-center animate-fade-in-up">
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-sky-500/25 bg-sky-500/10 px-3 py-1 text-xs font-medium text-sky-300">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-sky-400" />
            Web change detection & high-signal alerts
          </div>
          <h1 className="text-4xl font-semibold tracking-tight text-white sm:text-5xl md:text-6xl md:leading-[1.08]">
            Know the moment{" "}
            <span className="bg-gradient-to-r from-sky-300 via-cyan-200 to-indigo-300 bg-clip-text text-transparent">
              pages you care about
            </span>{" "}
            change.
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-base leading-relaxed text-slate-400 sm:text-lg">
            Track public URLs or precise sections, get email and webhook alerts, and review clear
            before-and-after diffs. Built for product teams, founders, and researchers.
          </p>
          <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
            <Link
              href="/sign-up"
              className="rounded-xl bg-gradient-to-b from-sky-500 to-sky-600 px-6 py-3 text-sm font-semibold text-white shadow-glow transition hover:from-sky-400 hover:to-sky-500"
            >
              Create free account
            </Link>
            <Link
              href="/sign-in"
              className="rounded-xl border border-white/10 bg-white/5 px-6 py-3 text-sm font-semibold text-slate-100 backdrop-blur transition hover:bg-white/10"
            >
              Sign in
            </Link>
            <Link
              href="/dashboard"
              className="rounded-xl px-4 py-3 text-sm font-medium text-slate-400 transition hover:text-white"
            >
              Go to dashboard →
            </Link>
          </div>
        </div>

        <div className="mx-auto mt-20 grid max-w-5xl gap-4 sm:grid-cols-3">
          {features.map((f) => (
            <div
              key={f.title}
              className="glass-card group transition hover:border-sky-500/25 hover:shadow-glow-sm"
            >
              <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-xl bg-sky-500/10 text-sky-400 ring-1 ring-sky-500/20 transition group-hover:bg-sky-500/15">
                {f.icon}
              </div>
              <h2 className="text-base font-semibold text-white">{f.title}</h2>
              <p className="mt-1.5 text-sm leading-relaxed text-slate-400">{f.body}</p>
            </div>
          ))}
        </div>

        <div className="mx-auto mt-16 max-w-3xl rounded-2xl border border-white/10 bg-gradient-to-br from-slate-900/80 to-slate-950/80 p-8 text-center shadow-card backdrop-blur">
          <p className="text-sm font-medium text-slate-300">
            Whole page · CSS selector · JSON field · List items · Visual screenshots
          </p>
          <p className="mt-2 text-xs text-slate-500">
            Auth powered by Clerk. After sign-in you land on the dashboard.
          </p>
        </div>
      </main>
    </div>
  );
}
