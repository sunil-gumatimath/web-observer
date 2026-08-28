"use client";

import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";
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
import { api, brandAssetUrl } from "@/lib/api";
import type { BrandInfo, Monitor, MonitorMode } from "@/lib/types";
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
	const [cssSelector, setCssSelector] = useState<string | null>(null);
	const [brand, setBrand] = useState<{
		title?: string | null;
		description?: string | null;
		logo_url?: string | null;
		hero_url?: string | null;
	} | null>(null);
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
				setCssSelector(m.css_selector ?? null);
				if (m.brand) {
					setBrand({
						title: m.brand.title,
						description: m.brand.description,
						logo_url: brandAssetUrl(m.brand.logo_path) || m.brand.logo_url,
						hero_url: brandAssetUrl(m.brand.hero_path) || m.brand.hero_url,
					});
				}
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

	function normalizeUrl(input: string): string {
		const trimmed = input.trim();
		if (!trimmed) return "";
		if (/^https?:\/\//i.test(trimmed)) return trimmed;
		return `https://${trimmed}`;
	}

	const lookupBrand = useCallback(async (rawUrl?: string) => {
		const candidate = normalizeUrl(rawUrl ?? url);
		if (!candidate || candidate.length < 8 || !candidate.includes(".")) return;
		try {
			const ws = await ensureWorkspace();
			const info = await api.brandInfo(ws, candidate);
			setBrand(info);
			if (info.title && !name.trim()) setName(info.title);
		} catch {
			// keep current brand
		}
	}, [url, name]);

	// Auto-lookup brand on URL change with debounce
	useEffect(() => {
		const candidate = normalizeUrl(url);
		if (!candidate || candidate.length < 8 || !candidate.includes(".")) return;
		const timer = setTimeout(() => {
			lookupBrand(candidate);
		}, 600);
		return () => clearTimeout(timer);
	}, [url, lookupBrand]);

	async function onSubmit(e: FormEvent) {
		e.preventDefault();
		if (!workspaceId) return;
		const interval = parseInterval(intervalRaw);
		const intervalProblem = intervalError(interval);
		if (intervalProblem) {
			setError(intervalProblem);
			return;
		}
		const finalUrl = normalizeUrl(url);
		if (!finalUrl) {
			setError("A valid URL is required.");
			return;
		}
		const needsPath = mode === "list_items" || mode === "json_field";
		if (needsPath && !cssSelector?.trim()) {
			setError(
				mode === "list_items"
					? "List items mode requires a CSS selector."
					: "JSON field mode requires a JSON path.",
			);
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
				css_selector: cssSelector || null,
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
							onBlur={() => lookupBrand()}
							onChange={(e) => setUrl(e.target.value)}
						/>
					</div>
					{brand ? (
						<div className="rounded-xl border border-[var(--border)] bg-slate-50/60 p-3.5 dark:bg-slate-950/40">
							<div className="flex items-start gap-3">
								{brand.logo_url ? (
									<img
										src={brand.logo_url}
										alt=""
										className="h-9 w-9 rounded-lg object-contain border border-[var(--border)] bg-white p-0.5 dark:bg-slate-900"
									/>
								) : null}
								<div className="min-w-0 flex-1">
									{brand.title ? (
										<p className="truncate text-sm font-medium text-slate-900 dark:text-slate-100">
											{brand.title}
										</p>
									) : null}
									{brand.description ? (
										<p className="mt-0.5 line-clamp-2 text-xs text-slate-500 dark:text-slate-400">
											{brand.description}
										</p>
									) : (
										<p className="text-xs text-slate-400">No brand description detected.</p>
									)}
								</div>
							</div>
							{brand.hero_url ? (
								<div className="mt-3 overflow-hidden rounded-lg border border-[var(--border)]">
									<img
										src={brand.hero_url}
										alt="Website thumbnail preview"
										className="max-h-48 w-full object-cover object-top"
									/>
								</div>
							) : null}
						</div>
					) : null}
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
							<option value="list_items">
								List items (e.g. blog/changelog entries)
							</option>
							<option value="json_field">
								JSON field (API / JSON responses)
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
{mode === "list_items" || mode === "json_field" ? (
					<div>
						<Label htmlFor="listSelector">
							{mode === "json_field"
								? "JSON path (required for JSON field)"
								: "List CSS selector (required for List items)"}
						</Label>
						<Input
							id="listSelector"
							required
							value={cssSelector ?? ""}
							onChange={(e) => setCssSelector(e.target.value || null)}
							placeholder={
								mode === "json_field" ? "$.data.price" : "article h2 a, .post-title a"
							}
						/>
						<p className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">
							{mode === "json_field" ? (
								<>
									Path to the value to watch, e.g. <code>$.data.price</code> or{" "}
									<code>$.results[0].status</code>.
								</>
							) : (
								<>
									Select the links to track, e.g. <code>.post-list li a</code>.
								</>
							)}
						</p>
					</div>
				) : null}
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
