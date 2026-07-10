"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import {
  Button,
  Card,
  ErrorBox,
  Input,
  Label,
  PageHeader,
  Select,
  Spinner,
  Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import type { Monitor, MonitorMode } from "@/lib/types";
import { ensureWorkspace } from "@/lib/workspace";

function needsPath(mode: MonitorMode): boolean {
  return mode === "css_selector" || mode === "json_field" || mode === "list_items";
}

export default function EditMonitorPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const monitorId = params.id;

  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [monitor, setMonitor] = useState<Monitor | null>(null);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [mode, setMode] = useState<MonitorMode>("whole_page");
  const [cssSelector, setCssSelector] = useState("");
  const [interval, setInterval] = useState(60);
  const [timezone, setTimezone] = useState("UTC");
  const [jsRequired, setJsRequired] = useState(false);
  const [ignoreSelectors, setIgnoreSelectors] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const ws = await ensureWorkspace();
        if (cancelled) return;
        setWorkspaceId(ws);
        const m = await api.getMonitor(ws, monitorId);
        if (cancelled) return;
        setMonitor(m);
        setName(m.name);
        setUrl(m.url);
        setMode((m.mode as MonitorMode) || "whole_page");
        setCssSelector(m.css_selector ?? "");
        setInterval(m.schedule_interval_minutes);
        setTimezone(m.timezone);
        setJsRequired(Boolean(m.js_required));
        setIgnoreSelectors((m.ignore_selectors ?? []).join("\n"));
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load monitor");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [monitorId]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!workspaceId) return;
    setSaving(true);
    setError(null);
    try {
      const ignore = ignoreSelectors
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);
      await api.updateMonitor(workspaceId, monitorId, {
        name,
        url,
        mode,
        css_selector:
          needsPath(mode) || (mode === "visual" && cssSelector) ? cssSelector || null : null,
        schedule_interval_minutes: interval,
        timezone,
        js_required: jsRequired || mode === "visual",
        ignore_selectors: ignore,
      });
      router.push(`/monitors/${monitorId}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update monitor");
      setSaving(false);
    }
  }

  if (loading) return <Spinner />;
  if (!monitor) return <ErrorBox message={error ?? "Monitor not found"} />;

  return (
    <div>
      <PageHeader
        title={`Edit: ${monitor.name}`}
        description="Changing URL, mode, or path creates a new baseline (no alert on next success)."
      />
      {error ? <ErrorBox message={error} /> : null}

      <Card className="max-w-xl">
        <form onSubmit={onSubmit} className="space-y-5">
          <div>
            <Label htmlFor="name">Name</Label>
            <Input id="name" required value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <Label htmlFor="url">URL</Label>
            <Input
              id="url"
              required
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
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
              <option value="css_selector">CSS selector</option>
              <option value="json_field">JSON field</option>
              <option value="list_items">List items</option>
              <option value="visual">Visual</option>
            </Select>
          </div>
          {needsPath(mode) || mode === "visual" ? (
            <div>
              <Label htmlFor="selector">Path / selector</Label>
              <Input
                id="selector"
                required={needsPath(mode)}
                value={cssSelector}
                onChange={(e) => setCssSelector(e.target.value)}
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
            <Label htmlFor="tz">Timezone</Label>
            <Input id="tz" value={timezone} onChange={(e) => setTimezone(e.target.value)} />
          </div>
          {mode !== "visual" ? (
            <label className="flex cursor-pointer items-center gap-2.5 rounded-lg border border-[var(--border)] bg-slate-50/60 px-3 py-2.5 text-sm text-slate-700 transition hover:border-slate-400 dark:bg-slate-950/40 dark:text-slate-300 dark:hover:border-white/10">
              <input
                type="checkbox"
                checked={jsRequired}
                onChange={(e) => setJsRequired(e.target.checked)}
                className="h-4 w-4 rounded border-slate-400 bg-white text-sky-500 focus:ring-sky-500/30 dark:border-slate-600 dark:bg-slate-900"
              />
              JavaScript rendering required
            </label>
          ) : null}
          {mode === "whole_page" || mode === "css_selector" ? (
            <div>
              <Label htmlFor="ignore">Ignore CSS selectors (one per line)</Label>
              <Textarea
                id="ignore"
                rows={3}
                value={ignoreSelectors}
                onChange={(e) => setIgnoreSelectors(e.target.value)}
              />
            </div>
          ) : null}
          <div className="flex gap-2 border-t border-[var(--border)] pt-5">
            <Button type="submit" disabled={saving}>
              {saving ? "Saving…" : "Save changes"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => router.push(`/monitors/${monitorId}`)}
            >
              Cancel
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
