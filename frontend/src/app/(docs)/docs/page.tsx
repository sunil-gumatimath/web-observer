import Link from "next/link";
import type { ReactNode } from "react";
import { Card, PageHeader } from "@/components/ui";

export const metadata = { title: "Documentation · Web Observer" };

const toc = [
  { id: "what-it-is", label: "What it is" },
  { id: "how-it-works", label: "How it works" },
  { id: "quick-start", label: "Quick start" },
  { id: "modes", label: "Monitor modes" },
  { id: "create", label: "Create a monitor" },
  { id: "runs-changes", label: "Runs & changes" },
  { id: "alerts", label: "Alerts & channels" },
  { id: "settings", label: "Settings" },
  { id: "import", label: "Bulk import" },
  { id: "tips", label: "Tips & FAQ" },
];

function DocSection({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-24">
      <h2 className="mb-3 text-xl font-semibold tracking-tight text-slate-900 dark:text-white">
        {title}
      </h2>
      <div className="space-y-3 text-sm leading-relaxed text-slate-600 dark:text-slate-400">
        {children}
      </div>
    </section>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-sky-500/15 text-xs font-bold text-sky-600 dark:text-sky-400">
        {n}
      </span>
      <div>
        <p className="font-medium text-slate-800 dark:text-slate-200">{title}</p>
        <p className="mt-0.5 text-slate-600 dark:text-slate-400">{children}</p>
      </div>
    </li>
  );
}

