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
import { ThresholdEditor } from "@/components/threshold-editor";
import { SelectorPicker } from "@/components/selector-picker";
import { api } from "@/lib/api";
import type {
	BrandInfo,
	MonitorMode,
	SitemapDiscovery as SitemapDiscoveryResult,
	SitemapImportResult,
} from "@/lib/types";
import {
	isReadmeMode,
	MONITOR_MODE_OPTIONS,
	needsJs,
	requiresSelector,
	SITEMAP_IMPORT_MODES,
	selectorHelp,
	selectorLabel,
	selectorPlaceholder,
	showsIgnore,
	showsSelector,
} from "@/lib/modes";
import { ensureWorkspace } from "@/lib/workspace";
import { usePageTitle } from "@/lib/use-page-title";

function normalizeUrl(input: string, mode?: MonitorMode): string {
	const trimmed = input.trim();
	if (!trimmed) return "";
	if (/^https?:\/\//i.test(trimmed)) return trimmed;
	// readme shorthand like owner/repo must stay as-is
	if (mode && isReadmeMode(mode) && /^[\w.\-]+\/[\w.\-]+$/.test(trimmed)) return trimmed;
	return `https://${trimmed}`;
}

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
}> = [
	{ label: "Pricing page", name: "Pricing", mode: "page_content", interval: 60 },
	{ label: "Product price", name: "Product price", mode: "product_price", interval: 1440 },
	{ label: "Changelog", name: "Changelog", mode: "page_content", interval: 1440 },
	{ label: "Job listings", name: "Jobs", mode: "page_content", interval: 60 },
	{ label: "Docs page", name: "Docs", mode: "page_content", interval: 1440 },
	{ label: "Site links", name: "Site links", mode: "site_links", interval: 1440 },
	{ label: "README", name: "README", mode: "readme", interval: 1440 },
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
	const [semanticTrigger, setSemanticTrigger] = useState("");
	const [ignoreSelectors, setIgnoreSelectors] = useState("");
	const [ignoreRegexes, setIgnoreRegexes] = useState("");
	const [cssSelector, setCssSelector] = useState<string | null>(null);
	const [pickerOpen, setPickerOpen] = useState(false);
	const [alertConfig, setAlertConfig] = useState<Record<string, unknown> | null>(null);
	const [runNow, setRunNow] = useState(true);
	const [brand, setBrand] = useState<BrandInfo | null>(null);
	const [brandLoading, setBrandLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [saving, setSaving] = useState(false);

	const lookupBrand = useCallback(async (rawUrl?: string) => {
		if (isReadmeMode(mode)) return;
		const candidate = normalizeUrl(rawUrl ?? url, mode);
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
			const timer = setTimeout(() => setBrand(null), 0);
			return () => clearTimeout(timer);
		}
		const candidate = normalizeUrl(url, mode);
		if (!candidate || candidate.length < 8 || !candidate.includes(".")) {
			const timer = setTimeout(() => setBrand(null), 0);
			return () => clearTimeout(timer);
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
		const finalUrl = normalizeUrl(url, mode);
		if (!finalUrl) {
			setError("A valid URL is required.");
			return;
		}
		const needsPath = requiresSelector(mode);
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
				js_required: mode === "visual" ? true : needsJs(mode) ? jsRequired : false,
				watch_note: watchNote.trim() || null,
				semantic_trigger: semanticTrigger.trim() || null,
				ignore_selectors: ignore.length ? ignore : null,
				ignore_regexes: ignoreRegex.length ? ignoreRegex : null,
				...(alertConfig && Object.keys(alertConfig).length > 0
					? { alert_config: alertConfig }
					: {}),
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
									<span className="inline-flex items-center gap-1.5 text-[11px] font-medium text-[var(--primary)]">
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
								<p className="mt-1.5 text-xs text-[var(--ink-subtle)]">
									Tracks the repository&apos;s <code>README.md</code> — any doc change on the default branch triggers a diff &amp; alert.
								</p>
							) : null}
						</div>

						{brandLoading ? (
							<div className="flex items-center gap-2.5 rounded-lg border border-[var(--hairline)] bg-[var(--surface-2)] px-3.5 py-2.5 text-xs text-[var(--ink-subtle)]">
								<svg className="size-3.5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
									<circle cx="12" cy="12" r="10" strokeOpacity="0.25" />
									<path d="M12 2a10 10 0 0 1 10 10" />
								</svg>
								<span>Detecting website title, logo, and metadata…</span>
							</div>
						) : brand ? (
							<div className="overflow-hidden rounded-[12px] border border-[var(--hairline)] bg-[var(--surface-1)]">
								{brand.hero_url ? (
									<div className="relative h-20 w-full overflow-hidden bg-[var(--surface-2)]">
										<img
											src={brand.hero_url}
											alt=""
											className="size-full object-cover object-top"
											onError={(e) => {
												(e.target as HTMLElement).parentElement!.style.display = "none";
											}}
										/>
										<div className="absolute inset-0 bg-[#010102]/20" />
									</div>
								) : null}
								<div className="flex items-start gap-3 p-3.5">
									{brand.logo_url ? (
										<img
											src={brand.logo_url}
											alt=""
											className="h-10 w-10 shrink-0 rounded-[8px] border border-[var(--hairline)] bg-[var(--surface-1)] object-contain p-1"
											onError={(e) => {
												(e.target as HTMLElement).style.display = "none";
											}}
										/>
									) : null}
									<div className="min-w-0 flex-1">
										<div className="flex items-center gap-2">
											<p className="truncate text-sm font-semibold text-[var(--fg)]">
												{brand.title || "Discovered Brand"}
											</p>
											<span className="rounded-full bg-[var(--semantic-success)]/10 px-2 py-0.5 text-[10px] font-semibold text-[var(--semantic-success)]">
												Brand Preview
											</span>
										</div>
										{brand.description ? (
											<p className="mt-0.5 line-clamp-2 text-xs text-[var(--ink-muted)] leading-relaxed">
												{brand.description}
											</p>
										) : (
											<p className="mt-0.5 text-xs text-[var(--ink-subtle)]">Logo and title detected.</p>
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
										className="rounded-lg border border-[var(--hairline)] px-2.5 py-1.5 text-xs font-medium capitalize text-[var(--ink-muted)] transition hover:border-[var(--hairline-strong)] hover:text-[var(--ink)] hover:bg-[var(--surface-2)]"
										onClick={() => {
											if (!name.trim()) setName(t.name);
											setMode(t.mode);
											setIntervalRaw(String(t.interval));
											setJsRequired(needsJs(t.mode));
										}}
									>
										{t.label}
									</button>
								))}
							</div>
							<p className="mt-1.5 text-xs text-[var(--ink-subtle)]">
								Pick a preset to pre-fill the mode and interval, then paste your URL.
							</p>
						</div>
						<div>
							<Label htmlFor="mode">Mode</Label>
							<Select
								id="mode"
								value={mode}
								onChange={(e) => {
									const m = e.target.value as MonitorMode;
									setMode(m);
									if (!needsJs(m)) setJsRequired(false);
								}}
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
								<option value="rss_feed">
									RSS feed (added or removed entries)
								</option>
								<option value="readme">
									GitHub README (repo documentation)
								</option>
								<option value="visual">
									Visual diff (screenshot comparison)
								</option>
								</Select>
								{mode === "list_items" ? (
								<p className="mt-1.5 text-xs text-[var(--ink-subtle)]">
								List items: watches a list of elements (headlines, posts, entries) and reports what was added or removed as clickable links. Set the target CSS selector below.
								</p>
								) : null}
								{mode === "json_field" ? (
								<p className="mt-1.5 text-xs text-[var(--ink-subtle)]">
								JSON field: watches one value inside a JSON response and reports when it changes. Set the JSON path below.
								</p>
								) : null}
								{mode === "readme" ? (
								<p className="mt-1.5 text-xs text-[var(--ink-subtle)]">
								README: monitors <code>README.md</code> on the repo&apos;s default branch (main/master). Use <code>vercel/next.js</code> or the full GitHub URL.
								</p>
								) : null}
								{mode === "rss_feed" ? (
								<p className="mt-1.5 text-xs text-[var(--ink-subtle)]">
								RSS feed: watches an RSS/Atom feed and reports added or removed entries, matched on GUID/link. The feed is fetched over plain HTTP.
								</p>
								) : null}
								{mode === "visual" ? (
								<p className="mt-1.5 text-xs text-[var(--ink-subtle)]">
								Visual diff: renders the page in a real browser and compares screenshots perceptively. Set an optional CSS selector below to compare only part of the page.
								</p>
								) : null}
								{mode === "product_price" ? (
								<p className="mt-1.5 text-xs text-[var(--ink-subtle)]">
								Product price: watches the price on a product page. Set an optional CSS selector below to narrow the price search.
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
								<p className="mt-1 text-xs text-[var(--warning)]">
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
							<label className="flex cursor-pointer items-center gap-2.5 rounded-lg border border-[var(--hairline)] bg-[var(--surface-1)] px-3 py-2.5 text-sm text-[var(--ink)] transition hover:border-[var(--hairline-strong)]">
								<input
									type="checkbox"
									checked={mode === "visual" ? true : jsRequired}
									disabled={mode === "visual"}
									onChange={(e) => setJsRequired(e.target.checked)}
									className="h-4 w-4 rounded-[4px] border-[var(--hairline-strong)] bg-[var(--surface-1)] text-[var(--primary)] focus:ring-[var(--primary-focus)]"
								/>
								JavaScript rendering required (Playwright)
								{mode === "visual" ? (
									<span className="text-xs text-[var(--ink-subtle)]">
										— always on for visual diff
									</span>
								) : null}
							</label>
						) : mode === "readme" ? (
							<p className="rounded-lg border border-[var(--hairline)] bg-[var(--surface-2)] px-3 py-2 text-xs text-[var(--ink-subtle)]">
								README mode fetches <code>README.md</code> from the repo&apos;s default branch over HTTP.
							</p>
						) : mode === "site_links" ? (
							<p className="rounded-lg border border-[var(--hairline)] bg-[var(--surface-2)] px-3 py-2 text-xs text-[var(--ink-subtle)]">
								Site links mode reads the sitemap over HTTP and watches for
								added or removed URLs.
							</p>
						) : (
							<p className="rounded-lg border border-[var(--hairline)] bg-[var(--surface-2)] px-3 py-2 text-xs text-[var(--ink-subtle)]">
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
							<p className="mt-1 text-xs text-[var(--ink-subtle)]">
								Focuses AI summaries and helps you remember intent.
							</p>
						</div>
						<div>
							<Label htmlFor="semanticTrigger">Semantic alert condition (optional)</Label>
							<Input
								id="semanticTrigger"
								value={semanticTrigger}
								onChange={(e) => setSemanticTrigger(e.target.value)}
								placeholder="e.g. Alert only if pricing increases or a new tier is added"
							/>
							<p className="mt-1 text-xs text-[var(--ink-subtle)]">
								Requires a configured LLM. Non-matching changes are filtered out; if AI evaluation is unavailable or fails, the change is allowed through (fail-open).
							</p>
						</div>
						<ThresholdEditor mode={mode} value={alertConfig} onChange={setAlertConfig} />
{showsSelector(mode) ? (
					<div>
						<Label htmlFor="listSelector">{selectorLabel(mode)}</Label>
						<Input
							id="listSelector"
							required={requiresSelector(mode)}
							value={cssSelector ?? ""}
							onChange={(e) => setCssSelector(e.target.value || null)}
							placeholder={selectorPlaceholder(mode)}
						/>
						{mode === "list_items" ? (
							<button
								type="button"
								onClick={() => setPickerOpen(true)}
								className="mt-1.5 text-xs font-medium text-[var(--primary)] underline-offset-2 hover:underline"
							>
								Pick element visually instead
							</button>
						) : null}
						<p className="mt-1.5 text-xs text-[var(--ink-subtle)]">
							{selectorHelp(mode)}
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
												className="rounded-md border border-[var(--hairline)] px-2 py-1 text-xs capitalize text-[var(--ink-muted)] hover:bg-[var(--surface-2)] hover:text-[var(--ink)]"
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
									<p className="mt-1 text-xs text-[var(--ink-subtle)]">
										Matched text is stripped before diffing — useful for
										timestamps or volatile counters.
									</p>
								</div>
							</>
						) : null}
						<label className="flex items-center gap-2 text-sm text-[var(--ink-muted)]">
							<input
								type="checkbox"
								checked={runNow}
								onChange={(e) => setRunNow(e.target.checked)}
								className="h-4 w-4 rounded-[4px] border-[var(--hairline-strong)] bg-[var(--surface-1)] text-[var(--primary)] focus:ring-[var(--primary-focus)]"
							/>
							Run first check immediately (see result, then keep or delete)
						</label>
						<div className="flex gap-2 border-t border-[var(--hairline)] pt-5">
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
					<SelectorPicker
						open={pickerOpen}
						initialUrl={normalizeUrl(url, mode)}
						onClose={() => setPickerOpen(false)}
						onPick={(sel) => {
							setCssSelector(sel);
							setPickerOpen(false);
						}}
					/>
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
		const needsPath = requiresSelector(mode);
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
				js_required: mode === "visual" ? true : needsJs(mode) ? jsRequired : false,
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
					<p className="text-sm font-medium text-[var(--semantic-success)]">
						Created {result.created_count} monitor
						{result.created_count === 1 ? "" : "s"}.
					</p>
					{result.skipped.length ? (
						<p className="text-xs text-[var(--ink-subtle)]">
							{result.skipped.length} skipped (duplicate URLs already
							monitored).
						</p>
					) : null}
					{result.errors.length ? (
						<p className="text-xs text-[var(--danger)]">
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
						<p className="text-xs text-[var(--ink-subtle)]">
							Reads the site&apos;s sitemap.xml (or robots.txt) and lists the
							pages it contains.
						</p>
					</div>

					{error ? <ErrorBox message={error} /> : null}

					{discovery ? (
						<div className="space-y-4">
							<div className="flex items-center justify-between gap-3">
								<p className="text-sm text-[var(--ink-subtle)]">
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
							<div className="max-h-72 space-y-1 overflow-y-auto rounded-lg border border-[var(--hairline)] bg-[var(--surface-1)] p-2">
								{discovery.urls.map((u) => (
									<label
										key={u}
										className="flex cursor-pointer items-start gap-2.5 rounded-md px-2 py-1.5 text-sm hover:bg-[var(--surface-2)]"
									>
										<input
											type="checkbox"
											checked={selected.has(u)}
											onChange={() => toggleOne(u)}
											className="mt-0.5 h-4 w-4 rounded-[4px] border-[var(--hairline-strong)] bg-[var(--surface-1)] text-[var(--primary)] focus:ring-[var(--primary-focus)]"
										/>
										<span className="min-w-0 break-all text-[var(--ink)]">
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
										{MONITOR_MODE_OPTIONS.filter((o) =>
											SITEMAP_IMPORT_MODES.includes(o.value),
										).map((o) => (
											<option key={o.value} value={o.value}>
												{o.optionLabel}
											</option>
										))}
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
										<p className="mt-1 text-xs text-[var(--warning)]">
											{intervalError(parseInterval(intervalRaw))}
										</p>
									) : null}
								</div>
							</div>
							{showsSelector(mode) ? (
								<div>
									<Label htmlFor="sm-listSelector">{selectorLabel(mode)}</Label>
									<Input
										id="sm-listSelector"
										required={requiresSelector(mode)}
										value={cssSelector ?? ""}
										onChange={(e) => setCssSelector(e.target.value || null)}
										placeholder={selectorPlaceholder(mode)}
									/>
									<p className="mt-1.5 text-xs text-[var(--ink-subtle)]">
										{selectorHelp(mode)}
									</p>
								</div>
							) : null}
							{needsJs(mode) ? (
								<label className="flex cursor-pointer items-center gap-2.5 rounded-lg border border-[var(--hairline)] bg-[var(--surface-1)] px-3 py-2.5 text-sm text-[var(--ink)] transition hover:border-[var(--hairline-strong)]">
									<input
										type="checkbox"
										checked={jsRequired}
										onChange={(e) => setJsRequired(e.target.checked)}
										className="h-4 w-4 rounded-[4px] border-[var(--hairline-strong)] bg-[var(--surface-1)] text-[var(--primary)] focus:ring-[var(--primary-focus)]"
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
													className="rounded-md border border-[var(--hairline)] px-2 py-1 text-xs capitalize text-[var(--ink-muted)] hover:bg-[var(--surface-2)] hover:text-[var(--ink)]"
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
										<p className="mt-1 text-xs text-[var(--ink-subtle)]">
											Matched text is stripped before diffing — useful for
											timestamps or volatile counters.
										</p>
									</div>
								</div>
							) : null}

							<div className="flex gap-2 border-t border-[var(--hairline)] pt-5">
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
