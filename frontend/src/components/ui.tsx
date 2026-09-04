"use client";

import {
	type ButtonHTMLAttributes,
	type InputHTMLAttributes,
	type ReactNode,
	type SelectHTMLAttributes,
	type TextareaHTMLAttributes,
	useEffect,
	useState,
} from "react";

export function cn(...parts: Array<string | false | null | undefined>) {
	return parts.filter(Boolean).join(" ");
}

export function Button({
	className,
	variant = "primary",
	size = "md",
	...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
	variant?: "primary" | "secondary" | "danger" | "ghost";
	size?: "sm" | "md" | "lg";
	ref?: React.Ref<HTMLButtonElement>;
}) {
	const styles = {
		primary:
			"bg-[var(--fg)] text-[var(--bg)] hover:bg-[var(--fg-2)] border border-transparent dark:bg-white dark:text-black dark:hover:bg-neutral-200",
		secondary:
			"bg-transparent text-[var(--fg)] border border-[var(--border)] hover:text-[var(--accent)] hover:border-[var(--accent)] hover:opacity-80",
		danger:
			"bg-[var(--danger)] text-white hover:opacity-90 border border-transparent shadow-sm",
		ghost:
			"bg-transparent text-[var(--fg)] hover:text-[var(--accent)] hover:opacity-80 border border-transparent",
	}[variant];

	const sizes = {
		sm: "px-2.5 py-1.5 text-xs",
		md: "px-3.5 py-2 text-sm",
		lg: "px-5 py-2.5 text-sm",
	}[size];

	return (
		<button
			className={cn(
				"inline-flex items-center justify-center gap-1.5 rounded-full font-normal transition",
				"focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-1",
				"disabled:pointer-events-none disabled:opacity-45",
				styles,
				sizes,
				className,
			)}
			{...props}
		/>
	);
}

export function Input({
	className,
	...props
}: InputHTMLAttributes<HTMLInputElement>) {
	return <input className={cn("field", className)} {...props} />;
}

