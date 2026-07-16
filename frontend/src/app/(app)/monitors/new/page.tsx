"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import {
  Button,
  Card,
  ErrorBox,
  Input,
  Label,
  PageHeader,
  Select,
  Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import type { MonitorMode, SitemapDiscovery as SitemapDiscoveryResult, SitemapImportResult } from "@/lib/types";
import { ensureWorkspace } from "@/lib/workspace";
import { usePageTitle } from "@/lib/use-page-title";

function pathLabel(mode: MonitorMode): string {
  switch (mode) {
    case "css_selector":
      return "CSS selector";
    case "json_field":
      return "JSON path (e.g. $.price or $.data.items[0].name)";
    case "list_items":
      return "List path/selector (JSON path to array, or CSS for HTML list items)";
    case "visual":
      return "Optional region CSS selector (empty = full page screenshot)";
    default:
      return "Selector";
  }
}

function needsPath(mode: MonitorMode): boolean {
  return mode === "css_selector" || mode === "json_field" || mode === "list_items";
}

export default function NewMonitorPage() {
  usePageTitle("New monitor");
  const router = useRouter();
  const [createMode, setCreateMode] = useState<"single" | "sitemap">("single");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("https://example.com/");
  const [mode, setMode] = useState<MonitorMode>("whole_page");
  const [cssSelector, setCssSelector] = useState("");
  const [interval, setInterval] = useState(60);
  const [email, setEmail] = useState("");
  const [jsRequired, setJsRequired] = useState(false);
  const [watchNote, setWatchNote] = useState("");
  const [ignoreSelectors, setIgnoreSelectors] = useState("");
  const [ignoreRegexes, setIgnoreRegexes] = useState("");
  const [runNow, setRunNow] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const IGNORE_PRESETS: Record<string, string[]> = {
    cookies: [".cookie-banner", "#cookie-consent", "[class*='cookie']", "#onetrust-banner-sdk"],
    ads: [".ads", ".ad-slot", "[id*='google_ads']", "iframe[src*='doubleclick']"],
    chat: [".intercom-lightweight-app", "#hubspot-messages-iframe-container", "[class*='chat-widget']"],
  };

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const ws = await ensureWorkspace();
      const ignore = ignoreSelectors
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);
      const ignoreRegex = ignoreRegexes
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);
      const monitor = await api.createMonitor(ws, {
        name,
        url,
        mode,
        css_selector:
          needsPath(mode) || (mode === "visual" && cssSelector)
            ? cssSelector || null
            : null,
        schedule_interval_minutes: interval,
        notification_email: email || undefined,
        js_required: jsRequired || mode === "visual",
        watch_note: watchNote.trim() || null,
        ignore_selectors: ignore.length ? ignore : null,
        ignore_regexes: ignoreRegex.length ? ignoreRegex : null,
      });

      // Kick off first check so the detail page can show a live result.
      if (runNow) {
        try {
          await api.runMonitor(ws, monitor.id);
        } catch {
          // Scheduler may already have queued a run — detail page will poll either way.
        }
      }

      router.push(`/monitors/${monitor.id}?fresh=1`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create monitor");
      setSaving(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Create monitor"
        description="Text, JSON field, list items, or visual (screenshot) monitoring."
      />
      {error ? <ErrorBox message={error} /> : null}

      <div className="mb-5 flex gap-2">
        <button
          type="button"
          onClick={() => setCreateMode("single")}
          className={
            createMode === "single"
              ? "rounded-lg bg-sky-600 px-3 py-1.5 text-sm font-medium text-white"
              : "rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/5"
          }
        >
          Single URL
        </button>
        <button
          type="button"
          onClick={() => setCreateMode("sitemap")}
          className={
            createMode === "sitemap"
              ? "rounded-lg bg-sky-600 px-3 py-1.5 text-sm font-medium text-white"
              : "rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/5"
          }
        >
          From sitemap
        </button>
      </div>

      {createMode === "sitemap" ? (
        <SitemapDiscovery
          onDone={() => router.push("/monitors")}
          onCancel={() => setCreateMode("single")}
        />
      ) : (
        <Card className="max-w-xl">
          <form onSubmit={onSubmit} className="space-y-5">
          <div>
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Pricing page"
            />
          </div>
          <div>
            <Label htmlFor="url">URL</Label>
            <Input
              id="url"
              required
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://example.com/pricing"
            />
          </div>
          <div>
            <Label htmlFor="mode">Mode</Label>
            <Select
              id="mode"
              value={mode}
              onChange={(e) => setMode(e.target.value as MonitorMode)}
            >
              <option value="whole_page">Whole page text</option>
              <option value="css_selector">CSS selector (HTML section)</option>
              <option value="json_field">JSON field</option>
              <option value="list_items">List items (JSON array or HTML list)</option>
              <option value="visual">Visual (screenshot / perceptual hash)</option>
            </Select>
          </div>
          {needsPath(mode) || mode === "visual" ? (
            <div>
              <Label htmlFor="selector">{pathLabel(mode)}</Label>
              <Input
                id="selector"
                required={needsPath(mode)}
                value={cssSelector}
                onChange={(e) => setCssSelector(e.target.value)}
                placeholder={
                  mode === "json_field"
                    ? "$.price"
                    : mode === "list_items"
                      ? "$.items or li.product"
                      : mode === "visual"
                        ? "#main (optional)"
                        : "main .price"
                }
              />
            </div>
          ) : null}
          <div>
            <Label htmlFor="interval">Check interval (minutes, min 15)</Label>
            <Input
              id="interval"
              type="number"
              min={15}
              required
              value={interval}
              onChange={(e) => setInterval(Number(e.target.value))}
            />
          </div>
          <div>
            <Label htmlFor="email">Alert email (optional)</Label>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
            />
          </div>
          {mode !== "visual" ? (
            <label className="flex cursor-pointer items-center gap-2.5 rounded-lg border border-[var(--border)] bg-slate-50/60 px-3 py-2.5 text-sm text-slate-700 transition hover:border-slate-400 dark:bg-slate-950/40 dark:text-slate-300 dark:hover:border-white/10">
              <input
                type="checkbox"
                checked={jsRequired}
                onChange={(e) => setJsRequired(e.target.checked)}
                className="h-4 w-4 rounded border-slate-400 bg-white text-sky-500 focus:ring-sky-500/30 dark:border-slate-600 dark:bg-slate-900"
              />
              JavaScript rendering required (Playwright)
            </label>
          ) : (
            <p className="rounded-lg border border-sky-500/25 bg-sky-500/10 px-3 py-2 text-xs text-sky-700 dark:border-sky-500/20 dark:bg-sky-500/5 dark:text-sky-200/90">
              Visual mode always uses the Playwright browser worker.
            </p>
          )}
          <div>
            <Label htmlFor="watch">Watch note (optional)</Label>
            <Input
              id="watch"
              value={watchNote}
              onChange={(e) => setWatchNote(e.target.value)}
              placeholder="e.g. Only care about pricing plan changes"
            />
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-500">
              Focuses AI summaries and helps you remember intent.
            </p>
          </div>
          {mode === "whole_page" || mode === "css_selector" ? (
            <>
              <div>
              <Label htmlFor="ignore">Ignore CSS selectors (one per line, optional)</Label>
              <div className="mb-2 flex flex-wrap gap-2">
                {Object.entries(IGNORE_PRESETS).map(([key, sels]) => (
                  <button
                    key={key}
                    type="button"
                    className="rounded-md border border-[var(--border)] px-2 py-1 text-xs capitalize text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/5"
                    onClick={() => {
                      const cur = new Set(
                        ignoreSelectors
                          .split("\n")
                          .map((s) => s.trim())
                          .filter(Boolean),
                      );
                      sels.forEach((s) => cur.add(s));
                      setIgnoreSelectors([...cur].join("\n"));
                    }}
                  >
                    + {key}
                  </button>
                ))}
              </div>
              <Textarea
                id="ignore"
                rows={3}
                value={ignoreSelectors}
                onChange={(e) => setIgnoreSelectors(e.target.value)}
                placeholder={".cookie-banner\n#ads"}
              />
            </div>
            <div className="mt-3">
              <Label htmlFor="ignoreRegex">Ignore text by regex (one per line, optional)</Label>
              <Textarea
                id="ignoreRegex"
                rows={3}
                value={ignoreRegexes}
                onChange={(e) => setIgnoreRegexes(e.target.value)}
                placeholder={"Price updated .* ago\nLast (login|visited): .*"}
              />
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-500">
                Matched text is stripped before diffing — useful for timestamps or volatile counters.
              </p>
            </div>
            </>
          ) : null}
          <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
            <input
              type="checkbox"
              checked={runNow}
              onChange={(e) => setRunNow(e.target.checked)}
              className="h-4 w-4 rounded border-slate-400 bg-white text-sky-500 focus:ring-sky-500/30 dark:border-slate-600 dark:bg-slate-900"
            />
            Run first check immediately (see result, then keep or delete)
          </label>
          <div className="flex gap-2 border-t border-[var(--border)] pt-5">
            <Button type="submit" disabled={saving}>
              {saving ? "Creating…" : "Create monitor"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => router.push("/monitors")}>
              Cancel
            </Button>
          </div>
        </form>
      </Card>
      )}
    </div>
  );
}

