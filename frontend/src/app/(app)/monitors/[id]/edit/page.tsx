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
import { usePageTitle } from "@/lib/use-page-title";

function needsJs(mode: MonitorMode): boolean {
	return mode !== "site_links";
}

function showsIgnore(mode: MonitorMode): boolean {
	return mode === "page_content";
}

const MIN_INTERVAL_MIN = 15;
const MAX_INTERVAL_MIN = 24 * 60; // once a day

function parseInterval(raw: string): number | null {
	const n = Number(raw);
	if (!raw.trim() || !Number.isFinite(n)) return null;
	return Math.round(n);
}

function intervalError(minutes: number | null): string | null {
	if (minutes == null) return "Enter a check interval in minutes.";
	if (minutes < MIN_INTERVAL_MIN)
		return `Minimum interval is ${MIN_INTERVAL_MIN} minutes.`;
	if (minutes > MAX_INTERVAL_MIN)
		return `Maximum interval is ${MAX_INTERVAL_MIN} minutes (24h).`;
	return null;
}

export default function EditMonitorPage() {
	usePageTitle("Edit monitor");
	const params = useParams<{ id: string }>();
	const router = useRouter();
	const monitorId = params.id;

	const [workspaceId, setWorkspaceId] = useState<string | null>(null);
	const [monitor, setMonitor] = useState<Monitor | null>(null);
	const [name, setName] = useState("");
	const [url, setUrl] = useState("");
	const [mode, setMode] = useState<MonitorMode>("page_content");
	const [intervalRaw, setIntervalRaw] = useState("60");
	const [timezone, setTimezone] = useState("UTC");
	const [jsRequired, setJsRequired] = useState(false);
	const [watchNote, setWatchNote] = useState("");
	const [ignoreSelectors, setIgnoreSelectors] = useState("");
	const [ignoreRegexes, setIgnoreRegexes] = useState("");
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
				setMode((m.mode as MonitorMode) || "page_content");
				setIntervalRaw(String(m.schedule_interval_minutes));
				setTimezone(m.timezone);
				setJsRequired(Boolean(m.js_required));
				setWatchNote(m.watch_note ?? "");
				setIgnoreSelectors((m.ignore_selectors ?? []).join("\n"));
				setIgnoreRegexes((m.ignore_regexes ?? []).join("\n"));
			} catch (e) {
				if (!cancelled)
					setError(e instanceof Error ? e.message : "Failed to load monitor");
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
		const interval = parseInterval(intervalRaw);
		const intervalProblem = intervalError(interval);
		if (intervalProblem) {
			setError(intervalProblem);
			return;
		}
		setSaving(true);
		setError(null);
		try {
			const ignore = ignoreSelectors
				.split("\n")
				.map((s) => s.trim())
				.filter(Boolean);
			const ignoreRegex = ignoreRegexes
				.split("\n")
				.map((s) => s.trim())
				.filter(Boolean);
			await api.updateMonitor(workspaceId, monitorId, {
				name,
				url,
				mode,
				css_selector: null,
				schedule_interval_minutes: interval!,
				timezone,
				js_required: needsJs(mode) ? jsRequired : false,
				watch_note: watchNote.trim() || null,
				ignore_selectors: ignore,
				ignore_regexes: ignoreRegex,
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
						<Input
							id="name"
							required
							value={name}
							onChange={(e) => setName(e.target.value)}
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
						/>
					</div>
					<div>
						<Label htmlFor="mode">Mode</Label>
						<Select
							id="mode"
							value={mode}
							onChange={(e) => setMode(e.target.value as MonitorMode)}
						>
							<option value="page_content">
								Page content (whole page text)
							</option>
							<option value="site_links">
								Site links (sitemap URL changes)
							</option>
							<option value="product_price">
								Product price (price / currency)
							</option>
						</Select>
					</div>
					<div>
						<Label htmlFor="interval">
							Check interval (minutes, {MIN_INTERVAL_MIN}–{MAX_INTERVAL_MIN})
						</Label>
						<Input
							id="interval"
							type="number"
							min={MIN_INTERVAL_MIN}
							max={MAX_INTERVAL_MIN}
							required
							value={intervalRaw}
							onChange={(e) => setIntervalRaw(e.target.value)}
						/>
						{intervalError(parseInterval(intervalRaw)) &&
						intervalRaw.trim() !== "" ? (
							<p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
								{intervalError(parseInterval(intervalRaw))}
							</p>
						) : null}
					</div>
					<div>
						<Label htmlFor="tz">Timezone</Label>
						<Input
							id="tz"
							value={timezone}
							onChange={(e) => setTimezone(e.target.value)}
						/>
					</div>
					{needsJs(mode) ? (
						<label className="flex cursor-pointer items-center gap-2.5 rounded-lg border border-[var(--border)] bg-slate-50/60 px-3 py-2.5 text-sm text-slate-700 transition hover:border-slate-400 dark:bg-slate-950/40 dark:text-slate-300 dark:hover:border-white/10">
							<input
								type="checkbox"
								checked={jsRequired}
								onChange={(e) => setJsRequired(e.target.checked)}
								className="h-4 w-4 rounded border-slate-400 bg-white text-sky-500 focus:ring-sky-500/30 dark:border-slate-600 dark:bg-slate-900"
							/>
							JavaScript rendering required
						</label>
					) : (
						<p className="rounded-lg border border-sky-500/25 bg-sky-500/10 px-3 py-2 text-xs text-sky-700 dark:border-sky-500/20 dark:bg-sky-500/5 dark:text-sky-200/90">
							Site links mode reads the sitemap over HTTP and watches for added
							or removed URLs.
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
					</div>
					{showsIgnore(mode) ? (
						<>
							<div>
								<Label htmlFor="ignore">
									Ignore CSS selectors (one per line)
								</Label>
								<Textarea
									id="ignore"
									rows={3}
									value={ignoreSelectors}
									onChange={(e) => setIgnoreSelectors(e.target.value)}
								/>
							</div>
							<div className="mt-3">
								<Label htmlFor="ignoreRegex">
									Ignore text by regex (one per line)
								</Label>
								<Textarea
									id="ignoreRegex"
									rows={3}
									value={ignoreRegexes}
									onChange={(e) => setIgnoreRegexes(e.target.value)}
								/>
							</div>
						</>
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
