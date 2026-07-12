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
import type { MonitorMode } from "@/lib/types";
import { ensureWorkspace } from "@/lib/workspace";

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
  const router = useRouter();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("https://example.com/");
  const [mode, setMode] = useState<MonitorMode>("whole_page");
  const [cssSelector, setCssSelector] = useState("");
  const [interval, setInterval] = useState(60);
  const [email, setEmail] = useState("");
  const [jsRequired, setJsRequired] = useState(false);
  const [watchNote, setWatchNote] = useState("");
  const [ignoreSelectors, setIgnoreSelectors] = useState("");
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
    </div>
  );
}