export default function DocsPage() {
  return (
    <div>
      <PageHeader
        title="Documentation"
        description="How Web Observer works, and how to set up monitors, alerts, and imports."
      />

      <div className="grid gap-8 lg:grid-cols-[220px_1fr]">
        {/* TOC */}
        <aside className="hidden lg:block">
          <nav className="sticky top-24 space-y-1">
            <p className="section-label mb-3">On this page</p>
            {toc.map((item) => (
              <a
                key={item.id}
                href={`#${item.id}`}
                className="block rounded-lg px-2.5 py-1.5 text-sm text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-white/5 dark:hover:text-white"
              >
                {item.label}
              </a>
            ))}
          </nav>
        </aside>

        <div className="min-w-0 space-y-10">
          {/* Mobile TOC */}
          <Card className="!py-4 lg:hidden">
            <p className="section-label mb-2">On this page</p>
            <div className="flex flex-wrap gap-2">
              {toc.map((item) => (
                <a
                  key={item.id}
                  href={`#${item.id}`}
                  className="rounded-full border border-[var(--border)] px-2.5 py-1 text-xs text-slate-600 hover:border-sky-500/40 hover:text-sky-600 dark:text-slate-400 dark:hover:text-sky-300"
                >
                  {item.label}
                </a>
              ))}
            </div>
          </Card>

          <DocSection id="what-it-is" title="What it is">
            <p>
              <strong className="text-slate-800 dark:text-slate-200">Web Observer</strong> watches
              public web pages (or parts of them) on a schedule. When content changes, it stores a
              clear before/after diff and can notify you by email, Slack, or Discord.
            </p>
            <p>Use it for pricing pages, changelogs, competitor sites, docs, APIs, or any URL you care about.</p>
            <Card className="!p-4 !shadow-none">
              <p className="text-sm text-slate-700 dark:text-slate-300">
                <span className="font-medium text-sky-600 dark:text-sky-400">Not uptime monitoring.</span>{" "}
                This app focuses on <em>content change</em> (what changed on the page), not whether the
                server is merely online.
              </p>
            </Card>
          </DocSection>

          <DocSection id="how-it-works" title="How it works">
            <ol className="space-y-4">
              <Step n={1} title="You create a monitor">
                Pick a URL, a mode (page content, site links, product price, or list
                items), and how often to check.
              </Step>
              <Step n={2} title="A worker fetches the page">
                The backend pulls the page (HTTP or Playwright if JavaScript is required) and
                extracts the content you care about.
              </Step>
              <Step n={3} title="First success = baseline">
                The first successful run saves a content hash as the baseline.{" "}
                <strong className="text-slate-800 dark:text-slate-200">No alert is sent</strong> for
                the baseline.
              </Step>
              <Step n={4} title="Later runs compare hashes">
                If the hash differs, a change event is saved with a deterministic diff (and optional
                AI summary). Alerts go to your channels.
              </Step>
            </ol>
          </DocSection>

          <DocSection id="quick-start" title="Quick start">
            <ol className="list-decimal space-y-2 pl-5">
              <li>
                <Link href="/sign-up" className="text-sky-600 hover:text-sky-500 dark:text-sky-400">
                  Create an account
                </Link>{" "}
                or sign in.
              </li>
              <li>
                Open{" "}
                <Link href="/monitors/new" className="text-sky-600 hover:text-sky-500 dark:text-sky-400">
                  New monitor
                </Link>
                , enter a name and public HTTPS URL.
              </li>
              <li>Choose a mode (start with <strong>Whole page text</strong> if unsure).</li>
              <li>Set check interval (minimum 15 minutes) and optional alert email.</li>
              <li>
                Open the monitor and click <strong>Run now</strong> to take a baseline immediately
                (scheduled checks need the worker + scheduler running).
              </li>
              <li>
                After a real change on the site, run again — you should see a change event and an
                alert if channels are configured.
              </li>
            </ol>
            <p className="pt-1">
              Also add channels under{" "}
              <Link href="/settings" className="text-sky-600 hover:text-sky-500 dark:text-sky-400">
                Settings
              </Link>{" "}
              so alerts have somewhere to go.
            </p>
          </DocSection>

          <DocSection id="modes" title="Monitor modes">
            <div className="overflow-hidden rounded-xl border border-[var(--border)]">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-[var(--border)] bg-slate-50 dark:bg-slate-950/40">
                    <th className="px-3 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                      Monitor
                    </th>
                    <th className="px-3 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                      What it watches
                    </th>
                    <th className="px-3 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                      Alerts on
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border)]">
                  <tr>
                    <td className="px-3 py-3 font-medium text-slate-800 dark:text-slate-200">
                      Site links
                    </td>
                    <td className="px-3 py-3">The site&apos;s sitemap</td>
                    <td className="px-3 py-3">New links, removed links, or both</td>
                  </tr>
                  <tr>
                    <td className="px-3 py-3 font-medium text-slate-800 dark:text-slate-200">
                      Page content
                    </td>
                    <td className="px-3 py-3">A single page, scraped to markdown</td>
                    <td className="px-3 py-3">Any content change, with a line-level diff</td>
                  </tr>
                  <tr>
                    <td className="px-3 py-3 font-medium text-slate-800 dark:text-slate-200">
                      Product price
                    </td>
                    <td className="px-3 py-3">A product page</td>
                    <td className="px-3 py-3">Price or currency changes (checks every 24h by default)</td>
                  </tr>
                  <tr>
                    <td className="px-3 py-3 font-medium text-slate-800 dark:text-slate-200">
                      List items
                    </td>
                    <td className="px-3 py-3">A CSS-selector link list on a page</td>
                    <td className="px-3 py-3">Added or removed items as clickable links</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p>
              <strong className="text-slate-800 dark:text-slate-200">JavaScript rendering</strong> —
              enable Playwright when the page only shows content after client-side render.
              Site links reads the sitemap over HTTP; the other modes can use Playwright when
              <code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">js_required</code> is enabled.
            </p>
            <p>
              <strong className="text-slate-800 dark:text-slate-200">Ignore selectors</strong> — for
              page content monitors, list CSS selectors (one per line) to strip cookie banners,
              ads, or timestamps that would otherwise create noise. List items uses its own{" "}
              <code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">css_selector</code>.
            </p>
          </DocSection>

          <DocSection id="create" title="Create a monitor">
            <p>
              Go to{" "}
              <Link href="/monitors/new" className="text-sky-600 hover:text-sky-500 dark:text-sky-400">
                New monitor
              </Link>
              .
            </p>
            <ul className="list-disc space-y-1.5 pl-5">
              <li>
                <strong className="text-slate-800 dark:text-slate-200">Name</strong> — label in the UI
                (e.g. “Competitor pricing”).
              </li>
              <li>
                <strong className="text-slate-800 dark:text-slate-200">URL</strong> — must be a public{" "}
                <code className="rounded bg-slate-100 px-1 py-0.5 text-xs dark:bg-slate-800">
                  https://
                </code>{" "}
                address the server can reach (private/internal IPs are blocked for safety).
              </li>
              <li>
                <strong className="text-slate-800 dark:text-slate-200">Interval</strong> — minutes
                between scheduled checks (minimum 15).
              </li>
              <li>
                <strong className="text-slate-800 dark:text-slate-200">Alert email</strong> — optional
                per-monitor override; workspace channels still apply when set in Settings.
              </li>
            </ul>
            <p>
              After create, open the monitor detail page to <strong>Run now</strong>,{" "}
              <strong>Pause</strong> / <strong>Resume</strong>, <strong>Edit</strong>, or{" "}
              <strong>Delete</strong>.
            </p>
            <p className="rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-amber-800 dark:text-amber-200">
              Editing URL, mode, or selector creates a <strong>new baseline</strong> on the next
              success (no alert for that re-baseline).
            </p>
          </DocSection>

          <DocSection id="runs-changes" title="Runs & changes">
            <p>
              On each monitor detail page you will see:
            </p>
            <ul className="list-disc space-y-1.5 pl-5">
              <li>
                <strong className="text-slate-800 dark:text-slate-200">Recent runs</strong> — status
                (succeeded / failed), HTTP code, latency, and errors.
              </li>
              <li>
                <strong className="text-slate-800 dark:text-slate-200">Changes</strong> — events where
                content differed from the previous hash. Open one for the full diff.
              </li>
              <li>
                <strong className="text-slate-800 dark:text-slate-200">Visual diffs</strong> — GitHub-style added/removed line views (split + unified) for every content change via <code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">GithubDiff</code> + <code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">unified_diff</code>.
              </li>
              <li>
                <strong className="text-slate-800 dark:text-slate-200">Opt-in screenshots</strong> — when <code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">screenshots_enabled</code> is on, every check captures a fresh Playwright screenshot (<code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">screenshots/{"{monitor_id}/{run_id}.png"}</code>) with aHash history — off by default to avoid forcing Playwright on text monitors.
              </li>
              <li>
                <strong className="text-slate-800 dark:text-slate-200">AI change summaries</strong> — optional plain-language summaries per change (heuristic by default; enable OpenAI or Vercel AI Gateway via <code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">LLM_API_BASE</code> and toggle per-workspace <code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">ai_summaries_enabled</code>).
              </li>
              <li>
                <strong className="text-slate-800 dark:text-slate-200">AI relevance filter</strong> — optional per-monitor <code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">watch_note</code> triage; routine noise is held as <code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">is_noise=true</code> in the dashboard (not deleted), excluded from notifications, fails open on LLM error.
              </li>
              <li>
                <strong className="text-slate-800 dark:text-slate-200">Brand-aware dashboard</strong> — adding a website auto-fills logo/title/description/hero from HTML <code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">og:*</code> meta and re-hosts via <code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">brand-assets/</code> for dashboard + public share pages (no Context.dev).
              </li>
            </ul>
            <p>
              On a change detail page you can mark something as <strong>noise</strong> (false alarm)
              so you can filter signal later. Diffs are deterministic text comparisons of the
              extracted content. Nothing is deleted — held noise is still stored and viewable, just not delivered.
            </p>
          </DocSection>

          <DocSection id="alerts" title="Alerts & channels">
            <p>
              <strong className="text-slate-800 dark:text-slate-200">Alerts inbox</strong> — every change is stored in-app with <code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">is_read</code>/<code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">is_noise</code> state, independent of external notifications. Filter Signal / Unread / Noise at <Link href="/alerts" className="text-sky-600 hover:text-sky-500 dark:text-sky-400">Alerts</Link>.
            </p>
            <p>
              Configure channels under{" "}
              <Link href="/settings" className="text-sky-600 hover:text-sky-500 dark:text-sky-400">
                Settings → Alert channels
              </Link>
              :
            </p>
            <ul className="list-disc space-y-1.5 pl-5">
              <li>
                <strong className="text-slate-800 dark:text-slate-200">Email</strong> — uses Resend
                when the API key is configured on the server (or per-workspace override).
              </li>
              <li>
                <strong className="text-slate-800 dark:text-slate-200">Slack</strong> — paste an
                incoming webhook URL.
              </li>
              <li>
                <strong className="text-slate-800 dark:text-slate-200">Discord</strong> — paste a
                Discord webhook URL.
              </li>
            </ul>
            <p>
              Enable only the channels you want. Alerts fire when a non-baseline content change is
              detected (and the notifications worker is running). Noise-marked changes do not notify.
            </p>
            <p>
              Optional <strong>digests</strong> (daily / weekly) summarize activity instead of only
              real-time pings — set cadence and UTC hour in Settings → Preferences.
            </p>
          </DocSection>

          <DocSection id="settings" title="Settings">
            <ul className="list-disc space-y-1.5 pl-5">
              <li>
                <strong className="text-slate-800 dark:text-slate-200">API health</strong> — confirms
                the frontend can reach the backend.
              </li>
              <li>
                <strong className="text-slate-800 dark:text-slate-200">Workspace</strong> — your
                active workspace ID (usually created automatically after sign-in).
              </li>
              <li>
                <strong className="text-slate-800 dark:text-slate-200">Preferences</strong> — digests
                and AI summaries (heuristic if no LLM key is set; toggle <code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">ai_summaries_enabled</code>).
              </li>
              <li>
                <strong className="text-slate-800 dark:text-slate-200">Managed or self-serve keys</strong> — run managed (server provides <code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">LLM_API_*</code>/<code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">RESEND_API_KEY</code>) or let each workspace bring its own keys in Settings → Workspace keys (overrides global; supports OpenAI or Vercel AI Gateway).
              </li>
              <li>
                <strong className="text-slate-800 dark:text-slate-200">Teams</strong> — invite members with expiring multi-use links (<code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">/invite/{"{token}"}</code>) and switch between workspaces you belong to.
              </li>
              <li>
                <strong className="text-slate-800 dark:text-slate-200">Public share links</strong> — generate a read-only public page per monitor (<code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">/share/{"{token}"}</code> — unguessable, hashed at rest, no login required).
              </li>
              <li>
                <strong className="text-slate-800 dark:text-slate-200">API keys & webhooks</strong> —
                optional automation hooks for external tools (<code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">mtw_*</code> + <code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">X-MTW-Signature</code>).
              </li>
            </ul>
          </DocSection>

          <DocSection id="import" title="Bulk import">
            <p>
              Use{" "}
              <Link href="/import" className="text-sky-600 hover:text-sky-500 dark:text-sky-400">
                Import
              </Link>{" "}
              to create many monitors from CSV. Expected columns:
            </p>
            <pre className="overflow-x-auto rounded-xl border border-[var(--border)] bg-slate-50 p-3 font-mono text-xs text-slate-700 dark:bg-slate-950/60 dark:text-slate-300">
              {`name,url,mode,schedule_interval_minutes
Example,https://example.com/,page_content,60
Pricing,https://example.com/pricing,product_price,1440
Links,https://example.com/blog,list_items,60`}
            </pre>
            <p>
              Valid modes:{" "}
              <code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">page_content</code>
              ,{" "}
              <code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">site_links</code>
              ,{" "}
              <code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">product_price</code>
              ,{" "}
              <code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">list_items</code>{" "}
              (requires <code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">css_selector</code>).
            </p>
          </DocSection>

          <DocSection id="tips" title="Tips & FAQ">
            <div className="space-y-4">
              <div>
                <p className="font-medium text-slate-800 dark:text-slate-200">
                  Why didn’t I get an email on the first run?
                </p>
                <p>
                  First success only sets the baseline. Alerts start on later changes. Also confirm
                  the notifications worker is running and Resend / channel addresses are correct.
                </p>
              </div>
              <div>
                <p className="font-medium text-slate-800 dark:text-slate-200">
                  Schedule isn’t running by itself
                </p>
                <p>
                  You need the API, Dramatiq worker (queues for checks + notifications), Redis, and
                  optionally the scheduler process. “Run now” only needs API + worker.
                </p>
              </div>
              <div>
                <p className="font-medium text-slate-800 dark:text-slate-200">Too many false alerts</p>
                <p>
                  Prefer CSS selector over whole page, add ignore selectors for banners/ads, or
                  mark noisy changes as noise. Narrower extraction = cleaner signal.
                </p>
              </div>
              <div>
                <p className="font-medium text-slate-800 dark:text-slate-200">
                  Overview usage numbers
                </p>
                <p>
                  The dashboard shows monitors count, checks today, and notifications today against
                  your plan limits.
                </p>
              </div>
            </div>

            <Card className="!p-4 mt-4">
              <p className="text-sm text-slate-700 dark:text-slate-300">
                Need to create a monitor now?{" "}
                <Link
                  href="/monitors/new"
                  className="font-medium text-sky-600 hover:text-sky-500 dark:text-sky-400"
                >
                  New monitor →
                </Link>
              </p>
            </Card>
          </DocSection>
        </div>
      </div>
    </div>
  );
}