export function Textarea({
	className,
	...props
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
	return <textarea className={cn("field resize-y", className)} {...props} />;
}

export function Select({
	className,
	children,
	...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
	return (
		<div className="relative">
			<select
				className={cn("field appearance-none pr-8", className)}
				{...props}
			>
				{children}
			</select>
			<svg
				className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 dark:text-slate-500"
				fill="none"
				viewBox="0 0 24 24"
				stroke="currentColor"
				strokeWidth={2}
				strokeLinecap="round"
				strokeLinejoin="round"
				aria-hidden="true"
			>
				<path d="m6 9 6 6 6-6" />
			</svg>
		</div>
	);
}

export function Label({
	children,
	htmlFor,
}: {
	children: ReactNode;
	htmlFor?: string;
}) {
	return (
		<label
			htmlFor={htmlFor}
			className="mb-1.5 block text-xs font-medium uppercase tracking-[0.12em] text-[var(--muted)]"
		>
			{children}
		</label>
	);
}

export function Card({
	children,
	className,
	hover = false,
}: {
	children: ReactNode;
	className?: string;
	hover?: boolean;
}) {
	return (
		<div
			className={cn(
				"glass-card",
				hover && "transition hover:border-[var(--border)]",
				className,
			)}
			suppressHydrationWarning
		>
			{children}
		</div>
	);
}

export function Badge({
	children,
	tone = "neutral",
	title,
}: {
	children: ReactNode;
	tone?: "neutral" | "success" | "danger" | "warn" | "info";
	title?: string;
}) {
	const styles = {
		neutral:
			"bg-[var(--surface)] text-[var(--muted)] ring-1 ring-[var(--border)]",
		success:
			"bg-emerald-500/10 text-emerald-700 ring-1 ring-emerald-500/25 dark:text-emerald-300",
		danger:
			"bg-rose-500/10 text-rose-700 ring-1 ring-rose-500/25 dark:text-rose-300",
		warn: "bg-amber-500/10 text-amber-700 ring-1 ring-amber-500/25 dark:text-amber-200",
		info: "bg-[var(--accent)]/10 text-[var(--accent)] ring-1 ring-[var(--accent)]/25",
	}[tone];
	return (
		<span
			title={title}
			className={cn(
				"inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide",
				styles,
			)}
		>
			{children}
		</span>
	);
}

export function PageHeader({
	title,
	description,
	actions,
}: {
	title: string;
	description?: ReactNode;
	actions?: ReactNode;
}) {
	return (
		<div className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
			<div className="min-w-0">
				<h1 className="font-display text-3xl tracking-tight text-[var(--fg)] sm:text-[48px] sm:leading-[1.2]">
					{title}
				</h1>
				{description ? (
					<p className="mt-1.5 max-w-2xl text-base leading-relaxed text-[var(--muted)]">
						{description}
					</p>
				) : null}
			</div>
			{actions ? (
				<div className="flex shrink-0 flex-wrap items-center gap-2">
					{actions}
				</div>
			) : null}
		</div>
	);
}

export function EmptyState({
	title,
	body,
	action,
	icon,
}: {
	title: string;
	body: string;
	action?: ReactNode;
	icon?: ReactNode;
}) {
	return (
		<Card className="flex flex-col items-center py-12 text-center">
			<div className="mb-4 flex h-12 w-12 items-center justify-center rounded-[22px] bg-[var(--surface)] text-[var(--fg)] ring-1 ring-[var(--border-soft)]">
				{icon ?? (
					<svg
						className="h-6 w-6"
						fill="none"
						viewBox="0 0 24 24"
						stroke="currentColor"
						strokeWidth={1.5}
					>
						<path
							strokeLinecap="round"
							strokeLinejoin="round"
							d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
						/>
					</svg>
				)}
			</div>
			<p className="text-base font-medium text-[var(--fg)]">{title}</p>
			<p className="mt-1.5 max-w-sm text-sm text-[var(--muted)]">{body}</p>
			{action ? <div className="mt-5">{action}</div> : null}
		</Card>
	);
}

export function ErrorBox({ message }: { message: string }) {
	return (
		<div className="mb-4 flex items-start gap-2.5 rounded-xl border border-rose-500/30 bg-rose-500/10 px-3.5 py-3 text-sm text-rose-700 dark:border-rose-500/25 dark:text-rose-200">
			<svg
				className="mt-0.5 h-4 w-4 shrink-0"
				fill="none"
				viewBox="0 0 24 24"
				stroke="currentColor"
				strokeWidth={2}
			>
				<path
					strokeLinecap="round"
					strokeLinejoin="round"
					d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z"
				/>
			</svg>
			<span>{message}</span>
		</div>
	);
}

export function SuccessBox({ message }: { message: string }) {
	return (
		<div className="mb-4 flex items-start gap-2.5 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-3.5 py-3 text-sm text-emerald-700 dark:border-emerald-500/25 dark:text-emerald-200">
			<svg
				className="mt-0.5 h-4 w-4 shrink-0"
				fill="none"
				viewBox="0 0 24 24"
				stroke="currentColor"
				strokeWidth={2}
			>
				<path
					strokeLinecap="round"
					strokeLinejoin="round"
					d="m4.5 12.75 6 6 9-13.5"
				/>
			</svg>
			<span>{message}</span>
		</div>
	);
}

export function Spinner({
	label = "Loading…",
	delayMs = 150,
}: {
	label?: string;
	delayMs?: number;
}) {
	// Delay showing the spinner so sub-second loads don't flash a loading state.
	const [visible, setVisible] = useState(delayMs <= 0);
	useEffect(() => {
		if (delayMs <= 0) return;
		const t = setTimeout(() => setVisible(true), delayMs);
		return () => clearTimeout(t);
	}, [delayMs]);

	if (!visible) return null;

	// suppressHydrationWarning: extensions may inject attrs (e.g. rtrvr-ls) before hydrate
	return (
		<div
			className="flex flex-col items-center justify-center gap-3 py-16"
			suppressHydrationWarning
		>
			<div
				className="h-8 w-8 animate-spin rounded-full border-2 border-[var(--border)] border-t-[var(--fg)]"
				suppressHydrationWarning
			/>
			<p
				className="text-sm text-[var(--muted)]"
				suppressHydrationWarning
			>
				{label}
			</p>
		</div>
	);
}

export function StatCard({
	label,
	value,
	hint,
	progress,
}: {
	label: string;
	value: ReactNode;
	hint?: string;
	progress?: number | null;
}) {
	const pct =
		progress != null && Number.isFinite(progress)
			? Math.max(0, Math.min(100, progress))
			: null;

	return (
		<Card className="relative overflow-hidden">
			<p className="section-label">{label}</p>
			<p className="mt-3 font-display text-3xl tracking-tight text-[var(--fg)]">
				{value}
			</p>
			{hint ? (
				<p className="mt-1.5 text-xs text-[var(--muted)]">{hint}</p>
			) : null}
			{pct != null ? (
				<div className="mt-4 h-1.5 overflow-hidden rounded-full bg-[var(--border-soft)]">
					<div
						className="h-full rounded-full bg-[var(--fg)] transition-all"
						style={{ width: `${pct}%` }}
					/>
				</div>
			) : null}
		</Card>
	);
}

export function SectionTitle({
	children,
	action,
}: {
	children: ReactNode;
	action?: ReactNode;
}) {
	return (
		<div className="mb-3 flex items-center justify-between gap-3">
			<h2 className="section-label">{children}</h2>
			{action}
		</div>
	);
}

const segmentedBtn =
	"rounded-lg px-3 py-1.5 text-sm transition " +
	"focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]";

/**
 * Single styled toggle group for 2+ mutually exclusive options.
 * Renders as a segmented control with `aria-pressed` on each option.
 */
export function SegmentedControl<T extends string>({
	options,
	value,
	onChange,
	ariaLabel,
	className,
}: {
	options: ReadonlyArray<{ value: T; label: ReactNode }>;
	value: T;
	onChange: (next: T) => void;
	ariaLabel?: string;
	className?: string;
}) {
	return (
		<div
			role="group"
			aria-label={ariaLabel}
			className={cn(
				"inline-flex flex-wrap gap-1 rounded-lg border border-[var(--border)] bg-[var(--surface-bg)] p-0.5",
				className,
			)}
		>
			{options.map((opt) => {
				const active = opt.value === value;
				return (
					<button
						key={opt.value}
						type="button"
						aria-pressed={active}
						onClick={() => onChange(opt.value)}
						className={cn(
							segmentedBtn,
							active
								? "bg-[var(--fg)] text-[var(--bg)] dark:bg-white dark:text-black"
								: "border border-transparent text-[var(--muted)] hover:text-[var(--accent)]",
						)}
					>
						{opt.label}
					</button>
				);
			})}
		</div>
	);
}

export function DataTable({
	headers,
	children,
	empty,
}: {
	headers: string[];
	children: ReactNode;
	empty?: ReactNode;
}) {
	return (
		<div className="surface overflow-hidden">
			<div className="relative">
				<div className="datatable-scroll overflow-x-auto">
					<table className="w-full text-left text-sm">
						<thead>
							<tr className="border-b border-[var(--border)] bg-[var(--surface-bg)]">
								{headers.map((h) => (
									<th
										key={h}
										className="whitespace-nowrap px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--muted)]"
									>
										{h}
									</th>
								))}
							</tr>
						</thead>
						<tbody className="divide-y divide-[var(--border)]">{children}</tbody>
					</table>
				</div>
				<div aria-hidden className="datatable-edge md:hidden" />
			</div>
			{empty}
		</div>
	);
}

export function ModeBadge({ mode }: { mode: string }) {
	const labels: Record<string, string> = {
		page_content: "Page content",
		site_links: "Site links",
		product_price: "Product price",
		list_items: "List items",
		json_field: "JSON field",
		rss_feed: "RSS feed",
		readme: "GitHub README",
		visual: "Visual diff",
	};
	return <Badge tone="info">{labels[mode] ?? mode}</Badge>;
}

export function CategoryBadge({ category }: { category: string | null | undefined }) {
	if (!category) return null;
	const toneMap: Record<string, "neutral" | "success" | "danger" | "warn" | "info"> = {
		pricing: "warn",
		availability: "success",
		legal: "info",
		security: "danger",
		design: "neutral",
		api: "info",
		content: "neutral",
		other: "neutral",
	};
	const tone = toneMap[category.toLowerCase()] ?? "neutral";
	return <Badge tone={tone}>{category}</Badge>;
}

export function ImpactBadge({ impact }: { impact: string | null | undefined }) {
	if (!impact) return null;
	const t = impact.toLowerCase();
	const tone: "neutral" | "success" | "danger" | "warn" | "info" =
		t === "critical" ? "danger" : t === "high" ? "warn" : t === "medium" ? "info" : "neutral";
	return <Badge tone={tone}>impact: {t}</Badge>;
}

export function parseImpact(summary: string | null | undefined): string | null {
	if (!summary) return null;
	const m = summary.match(/\(impact:\s*(low|medium|high|critical)\)/i);
	return m ? m[1].toLowerCase() : null;
}

export function stripImpact(summary: string): string {
	return summary.replace(/\s*\(impact:\s*(low|medium|high|critical)\)\s*$/i, "").trim();
}
