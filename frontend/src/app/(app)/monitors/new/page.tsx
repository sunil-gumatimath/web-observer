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
  const [ignoreSelectors, setIgnoreSelectors] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

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
        ignore_selectors: ignore.length ? ignore : null,
      });
      router.push(`/monitors/${monitor.id}`);
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
          {mode === "whole_page" || mode === "css_selector" ? (
            <div>
              <Label htmlFor="ignore">Ignore CSS selectors (one per line, optional)</Label>
              <Textarea
                id="ignore"
                rows={3}
                value={ignoreSelectors}
                onChange={(e) => setIgnoreSelectors(e.target.value)}
                placeholder={".cookie-banner\n#ads"}
              />
            </div>
          ) : null}
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
