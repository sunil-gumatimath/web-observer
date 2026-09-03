"use client";

import { useEffect, useRef, useState } from "react";
import { Input, Label, SectionTitle } from "@/components/ui";
import {
	applyNumericDraft,
	applyPatternDraft,
	isValidRegex,
	keysForMode,
	parseNumericDraft,
	toDrafts,
} from "@/lib/thresholds";
import type { ThresholdConfig, ThresholdKey } from "@/lib/thresholds";
import type { MonitorMode } from "@/lib/types";

type FieldKind = "float" | "int" | "regex";

interface FieldMeta {
	key: ThresholdKey;
	label: string;
	placeholder?: string;
	help: string | ((mode: MonitorMode) => string);
	kind: FieldKind;
	min?: string;
	step?: string;
}

const FIELD_META: Record<ThresholdKey, FieldMeta> = {
	price_below: {
		key: "price_below",
		label: "Alert when price drops below",
		placeholder: "e.g. 49.99",
		help: "Only alert when the detected price is below this amount.",
		kind: "float",
		step: "any",
	},
	price_above: {
		key: "price_above",
		label: "Alert when price rises above",
		placeholder: "e.g. 199.99",
		help: "Only alert when the detected price is above this amount.",
		kind: "float",
		step: "any",
	},
	percent_change: {
		key: "percent_change",
		label: "Minimum change (%)",
		placeholder: "e.g. 5",
		help: (mode) =>
			mode === "product_price"
				? "Only alert when the price moves by at least this percent since the last check."
				: mode === "json_field"
					? "Only alert when the watched value moves by at least this percent."
					: "Only alert when at least this share of the content changed.",
		kind: "float",
		min: "0",
		step: "any",
	},
	list_min_added: {
		key: "list_min_added",
		label: "Min. items added",
		placeholder: "e.g. 1",
		help: "Only alert when at least this many items were added.",
		kind: "int",
		min: "0",
		step: "1",
	},
	list_min_removed: {
		key: "list_min_removed",
		label: "Min. items removed",
		placeholder: "e.g. 1",
		help: "Only alert when at least this many items were removed.",
		kind: "int",
		min: "0",
		step: "1",
	},
	min_diff_chars: {
		key: "min_diff_chars",
		label: "Min. changed characters",
		placeholder: "e.g. 50",
		help: "Ignore tiny edits — only alert when the change is at least this large.",
		kind: "int",
		min: "0",
		step: "1",
	},
	regex_must_match: {
		key: "regex_must_match",
		label: "New content must match",
		placeholder: "e.g. \\bprice\\b",
		help: "Only alert when the new content matches this pattern.",
		kind: "regex",
	},
	regex_must_not_match: {
		key: "regex_must_not_match",
		label: "New content must not match",
		placeholder: "e.g. \\bout of stock\\b",
		help: "Skip the alert when the new content matches this pattern.",
		kind: "regex",
	},
};

function helpFor(meta: FieldMeta, mode: MonitorMode): string {
	return typeof meta.help === "function" ? meta.help(mode) : meta.help;
}

/**
 * Per-mode alert threshold editor backed by `monitor.alert_config`.
 * Empty (all blank) means alert on any change. Invalid input stays local:
 * it shows an inline error and is never propagated via onChange.
 */
export function ThresholdEditor({
	mode,
	value,
	onChange,
}: {
	mode: MonitorMode;
	value: ThresholdConfig | null;
	onChange: (next: ThresholdConfig) => void;
}) {
	const [drafts, setDrafts] = useState<Record<ThresholdKey, string>>(() =>
		toDrafts(value),
	);
	const lastEmitted = useRef<string | null>(null);

	// Resync drafts when the parent value changes externally (e.g. the
	// monitor finished loading). Echoes of our own onChange calls (tracked
	// via lastEmitted) are skipped so in-progress typing like "1." is kept.
	const fingerprintValue = JSON.stringify(value ?? null);
	useEffect(() => {
		if (fingerprintValue !== lastEmitted.current) {
			setDrafts(toDrafts(value));
		}
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [fingerprintValue]);

	function commit(next: ThresholdConfig) {
		lastEmitted.current = JSON.stringify(next);
		onChange(next);
	}

	function setNumeric(key: ThresholdKey, raw: string, integer: boolean) {
		setDrafts((d) => (d[key] === raw ? d : { ...d, [key]: raw }));
		const next = applyNumericDraft(key, raw, integer, value);
		if (next) commit(next);
	}

	function setPattern(key: ThresholdKey, raw: string) {
		setDrafts((d) => (d[key] === raw ? d : { ...d, [key]: raw }));
		const next = applyPatternDraft(key, raw, value);
		if (next) commit(next);
	}

	function numericError(key: ThresholdKey, integer: boolean): string | null {
		const raw = drafts[key];
		if (raw.trim() === "") return null;
		return parseNumericDraft(raw, integer) === null
			? "Enter a valid number."
			: null;
	}

	function patternError(key: ThresholdKey): string | null {
		const raw = drafts[key];
		if (raw === "") return null;
		return isValidRegex(raw) ? null : "Invalid regular expression.";
	}

	const keys = keysForMode(mode);
	const numericKeys = keys.filter((k) => FIELD_META[k].kind !== "regex");
	const patternKeys = keys.filter((k) => FIELD_META[k].kind === "regex");

	return (
		<div>
			<SectionTitle>Alert thresholds</SectionTitle>
			<p className="mt-1 text-xs text-slate-500 dark:text-slate-500">
				Leave all blank to alert on any change.
			</p>
			<div className="mt-3 grid gap-4 sm:grid-cols-2">
				{numericKeys.map((key) => {
					const meta = FIELD_META[key];
					const error = numericError(key, meta.kind === "int");
					return (
						<div key={key}>
							<Label htmlFor={`threshold-${key}`}>{meta.label}</Label>
							<Input
								id={`threshold-${key}`}
								type="number"
								inputMode="decimal"
								value={drafts[key]}
								min={meta.min}
								step={meta.step}
								placeholder={meta.placeholder}
								aria-invalid={error ? true : undefined}
								onChange={(e) =>
									setNumeric(key, e.target.value, meta.kind === "int")
								}
							/>
							{error ? (
								<p className="mt-1 text-xs text-rose-600 dark:text-rose-400">
									{error}
								</p>
							) : (
								<p className="mt-1 text-xs text-slate-500 dark:text-slate-500">
									{helpFor(meta, mode)}
								</p>
							)}
						</div>
					);
				})}
			</div>
			<div className="mt-4 space-y-4">
				{patternKeys.map((key) => {
					const meta = FIELD_META[key];
					const error = patternError(key);
					return (
						<div key={key}>
							<Label htmlFor={`threshold-${key}`}>{meta.label}</Label>
							<Input
								id={`threshold-${key}`}
								type="text"
								value={drafts[key]}
								placeholder={meta.placeholder}
								aria-invalid={error ? true : undefined}
								onChange={(e) => setPattern(key, e.target.value)}
							/>
							{error ? (
								<p className="mt-1 text-xs text-rose-600 dark:text-rose-400">
									{error}
								</p>
							) : (
								<p className="mt-1 text-xs text-slate-500 dark:text-slate-500">
									{helpFor(meta, mode)}
								</p>
							)}
						</div>
					);
				})}
			</div>
		</div>
	);
}
