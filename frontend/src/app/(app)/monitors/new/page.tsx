"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
	Button,
	Card,
	ErrorBox,
	Input,
	Label,
	PageHeader,
	SegmentedControl,
	Select,
	Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import type {
	BrandInfo,
	MonitorMode,
	SitemapDiscovery as SitemapDiscoveryResult,
	SitemapImportResult,
} from "@/lib/types";
import { ensureWorkspace } from "@/lib/workspace";
import { usePageTitle } from "@/lib/use-page-title";

const IGNORE_PRESETS: Record<string, string[]> = {
	cookies: [
		".cookie-banner",
		"#cookie-consent",
		"[class*='cookie']",
		"#onetrust-banner-sdk",
	],
	ads: [".ads", ".ad-slot", "[id*='google_ads']", "iframe[src*='doubleclick']"],
	chat: [
		".intercom-lightweight-app",
		"#hubspot-messages-iframe-container",
		"[class*='chat-widget']",
	],
};

/** webdog.ai-parity starter templates — one-click monitor presets. */
const STARTER_TEMPLATES: Array<{
	label: string;
	name: string;
	mode: MonitorMode;
	interval: number;
	urlHint: string;
}> = [
	{ label: "Pricing page", name: "Pricing", mode: "page_content", interval: 60, urlHint: "…/pricing" },
	{ label: "Product price", name: "Product price", mode: "product_price", interval: 1440, urlHint: "…/product" },
	{ label: "Changelog", name: "Changelog", mode: "page_content", interval: 1440, urlHint: "…/changelog" },
	{ label: "Job listings", name: "Jobs", mode: "page_content", interval: 60, urlHint: "…/careers" },
	{ label: "Docs page", name: "Docs", mode: "page_content", interval: 1440, urlHint: "…/docs" },
	{ label: "Site links", name: "Site links", mode: "site_links", interval: 1440, urlHint: "domain.com" },
	{ label: "README", name: "README", mode: "readme", interval: 1440, urlHint: "owner/repo" },
];

const MIN_INTERVAL_MIN = 15;
const MAX_INTERVAL_MIN = 24 * 60; // once a day

/** Parse an interval input; returns null when the value is not usable yet. */
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

function needsJs(mode: MonitorMode): boolean {
	// site_links/readme/rss_field watch over plain HTTP; the others may need a browser.
	return mode !== "site_links" && mode !== "readme" && mode !== "rss_feed";
}

function showsIgnore(mode: MonitorMode): boolean {
	return mode === "page_content";
}

function isReadmeMode(mode: MonitorMode): boolean {
	return mode === "readme";
}

