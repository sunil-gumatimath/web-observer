"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui";

/**
 * On-brand replacement for native `window.confirm()`.
 *
 * Renders a trigger button; when clicked, shows a small modal dialog with
 * Cancel / Confirm actions. Supports async `onConfirm` — the dialog shows a
 * pending state while it resolves, and closes automatically on success.
 *
 * Focus is moved into the dialog when it opens (and returned to the trigger
 * when it closes) so keyboard users stay inside the modal flow.
 */
export function ConfirmButton({
	onConfirm,
	title = "Are you sure?",
	body,
	confirmLabel = "Confirm",
	cancelLabel = "Cancel",
	variant = "danger",
	size = "md",
	busy = false,
	disabled = false,
	error,
	className,
	children,
}: {
	onConfirm: () => void | Promise<void>;
	title?: string;
	body?: ReactNode;
	confirmLabel?: string;
	cancelLabel?: string;
	variant?: "primary" | "secondary" | "danger" | "ghost";
	size?: "sm" | "md" | "lg";
	busy?: boolean;
	disabled?: boolean;
	error?: string | null;
	className?: string;
	children: ReactNode;
}) {
	const [open, setOpen] = useState(false);
	const [pending, setPending] = useState(false);
	const triggerRef = useRef<HTMLButtonElement>(null);
	const cancelRef = useRef<HTMLButtonElement>(null);
	const panelRef = useRef<HTMLDivElement>(null);

	useEffect(() => {
		if (!open) return;
		const prev = document.body.style.overflow;
		document.body.style.overflow = "hidden";
		// Snapshot refs so the cleanup uses stable values (exhaustive-deps).
		const trigger = triggerRef.current;
		const cancel = cancelRef.current;
		const panel = panelRef.current;

		const FOCUSABLE =
			'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

		function onKey(e: KeyboardEvent) {
			if (e.key === "Escape") {
				setOpen(false);
				return;
			}
			if (e.key !== "Tab" || !panel) return;
			// Focus trap: keep Tab / Shift+Tab cycling inside the dialog.
			const focusables = Array.from(
				panel.querySelectorAll<HTMLElement>(FOCUSABLE),
			).filter((el) => el.offsetParent !== null);
			if (focusables.length === 0) return;
			const first = focusables[0];
			const last = focusables[focusables.length - 1];
			const active = document.activeElement;
			if (e.shiftKey && (active === first || !panel.contains(active))) {
				e.preventDefault();
				last.focus();
			} else if (!e.shiftKey && (active === last || !panel.contains(active))) {
				e.preventDefault();
				first.focus();
			}
		}

		window.addEventListener("keydown", onKey);
		// Move focus into the dialog so keyboard users land on the actions.
		cancel?.focus();
		return () => {
			window.removeEventListener("keydown", onKey);
			document.body.style.overflow = prev;
			// Return focus to the element that opened the dialog.
			trigger?.focus();
		};
	}, [open]);

	async function handleConfirm() {
		setPending(true);
		try {
			await onConfirm();
			setOpen(false);
		} finally {
			setPending(false);
		}
	}

	return (
		<>
			<Button
				ref={triggerRef}
				type="button"
				variant={variant}
				size={size}
				disabled={disabled || busy || pending}
				onClick={() => setOpen(true)}
				className={className}
				aria-haspopup="dialog"
			>
				{children}
			</Button>

			{open ? (
				<div
					className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
					role="dialog"
					aria-modal="true"
					aria-label={title}
					onClick={() => setOpen(false)}
				>
					<div
						ref={panelRef}
						className="w-full max-w-md rounded-[22px] border border-[var(--border-soft)] bg-[var(--bg)] p-5"
						onClick={(e) => e.stopPropagation()}
					>
						<div className="flex h-10 w-10 items-center justify-center rounded-xl bg-rose-500/15 text-rose-600 ring-1 ring-rose-500/25 dark:text-rose-300">
							<svg
								className="h-5 w-5"
								fill="none"
								viewBox="0 0 24 24"
								stroke="currentColor"
								strokeWidth={1.75}
								aria-hidden="true"
							>
								<path
									strokeLinecap="round"
									strokeLinejoin="round"
									d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0"
								/>
							</svg>
						</div>
						<h3 className="mt-4 text-base font-semibold text-[var(--fg)]">
							{title}
						</h3>
						{body ? (
							<p className="mt-2 text-sm leading-relaxed text-[var(--muted)]">
								{body}
							</p>
						) : null}
						{error ? (
							<p className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-700 dark:text-rose-200">
								{error}
							</p>
						) : null}
						<div className="mt-5 flex justify-end gap-2">
							<Button
								ref={cancelRef}
								type="button"
								variant="ghost"
								size="sm"
								disabled={pending}
								onClick={() => setOpen(false)}
							>
								{cancelLabel}
							</Button>
							<Button
								type="button"
								variant={variant}
								size="sm"
								disabled={pending}
								onClick={handleConfirm}
							>
								{pending ? "Working…" : confirmLabel}
							</Button>
						</div>
					</div>
				</div>
			) : null}
		</>
	);
}
