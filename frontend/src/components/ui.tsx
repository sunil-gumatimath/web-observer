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

import { modeLabel } from "@/lib/modes";

export function cn(...parts: Array<string | false | null | undefined>) {
	return parts.filter(Boolean).join(" ");
}

export function Button({
	className,
	variant = "primary",
	size = "md",
	...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
	variant?: "primary" | "secondary" | "tertiary" | "inverse" | "danger" | "ghost";
	size?: "sm" | "md" | "lg";
	ref?: React.Ref<HTMLButtonElement>;
}) {
	const styles = {
		primary:
			"bg-[var(--primary)] text-[var(--on-primary)] hover:bg-[var(--primary-hover)] hover:text-[var(--on-primary)] active:bg-[var(--primary-focus)] active:text-[var(--on-primary)] border border-transparent",
		secondary:
			"bg-[var(--surface-1)] text-[var(--ink)] border border-[var(--hairline)] hover:bg-[var(--surface-2)] hover:text-[var(--ink)] hover:border-[var(--hairline-strong)] active:bg-[var(--surface-3)] active:text-[var(--ink)]",
		tertiary:
			"bg-[var(--canvas)] text-[var(--ink)] border border-transparent hover:bg-[var(--surface-1)] hover:text-[var(--ink)] active:bg-[var(--surface-2)] active:text-[var(--ink)]",
		inverse:
			"bg-[var(--inverse-canvas)] text-[var(--inverse-ink)] border border-transparent hover:bg-[var(--inverse-surface-1)] hover:text-[var(--inverse-ink)] active:bg-[var(--inverse-surface-2)] active:text-[var(--inverse-ink)]",
		danger:
			"bg-[var(--danger)] text-white hover:opacity-90 hover:text-white active:opacity-100 active:text-white border border-transparent",
		ghost:
			"bg-transparent text-[var(--ink)] hover:bg-[var(--surface-2)] hover:text-[var(--ink)] active:bg-[var(--surface-3)] active:text-[var(--ink)] border border-transparent",
	}[variant];

	const sizes = {
		sm: "px-2.5 py-1 text-xs leading-[1.20] rounded-[8px]",
		md: "px-3.5 py-2 text-sm leading-[1.20] rounded-[8px]",
		lg: "px-4 py-2.5 text-sm leading-[1.20] rounded-[8px] min-h-[40px]",
	}[size];

	return (
		<button
			className={cn(
				"inline-flex items-center justify-center gap-1.5 font-medium transition",
				"focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-focus)] focus-visible:ring-offset-1 focus-visible:ring-offset-[var(--canvas)]",
				"disabled:pointer-events-none disabled:opacity-40",
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
				className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--ink-subtle)]"
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
	className,
}: {
	children: ReactNode;
	htmlFor?: string;
	className?: string;
}) {
	return (
		<label
			htmlFor={htmlFor}
			className={cn(
				"mb-1.5 block text-xs font-medium uppercase tracking-[0.05em] text-[var(--muted)]",
				className,
			)}
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
				hover && "transition hover:border-[var(--hairline-strong)] hover:bg-[color:color-mix(in_srgb,var(--surface-2)_40%,transparent)]",
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
			"bg-[var(--surface-2)] text-[var(--ink-muted)] border border-[var(--hairline)]",
		success:
			"bg-[color:color-mix(in_srgb,var(--semantic-success)_10%,transparent)] text-[var(--semantic-success)] border border-[color:color-mix(in_srgb,var(--semantic-success)_25%,transparent)]",
		danger:
			"bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20",
		warn: "bg-amber-500/10 text-amber-700 dark:text-amber-300 border border-amber-500/20",
		info: "bg-[color:color-mix(in_srgb,var(--primary)_10%,transparent)] text-[var(--primary-hover)] border border-[color:color-mix(in_srgb,var(--primary)_25%,transparent)]",
	}[tone];
	return (
		<span
			title={title}
			className={cn(
				"inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium tracking-wide",
				styles,
			)}
		>
			{children}
		</span>
	);
}