export default function NewMonitorPage() {
	usePageTitle("New monitor");
	const router = useRouter();
	const [createMode, setCreateMode] = useState<"single" | "sitemap">("single");
	const [name, setName] = useState("");
	const [url, setUrl] = useState("");
	const [mode, setMode] = useState<MonitorMode>("page_content");
	const [intervalRaw, setIntervalRaw] = useState("60");
	const [email, setEmail] = useState("");
	const [jsRequired, setJsRequired] = useState(false);
	const [watchNote, setWatchNote] = useState("");
	const [ignoreSelectors, setIgnoreSelectors] = useState("");
	const [ignoreRegexes, setIgnoreRegexes] = useState("");
	const [cssSelector, setCssSelector] = useState<string | null>(null);
	const [runNow, setRunNow] = useState(true);
	const [brand, setBrand] = useState<BrandInfo | null>(null);
	const [brandLoading, setBrandLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [saving, setSaving] = useState(false);

	function normalizeUrl(input: string): string {
		const trimmed = input.trim();
		if (!trimmed) return "";
		if (/^https?:\/\//i.test(trimmed)) return trimmed;
		// readme shorthand like owner/repo must stay as-is
		if (isReadmeMode(mode) && /^[\w.\-]+\/[\w.\-]+$/.test(trimmed)) return trimmed;
		return `https://${trimmed}`;
	}

	const lookupBrand = useCallback(async (rawUrl?: string) => {
		if (isReadmeMode(mode)) return;
		const candidate = normalizeUrl(rawUrl ?? url);
		if (!candidate || candidate.length < 8 || !candidate.includes(".")) return;
		setBrandLoading(true);
		try {
			const ws = await ensureWorkspace();
			const info = await api.brandInfo(ws, candidate);
			setBrand(info);
			if (info.title && !name.trim()) setName(info.title);
		} catch {
			setBrand(null);
		} finally {
			setBrandLoading(false);
		}
	}, [url, name, mode]);

	// Auto-lookup brand on typing with debounce (skip for readme)
	useEffect(() => {
		if (isReadmeMode(mode)) {
			setBrand(null);
			return;
		}
		const candidate = normalizeUrl(url);
		if (!candidate || candidate.length < 8 || !candidate.includes(".")) {
			setBrand(null);
			return;
		}
		const timer = setTimeout(() => {
			lookupBrand(candidate);
		}, 600);
		return () => clearTimeout(timer);
	}, [url, lookupBrand, mode]);

	async function onSubmit(e: FormEvent) {
		e.preventDefault();
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
				name: name.trim() || brand?.title || finalUrl.replace(/^https?:\/\//, ""),
				url: finalUrl,
				mode,
				css_selector: cssSelector || null,
				schedule_interval_minutes: interval!,
				notification_email: email || undefined,
				js_required: needsJs(mode) ? jsRequired : false,
				watch_note: watchNote.trim() || null,
				ignore_selectors: ignore.length ? ignore : null,
				ignore_regexes: ignoreRegex.length ? ignoreRegex : null,
				run_now: runNow,
			});
			// run_now is handled server-side in the same POST to avoid a second
			// round-trip (~0.7s saved). No second await here — navigate immediately.
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
				description="Watch page content, a site's sitemap links, or a product's price."
			/>
			{error ? <ErrorBox message={error} /> : null}

			<div className="mb-5">
				<SegmentedControl
					ariaLabel="Create mode"
					value={createMode}
					onChange={setCreateMode}
					options={[
						{ value: "single", label: "Single URL" },
						{ value: "sitemap", label: "From sitemap" },
					]}
				/>
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
								placeholder="e.g. My monitor name"
							/>
						</div>
						<div>
							<div className="flex items-center justify-between">
								<Label htmlFor="url">URL</Label>
								{brandLoading ? (
									<span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-sky-600 dark:text-sky-400">
										<svg className="size-3 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
											<circle cx="12" cy="12" r="10" strokeOpacity="0.25" />
											<path d="M12 2a10 10 0 0 1 10 10" />
										</svg>
										Discovering brand…
									</span>
								) : null}
							</div>
							<Input
								id="url"
								required
								value={url}
								onBlur={() => lookupBrand()}
								onChange={(e) => setUrl(e.target.value)}
								placeholder={isReadmeMode(mode) ? "owner/repo  or  https://github.com/owner/repo" : "https://example.com/pricing or example.com"}
							/>
							{isReadmeMode(mode) ? (
								<p className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">
									Tracks the repository&apos;s <code>README.md</code> — any doc change on the default branch triggers a diff &amp; alert.
								</p>
							) : null}
						</div>

						{brandLoading ? (
							<div className="flex items-center gap-2.5 rounded-xl border border-sky-500/20 bg-sky-50/40 px-3.5 py-2.5 text-xs text-sky-700 dark:border-sky-500/30 dark:bg-sky-950/20 dark:text-sky-300">
								<svg className="size-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
									<circle cx="12" cy="12" r="10" strokeOpacity="0.25" />
									<path d="M12 2a10 10 0 0 1 10 10" />
								</svg>
								<span>Detecting website title, logo, and metadata…</span>
							</div>
						) : brand ? (
							<div className="overflow-hidden rounded-xl border border-sky-500/20 bg-gradient-to-br from-slate-50 via-white to-sky-50/30 shadow-xs dark:border-sky-500/30 dark:from-slate-900/60 dark:via-slate-950 dark:to-sky-950/20">
								{brand.hero_url ? (
									<div className="relative h-20 w-full overflow-hidden bg-slate-100 dark:bg-slate-900">
										<img
											src={brand.hero_url}
											alt=""
											className="size-full object-cover object-top"
											onError={(e) => {
												(e.target as HTMLElement).parentElement!.style.display = "none";
											}}
										/>
										<div className="absolute inset-0 bg-gradient-to-t from-black/40 to-transparent" />
									</div>
								) : null}
								<div className="flex items-start gap-3 p-3.5">
									{brand.logo_url ? (
										<img
											src={brand.logo_url}
											alt=""
											className="h-10 w-10 shrink-0 rounded-xl border border-[var(--border)] bg-white object-contain p-1 shadow-xs dark:bg-slate-900"
											onError={(e) => {
												(e.target as HTMLElement).style.display = "none";
											}}
										/>
									) : null}
									<div className="min-w-0 flex-1">
										<div className="flex items-center gap-2">
											<p className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">
												{brand.title || "Discovered Brand"}
											</p>
											<span className="rounded-full bg-emerald-500/10 px-2 py-0.2 text-[10px] font-semibold text-emerald-600 dark:bg-emerald-500/20 dark:text-emerald-400">
												Brand Preview
											</span>
										</div>
										{brand.description ? (
											<p className="mt-0.5 line-clamp-2 text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
												{brand.description}
											</p>
										) : (
											<p className="mt-0.5 text-xs text-slate-400">Logo and title detected.</p>
										)}
									</div>
								</div>
							</div>
						) : null}
						<div>
							<Label>Starter templates</Label>
							<div className="flex flex-wrap gap-2">
								{STARTER_TEMPLATES.map((t) => (
									<button
										key={t.label}
										type="button"
										className="rounded-lg border border-[var(--border)] px-2.5 py-1.5 text-xs font-medium capitalize text-slate-600 transition hover:border-sky-400/60 hover:text-sky-600 dark:text-slate-300 dark:hover:text-sky-300"
										onClick={() => {
											if (!name.trim()) setName(t.name);
											setMode(t.mode);
											setIntervalRaw(String(t.interval));
											setJsRequired(t.mode !== "site_links");
										}}
									>
										{t.label}
									</button>
								))}
							</div>
							<p className="mt-1.5 text-xs text-slate-500 dark:text-slate-500">
								Pick a preset to pre-fill the mode and interval, then paste your URL.
							</p>
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
								<option value="list_items">
									List items (e.g. blog/changelog entries)
								</option>
								<option value="json_field">
									JSON field (API / JSON responses)
								</option>
								<option value="readme">
									GitHub README (repo documentation)
								</option>
								<option value="visual">
									Visual diff (screenshot comparison)
								</option>
								</Select>
								{mode === "list_items" ? (
								<p className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">
								List items: watches a list of elements (headlines, posts, entries) and reports what was added or removed as clickable links. Set the target CSS selector below.
								</p>
								) : null}
								{mode === "json_field" ? (
								<p className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">
								JSON field: watches one value inside a JSON response and reports when it changes. Set the JSON path below.
								</p>
								) : null}
								{mode === "readme" ? (
								<p className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">
								README: monitors <code>README.md</code> on the repo&apos;s default branch (main/master). Use <code>vercel/next.js</code> or the full GitHub URL.
								</p>
								) : null}
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
							<Label htmlFor="email">Alert email (optional)</Label>
							<Input
								id="email"
								type="email"
								value={email}
								onChange={(e) => setEmail(e.target.value)}
								placeholder="you@company.com"
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
								JavaScript rendering required (Playwright)
							</label>
						) : mode === "readme" ? (
							<p className="rounded-lg border border-sky-500/25 bg-sky-500/10 px-3 py-2 text-xs text-sky-700 dark:border-sky-500/20 dark:bg-sky-500/5 dark:text-sky-200/90">
								README mode fetches <code>README.md</code> from the repo&apos;s default branch over HTTP.
							</p>
						) : mode === "site_links" ? (
							<p className="rounded-lg border border-sky-500/25 bg-sky-500/10 px-3 py-2 text-xs text-sky-700 dark:border-sky-500/20 dark:bg-sky-500/5 dark:text-sky-200/90">
								Site links mode reads the sitemap over HTTP and watches for
								added or removed URLs.
							</p>
						) : (
							<p className="rounded-lg border border-sky-500/25 bg-sky-500/10 px-3 py-2 text-xs text-sky-700 dark:border-sky-500/20 dark:bg-sky-500/5 dark:text-sky-200/90">
								RSS mode reads the feed over HTTP and watches for added or removed entries.
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
									Ignore CSS selectors (one per line, optional)
								</Label>
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
									<Label htmlFor="ignoreRegex">
										Ignore text by regex (one per line, optional)
									</Label>
									<Textarea
										id="ignoreRegex"
										rows={3}
										value={ignoreRegexes}
										onChange={(e) => setIgnoreRegexes(e.target.value)}
										placeholder={
											"Price updated .* ago\nLast (login|visited): .*"
										}
									/>
									<p className="mt-1 text-xs text-slate-500 dark:text-slate-500">
										Matched text is stripped before diffing — useful for
										timestamps or volatile counters.
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
							<Button
								type="button"
								variant="ghost"
								onClick={() => router.push("/monitors")}
							>
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
	const [siteUrl, setSiteUrl] = useState("");
	const [discovery, setDiscovery] = useState<SitemapDiscoveryResult | null>(
		null,
	);
	const [selected, setSelected] = useState<Set<string>>(new Set());
	const [mode, setMode] = useState<MonitorMode>("site_links");
	const [intervalRaw, setIntervalRaw] = useState("60");
	const [jsRequired, setJsRequired] = useState(false);
	const [ignoreSelectors, setIgnoreSelectors] = useState("");
	const [ignoreRegexes, setIgnoreRegexes] = useState("");
	const [cssSelector, setCssSelector] = useState<string | null>(null);
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
		const interval = parseInterval(intervalRaw);
		const intervalProblem = intervalError(interval);
		if (intervalProblem) {
			setError(intervalProblem);
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
		setCreating(true);
		setError(null);
		setResult(null);
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
			const res = await api.createMonitorsFromSitemap(ws, {
				url: discovery.url,
				urls: [...selected],
				mode,
				css_selector: cssSelector || null,
				schedule_interval_minutes: interval!,
				js_required: needsJs(mode) ? jsRequired : false,
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
						Created {result.created_count} monitor
						{result.created_count === 1 ? "" : "s"}.
					</p>
					{result.skipped.length ? (
						<p className="text-xs text-slate-500 dark:text-slate-500">
							{result.skipped.length} skipped (duplicate URLs already
							monitored).
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
							Reads the site&apos;s sitemap.xml (or robots.txt) and lists the
							pages it contains.
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
									<Button
										type="button"
										variant="ghost"
										size="sm"
										onClick={() => toggleAll(true)}
									>
										Select all
									</Button>
									<Button
										type="button"
										variant="ghost"
										size="sm"
										onClick={() => toggleAll(false)}
									>
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
										<span className="min-w-0 break-all text-slate-700 dark:text-slate-300">
											{u}
										</span>
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
									<Label htmlFor="sm-interval">
										Check interval (minutes, {MIN_INTERVAL_MIN}–
										{MAX_INTERVAL_MIN})
									</Label>
									<Input
										id="sm-interval"
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
							</div>
							{mode === "list_items" || mode === "json_field" ? (
								<div>
									<Label htmlFor="sm-listSelector">
										{mode === "json_field"
											? "JSON path (required for JSON field)"
											: "List CSS selector (required for List items)"}
									</Label>
									<Input
										id="sm-listSelector"
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
												Path to the value to watch on each page, e.g.{" "}
												<code>$.data.price</code>.
											</>
										) : (
											<>
												Select the links to track on each page, e.g.{" "}
												<code>.post-list li a</code>.
											</>
										)}
									</p>
								</div>
							) : null}
							{needsJs(mode) ? (
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

							{showsIgnore(mode) ? (
								<div className="space-y-4">
									<div>
										<Label htmlFor="sm-ignore">
											Ignore CSS selectors (one per line, optional)
										</Label>
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
											id="sm-ignore"
											rows={3}
											value={ignoreSelectors}
											onChange={(e) => setIgnoreSelectors(e.target.value)}
											placeholder={".cookie-banner\n#ads"}
										/>
									</div>
									<div>
										<Label htmlFor="sm-ignoreRegex">
											Ignore text by regex (one per line, optional)
										</Label>
										<Textarea
											id="sm-ignoreRegex"
											rows={3}
											value={ignoreRegexes}
											onChange={(e) => setIgnoreRegexes(e.target.value)}
											placeholder={
												"Price updated .* ago\nLast (login|visited): .*"
											}
										/>
										<p className="mt-1 text-xs text-slate-500 dark:text-slate-500">
											Matched text is stripped before diffing — useful for
											timestamps or volatile counters.
										</p>
									</div>
								</div>
							) : null}

							<div className="flex gap-2 border-t border-[var(--border)] pt-5">
								<Button
									type="button"
									onClick={onCreate}
									disabled={creating || selected.size === 0}
								>
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