/**
 * Sitemap-driven bulk monitor creation.
 * 1. Enter a site URL → discover its sitemap URLs.
 * 2. Select which pages to monitor (checklist).
 * 3. Configure shared options, then create all selected monitors at once.
 */
function SitemapDiscovery({
  onDone,
  onCancel,
}: {
  onDone: () => void;
  onCancel: () => void;
}) {
  const [siteUrl, setSiteUrl] = useState("https://example.com/");
  const [discovery, setDiscovery] = useState<SitemapDiscoveryResult | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [mode, setMode] = useState<MonitorMode>("whole_page");
  const [interval, setInterval] = useState(60);
  const [jsRequired, setJsRequired] = useState(false);
  const [ignoreSelectors, setIgnoreSelectors] = useState("");
  const [ignoreRegexes, setIgnoreRegexes] = useState("");
  const [discovering, setDiscovering] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SitemapImportResult | null>(null);

  function toggleAll(next: boolean) {
    if (!discovery) return;
    setSelected(next ? new Set(discovery.urls) : new Set());
  }

  function toggleOne(url: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(url)) next.delete(url);
      else next.add(url);
      return next;
    });
  }

  async function onDiscover() {
    setDiscovering(true);
    setError(null);
    setDiscovery(null);
    setSelected(new Set());
    try {
      const ws = await ensureWorkspace();
      const res = await api.discoverSitemap(ws, siteUrl);
      setDiscovery(res);
      setSelected(new Set(res.urls));
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Sitemap discovery failed";
      setError(msg);
    } finally {
      setDiscovering(false);
    }
  }

  async function onCreate() {
    if (!discovery || selected.size === 0) return;
    setCreating(true);
    setError(null);
    setResult(null);
    try {
      const ws = await ensureWorkspace();
      const ignore = ignoreSelectors.split("\n").map((s) => s.trim()).filter(Boolean);
      const ignoreRegex = ignoreRegexes.split("\n").map((s) => s.trim()).filter(Boolean);
      const res = await api.createMonitorsFromSitemap(ws, {
        url: discovery.url,
        urls: [...selected],
        mode,
        schedule_interval_minutes: interval,
        js_required: jsRequired,
        ignore_selectors: ignore.length ? ignore : null,
        ignore_regexes: ignoreRegex.length ? ignoreRegex : null,
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create monitors");
    } finally {
      setCreating(false);
    }
  }

  return (
    <Card className="max-w-2xl space-y-5">
      {result ? (
        <div className="space-y-3">
          <p className="text-sm font-medium text-emerald-700 dark:text-emerald-400">
            Created {result.created_count} monitor{result.created_count === 1 ? "" : "s"}.
          </p>
          {result.skipped.length ? (
            <p className="text-xs text-slate-500 dark:text-slate-500">
              {result.skipped.length} skipped (duplicate URLs already monitored).
            </p>
          ) : null}
          {result.errors.length ? (
            <p className="text-xs text-rose-600 dark:text-rose-400">
              {result.errors.length} failed — see server logs.
            </p>
          ) : null}
          <div className="flex gap-2 pt-2">
            <Button type="button" onClick={onDone}>
              View monitors
            </Button>
            <Button type="button" variant="ghost" onClick={onCancel}>
              Back
            </Button>
          </div>
        </div>
      ) : (
        <>
          <div className="space-y-2">
            <Label htmlFor="site">Website URL</Label>
            <div className="flex flex-wrap gap-2">
              <Input
                id="site"
                type="url"
                required
                value={siteUrl}
                onChange={(e) => setSiteUrl(e.target.value)}
                placeholder="https://example.com/"
                className="flex-1"
              />
              <Button type="button" onClick={onDiscover} disabled={discovering}>
                {discovering ? "Discovering…" : "Discover"}
              </Button>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-500">
              Reads the site&apos;s sitemap.xml (or robots.txt) and lists the pages it contains.
            </p>
          </div>

          {error ? <ErrorBox message={error} /> : null}

          {discovery ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm text-slate-600 dark:text-slate-300">
                  {discovery.count} page{discovery.count === 1 ? "" : "s"} found
                </p>
                <div className="flex gap-2">
                  <Button type="button" variant="ghost" size="sm" onClick={() => toggleAll(true)}>
                    Select all
                  </Button>
                  <Button type="button" variant="ghost" size="sm" onClick={() => toggleAll(false)}>
                    Clear
                  </Button>
                </div>
              </div>
              <div className="max-h-72 space-y-1 overflow-y-auto rounded-xl border border-[var(--border)] p-2">
                {discovery.urls.map((u) => (
                  <label
                    key={u}
                    className="flex cursor-pointer items-start gap-2.5 rounded-lg px-2 py-1.5 text-sm hover:bg-slate-100/60 dark:hover:bg-white/5"
                  >
                    <input
                      type="checkbox"
                      checked={selected.has(u)}
                      onChange={() => toggleOne(u)}
                      className="mt-0.5 h-4 w-4 rounded border-slate-400 bg-white text-sky-500 focus:ring-sky-500/30 dark:border-slate-600 dark:bg-slate-900"
                    />
                    <span className="min-w-0 break-all text-slate-700 dark:text-slate-300">{u}</span>
                  </label>
                ))}
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <Label htmlFor="sm-mode">Mode</Label>
                  <Select
                    id="sm-mode"
                    value={mode}
                    onChange={(e) => setMode(e.target.value as MonitorMode)}
                  >
                    <option value="whole_page">Whole page text</option>
                    <option value="css_selector">CSS selector (HTML section)</option>
                    <option value="json_field">JSON field</option>
                    <option value="list_items">List items</option>
                    <option value="visual">Visual (screenshot)</option>
                  </Select>
                </div>
                <div>
                  <Label htmlFor="sm-interval">Check interval (minutes, min 15)</Label>
                  <Input
                    id="sm-interval"
                    type="number"
                    min={15}
                    required
                    value={interval}
                    onChange={(e) => setInterval(Number(e.target.value))}
                  />
                </div>
              </div>
              {mode !== "visual" ? (
                <label className="flex cursor-pointer items-center gap-2.5 rounded-lg border border-[var(--border)] bg-slate-50/60 px-3 py-2.5 text-sm text-slate-700 dark:bg-slate-950/40 dark:text-slate-300">
                  <input
                    type="checkbox"
                    checked={jsRequired}
                    onChange={(e) => setJsRequired(e.target.checked)}
                    className="h-4 w-4 rounded border-slate-400 bg-white text-sky-500 focus:ring-sky-500/30 dark:border-slate-600 dark:bg-slate-900"
                  />
                  JavaScript rendering required (Playwright)
                </label>
              ) : null}

              <div className="flex gap-2 border-t border-[var(--border)] pt-5">
                <Button type="button" onClick={onCreate} disabled={creating || selected.size === 0}>
                  {creating
                    ? "Creating…"
                    : `Create ${selected.size || ""} monitor${selected.size === 1 ? "" : "s"}`}
                </Button>
                <Button type="button" variant="ghost" onClick={onCancel}>
                  Cancel
                </Button>
              </div>
            </div>
          ) : null}
        </>
      )}
    </Card>
  );
}