export function CopyButton({
	text,
	label = "Copy",
	className,
}: {
	text: string;
	label?: string;
	className?: string;
}) {
	const [copied, setCopied] = useState(false);

	async function copy() {
		try {
			await navigator.clipboard.writeText(text);
			setCopied(true);
			window.setTimeout(() => setCopied(false), 1500);
		} catch {
			/* clipboard unavailable — text stays selectable */
		}
	}

	return (
		<Button
			type="button"
			variant="secondary"
			size="sm"
			onClick={copy}
			className={className}
		>
			{copied ? "Copied ✓" : label}
		</Button>
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
				<h1 className="font-display text-2xl font-semibold tracking-tight text-[var(--fg)] sm:text-3xl">
					{title}
				</h1>
				{description ? (
					<p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-[var(--muted)]">
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
			<div className="mb-4 flex h-10 w-10 items-center justify-center rounded-[10px] bg-[var(--surface-2)] text-[var(--fg)] border border-[var(--hairline)]">
				{icon ?? (
					<svg
						className="h-5 w-5"
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
			<p className="text-sm font-medium text-[var(--fg)]">{title}</p>
			<p className="mt-1 max-w-sm text-xs text-[var(--muted)] leading-relaxed">{body}</p>
			{action ? <div className="mt-4">{action}</div> : null}
		</Card>
	);
}

export function ErrorBox({ message }: { message: string }) {
	return (
		<div
			role="alert"
			className="mb-4 flex items-start gap-2.5 rounded-[8px] border border-rose-500/25 bg-rose-500/10 px-3 py-2.5 text-xs text-rose-700 dark:text-rose-300"
		>
			<svg
				className="mt-0.5 h-4 w-4 shrink-0 text-rose-500 dark:text-rose-400"
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
		<div
			role="status"
			className="mb-4 flex items-start gap-2.5 rounded-[8px] border border-emerald-500/25 bg-emerald-500/10 px-3 py-2.5 text-xs text-emerald-700 dark:text-emerald-300"
		>
			<svg
				className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400"
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
	const [visible, setVisible] = useState(delayMs <= 0);
	useEffect(() => {
		if (delayMs <= 0) return;
		const t = setTimeout(() => setVisible(true), delayMs);
		return () => clearTimeout(t);
	}, [delayMs]);

	if (!visible) return null;

	return (
		<div
			className="flex flex-col items-center justify-center gap-3 py-16"
			suppressHydrationWarning
		>
			<div
				className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--hairline-strong)] border-t-[var(--primary)]"
				suppressHydrationWarning
			/>
			<p
				className="text-xs text-[var(--muted)]"
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
			<p className="mt-2 font-display text-2xl font-semibold tracking-tight text-[var(--fg)]">
				{value}
			</p>
			{hint ? (
				<p className="mt-1 text-xs text-[var(--muted)]">{hint}</p>
			) : null}
			{pct != null ? (
				<div className="mt-3 h-1 overflow-hidden rounded-full bg-[var(--surface-3)]">
					<div
						className="h-full rounded-full bg-[var(--primary)] transition-all"
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

export function SegmentedControl<T extends string>({
	options,
	value,
	onChange,
	ariaLabel,
	className,
	size = "sm",
}: {
	options: ReadonlyArray<{ value: T; label: ReactNode }>;
	value: T;
	onChange: (next: T) => void;
	ariaLabel?: string;
	className?: string;
	size?: "sm" | "md";
}) {
	const isMd = size === "md";
	return (
		<div
			role="group"
			aria-label={ariaLabel}
			className={cn(
				"inline-flex flex-wrap items-center gap-1 border border-[var(--hairline)] bg-[var(--canvas)]",
				isMd ? "p-1 rounded-[10px]" : "p-0.5 rounded-[8px]",
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
							"font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring-focus)]",
							isMd
								? "rounded-[8px] px-3.5 py-1.5 text-sm"
								: "rounded-[6px] px-2.5 py-1 text-xs",
							active
								? "bg-[var(--surface-2)] text-[var(--fg)] border border-[var(--hairline-strong)] shadow-sm"
								: "border border-transparent text-[var(--muted)] hover:text-[var(--fg)] hover:bg-[var(--surface-1)]",
						)}
					>
						{opt.label}
					</button>
				);
			})}
		</div>
	);
}

export function ModeBadge({ mode }: { mode: string }) {
	return <Badge tone="info">{modeLabel(mode)}</Badge>;
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
