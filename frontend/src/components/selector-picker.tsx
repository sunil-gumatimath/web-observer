"use client";

import { useEffect, useRef, useState, type MouseEvent, type SyntheticEvent } from "react";
import { Button, ErrorBox, Input, Label } from "@/components/ui";
import { api } from "@/lib/api";
import { ensureWorkspace } from "@/lib/workspace";
import { fromDomElement, synthesizeSelector } from "@/lib/selector";

interface Picked {
	selector: string;
	matches: number;
	sample: string;
}

interface SelectorPickerProps {
	open: boolean;
	initialUrl: string;
	onClose: () => void;
	onPick: (selector: string) => void;
}

/** Visual element picker: load a proxied page preview, click an element,
 *  get back a resilient CSS selector for list_items monitors. */
export function SelectorPicker({ open, initialUrl, onClose, onPick }: SelectorPickerProps) {
	const [url, setUrl] = useState(initialUrl);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [html, setHtml] = useState<string | null>(null);
	const [finalUrl, setFinalUrl] = useState<string | null>(null);
	const [truncated, setTruncated] = useState(false);
	const [picked, setPicked] = useState<Picked | null>(null);
	const previewRef = useRef<HTMLDivElement>(null);
	const hoveredRef = useRef<HTMLElement | null>(null);

	useEffect(() => {
		if (open) {
			setUrl(initialUrl);
			setHtml(null);
			setFinalUrl(null);
			setTruncated(false);
			setPicked(null);
			setError(null);
			setLoading(false);
		}
	}, [open, initialUrl]);

	useEffect(() => {
		if (!open) return;
		const onKey = (e: KeyboardEvent) => {
			if (e.key === "Escape") onClose();
		};
		window.addEventListener("keydown", onKey);
		return () => window.removeEventListener("keydown", onKey);
	}, [open, onClose]);

	if (!open) return null;

	function clearHover() {
		const el = hoveredRef.current;
		if (el) {
			el.style.outline = "";
			el.style.cursor = "";
			hoveredRef.current = null;
		}
	}

	function onHover(e: MouseEvent<HTMLDivElement>) {
		const target = (e.target as HTMLElement | null)?.closest?.("a,button,p,h1,h2,h3,h4,li,article,div,span,td,img") as HTMLElement | null;
		if (!target || !previewRef.current?.contains(target)) return;
		if (hoveredRef.current === target) return;
		clearHover();
		hoveredRef.current = target;
		target.style.outline = "2px solid #0ea5e9";
		target.style.cursor = "crosshair";
	}

	function countMatches(selector: string): number {
		const root = previewRef.current;
		if (!root) return 0;
		try {
			return root.querySelectorAll(selector).length;
		} catch {
			return 0;
		}
	}

	function onPreviewInteract(e: MouseEvent<HTMLDivElement>) {
		// Inert preview: intercept first, then treat the interaction as a pick.
		e.preventDefault();
		e.stopPropagation();
		if (e.type !== "click") return;
		const target = (e.target as HTMLElement | null)?.closest?.(
			"a,button,p,h1,h2,h3,h4,li,article,div,span,td,img",
		) as HTMLElement | null;
		if (!target || !previewRef.current?.contains(target)) return;
		const { selector, matches } = synthesizeSelector(fromDomElement(target), countMatches);
		const sample = (target.textContent || target.getAttribute("alt") || target.tagName)
			.trim()
			.slice(0, 120);
		setPicked({ selector, matches, sample });
	}

	function stopSubmit(e: SyntheticEvent) {
		// Block form submits (Enter key) inside the inert preview.
		e.preventDefault();
		e.stopPropagation();
	}

	async function loadPreview() {
		const candidate = url.trim();
		if (!candidate) {
			setError("Enter the page URL first.");
			return;
		}
		setLoading(true);
		setError(null);
		setPicked(null);
		try {
			const ws = await ensureWorkspace();
			const preview = await api.selectorPreview(ws, candidate);
			setHtml(preview.html);
			setFinalUrl(preview.final_url);
			setTruncated(preview.truncated);
		} catch (err) {
			setError(err instanceof Error ? err.message : "Failed to load preview");
			setHtml(null);
		} finally {
			setLoading(false);
		}
	}

	return (
		<div
			className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
			onClick={onClose}
			role="dialog"
			aria-modal="true"
			aria-label="Pick element visually"
		>
			<div
				className="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl bg-white shadow-2xl dark:bg-slate-900"
				onClick={(e) => e.stopPropagation()}
			>
				<div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-3">
					<h2 className="text-base font-semibold">Pick element visually</h2>
					<button
						type="button"
						onClick={onClose}
						aria-label="Close picker"
						className="rounded-md px-2 py-1 text-xl leading-none text-slate-500 hover:bg-slate-100 dark:hover:bg-white/10"
					>
						×
					</button>
				</div>

				<div className="space-y-3 overflow-y-auto px-5 py-4">
					<div>
						<Label htmlFor="picker-url">Page URL</Label>
						<div className="flex gap-2">
							<Input
								id="picker-url"
								value={url}
								onChange={(e) => setUrl(e.target.value)}
								placeholder="https://example.com/jobs"
							/>
							<Button type="button" onClick={loadPreview} disabled={loading}>
								{loading ? "Loading…" : html ? "Reload" : "Load preview"}
							</Button>
						</div>
					</div>

					{error ? <ErrorBox message={error} /> : null}

					{html ? (
						<>
							<p className="text-xs text-slate-500 dark:text-slate-400">
								Hover to highlight, click to select. Preview of{" "}
								<code className="break-all">{finalUrl}</code>
								{truncated ? " (page truncated to first 1MB)" : ""}.
							</p>
							<div
								ref={previewRef}
								onMouseOver={onHover}
								onMouseOut={clearHover}
								onClickCapture={onPreviewInteract}
								onSubmit={stopSubmit}
								className="max-h-[45vh] overflow-auto rounded-lg border border-[var(--border)] bg-white p-4 text-slate-900"
								// Sanitized server-side (no scripts/frames/handlers); inert by interception.
								dangerouslySetInnerHTML={{ __html: html }}
							/>
							{picked ? (
								<div className="rounded-lg border border-[var(--border)] p-3">
									<div className="flex flex-wrap items-center gap-2">
										<code className="break-all text-sm font-medium">{picked.selector}</code>
										<span
											className={`rounded-full px-2 py-0.5 text-xs font-medium ${
												picked.matches === 1
													? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300"
													: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
											}`}
										>
											{picked.matches === 1
												? "matches 1 element"
												: `matches ${picked.matches} elements`}
										</span>
									</div>
									{picked.sample ? (
										<p className="mt-1 truncate text-xs text-slate-500 dark:text-slate-400">
											“{picked.sample}”
										</p>
									) : null}
									{picked.matches !== 1 ? (
										<p className="mt-1 text-xs text-amber-700 dark:text-amber-400">
											Matches several elements — list mode watches all of them. Click a more
											specific element for a tighter selector.
										</p>
									) : null}
									<div className="mt-2 flex gap-2">
										<Button type="button" onClick={() => onPick(picked.selector)}>
											Use this selector
										</Button>
										<Button type="button" variant="secondary" onClick={() => setPicked(null)}>
											Clear
										</Button>
									</div>
								</div>
							) : null}
						</>
					) : (
						<p className="text-sm text-slate-500 dark:text-slate-400">
							Load a preview of the page, then click the element holding the links you want to
							watch — the CSS selector fills in automatically.
						</p>
					)}
				</div>
			</div>
		</div>
	);
}
