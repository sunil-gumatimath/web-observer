import type { MonitorMode } from "@/lib/types";

export type ThresholdConfig = Record<string, unknown>;

export type ThresholdKey =
	| "price_below"
	| "price_above"
	| "percent_change"
	| "list_min_added"
	| "list_min_removed"
	| "min_diff_chars"
	| "regex_must_match"
	| "regex_must_not_match";

export const ALL_THRESHOLD_KEYS: ThresholdKey[] = [
	"price_below",
	"price_above",
	"percent_change",
	"list_min_added",
	"list_min_removed",
	"min_diff_chars",
	"regex_must_match",
	"regex_must_not_match",
];

/** Fields valid for each mode — mirrors backend/app/services/conditional.py. */
export function keysForMode(mode: MonitorMode): ThresholdKey[] {
	const keys: ThresholdKey[] = [];
	if (mode === "product_price") {
		keys.push("price_below", "price_above", "percent_change");
	} else if (mode === "json_field" || mode === "page_content") {
		keys.push("percent_change");
	} else if (
		mode === "list_items" ||
		mode === "site_links" ||
		mode === "rss_feed"
	) {
		keys.push("list_min_added", "list_min_removed");
	}
	// Common to every mode.
	keys.push("min_diff_chars", "regex_must_match", "regex_must_not_match");
	return keys;
}

export function toDrafts(
	value: ThresholdConfig | null,
): Record<ThresholdKey, string> {
	const drafts = {} as Record<ThresholdKey, string>;
	for (const key of ALL_THRESHOLD_KEYS) {
		const v = value?.[key];
		drafts[key] = v === undefined || v === null ? "" : String(v);
	}
	return drafts;
}

export function isValidRegex(pattern: string): boolean {
	try {
		new RegExp(pattern);
		return true;
	} catch {
		return false;
	}
}

/** Returns the number for a draft, or null when it is not a usable value. */
export function parseNumericDraft(
	raw: string,
	integer: boolean,
): number | null {
	if (raw.trim() === "") return null;
	const n = Number(raw.trim());
	if (!Number.isFinite(n)) return null;
	if (integer && !Number.isInteger(n)) return null;
	return n;
}
/**
 * Pure draft application for numeric fields.
 * Returns the next config to propagate, or null when the input must stay
 * local (blank-but-absent, or intermediate/invalid like "abc").
 */
export function applyNumericDraft(
	key: ThresholdKey,
	raw: string,
	integer: boolean,
	current: ThresholdConfig | null,
): ThresholdConfig | null {
	if (raw.trim() === "") {
		if (current && key in current) {
			const next = { ...current };
			delete next[key];
			return next;
		}
		return null;
	}
	const n = parseNumericDraft(raw, integer);
	if (n === null) return null;
	if (current?.[key] === n) return null;
	return { ...(current ?? {}), [key]: n };
}

/** Pure draft application for regex fields. Invalid patterns never propagate. */
export function applyPatternDraft(
	key: ThresholdKey,
	raw: string,
	current: ThresholdConfig | null,
): ThresholdConfig | null {
	if (raw === "") {
		if (current && key in current) {
			const next = { ...current };
			delete next[key];
			return next;
		}
		return null;
	}
	if (!isValidRegex(raw)) return null;
	if (current?.[key] === raw) return null;
	return { ...(current ?? {}), [key]: raw };
}

/** True when no threshold is set — alert on any change. */
export function isEmptyConfig(config: ThresholdConfig | null): boolean {
	return !config || Object.keys(config).length === 0;
}
