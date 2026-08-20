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
			"bg-gradient-to-b from-sky-500 to-sky-600 text-white shadow-glow-sm hover:from-sky-400 hover:to-sky-500 border border-sky-400/30",
		secondary:
			"bg-slate-100 text-slate-800 hover:bg-slate-200 border border-slate-300 shadow-sm dark:bg-slate-800/80 dark:text-slate-100 dark:hover:bg-slate-700/90 dark:border-white/10",
		danger:
			"bg-rose-600/90 text-white hover:bg-rose-500 border border-rose-400/20 shadow-sm",
		ghost:
			"bg-transparent text-slate-600 hover:bg-slate-200/60 hover:text-slate-900 border border-transparent dark:text-slate-300 dark:hover:bg-white/5 dark:hover:text-white",
	}[variant];

	const sizes = {
		sm: "px-2.5 py-1.5 text-xs",
		md: "px-3.5 py-2 text-sm",
		lg: "px-5 py-2.5 text-sm",
	}[size];

	return (
		<button
			className={cn(
				"inline-flex items-center justify-center gap-1.5 rounded-lg font-medium transition",
				"focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/40",
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
			className="mb-1.5 block text-xs font-medium uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400"
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
				hover &&
					"transition hover:border-sky-500/40 hover:shadow-glow-sm dark:hover:border-sky-500/25",
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
			"bg-slate-200/90 text-slate-700 ring-1 ring-slate-300 dark:bg-slate-800/90 dark:text-slate-300 dark:ring-white/10",
		success:
			"bg-emerald-500/15 text-emerald-700 ring-1 ring-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/25",
		danger:
			"bg-rose-500/15 text-rose-700 ring-1 ring-rose-500/30 dark:bg-rose-500/10 dark:text-rose-300 dark:ring-rose-500/25",
		warn: "bg-amber-500/15 text-amber-700 ring-1 ring-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200 dark:ring-amber-500/25",
		info: "bg-sky-500/15 text-sky-700 ring-1 ring-sky-500/30 dark:bg-sky-500/10 dark:text-sky-300 dark:ring-sky-500/25",
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
				<h1 className="text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl dark:text-white">
					{title}
				</h1>
				{description ? (
					<p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-slate-500 dark:text-slate-400">
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
			<div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-sky-500/15 text-sky-600 ring-1 ring-sky-500/25 dark:bg-sky-500/10 dark:text-sky-400 dark:ring-sky-500/20">
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
			<p className="text-base font-medium text-slate-900 dark:text-slate-100">
				{title}
			</p>
			<p className="mt-1.5 max-w-sm text-sm text-slate-500 dark:text-slate-400">
				{body}
			</p>
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
				className="h-8 w-8 animate-spin rounded-full border-2 border-sky-500/20 border-t-sky-500"
				suppressHydrationWarning
			/>
			<p
				className="text-sm text-slate-500 dark:text-slate-500"
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
			<div className="pointer-events-none absolute -right-6 -top-6 h-24 w-24 rounded-full bg-sky-500/10 blur-2xl" />
			<p className="section-label">{label}</p>
			<p className="mt-3 text-3xl font-semibold tracking-tight text-slate-900 dark:text-white">
				{value}
			</p>
			{hint ? (
				<p className="mt-1.5 text-xs text-slate-500 dark:text-slate-500">
					{hint}
				</p>
			) : null}
			{pct != null ? (
				<div className="mt-4 h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
					<div
						className="h-full rounded-full bg-gradient-to-r from-sky-500 to-indigo-400 transition-all"
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
	"rounded-lg px-3 py-1.5 text-sm font-medium transition " +
	"focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/40";

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
				"inline-flex flex-wrap gap-1 rounded-lg border border-[var(--border)] bg-slate-50/60 p-0.5 dark:bg-slate-950/40",
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
								? "bg-sky-600 text-white shadow-sm"
								: "border border-transparent text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/5",
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
			<div className="overflow-x-auto">
				<table className="w-full text-left text-sm">
					<thead>
						<tr className="border-b border-[var(--border)] bg-slate-50/60 dark:bg-slate-950/40">
							{headers.map((h) => (
								<th
									key={h}
									className="px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-500"
								>
									{h}
								</th>
							))}
						</tr>
					</thead>
					<tbody className="divide-y divide-[var(--border)]">{children}</tbody>
				</table>
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
