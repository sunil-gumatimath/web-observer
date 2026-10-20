/**
 * Parsing helpers for the AI change summary stored on a change event.
 *
 * The backend stores the model's own summary text in `ai_summary`. When a
 * change was not a plain signal the summary is prefixed with a marker line:
 *
 *     [AI triage] cookie banner churn (watched: prices)
 *     The banner text changed from "Accept" to "Got it".
 *
 *     [Conditional] price_below 20 (threshold not met)
 *
 * The marker line explains *why* the change was held back; the lines after it
 * describe what actually changed. Older rows were stored with the title and
 * impact baked into the text ("Title: body (impact: high)") — `stripDecoration`
 * removes that legacy shape so both formats render the same way.
 */

export const TRIAGE_MARKER = "[AI triage]";
export const CONDITIONAL_MARKER = "[Conditional]";

export type SummaryKind = "triage" | "conditional" | "plain";

export type SummaryParts = {
	kind: SummaryKind;
	/** Why the change was held back (triage / conditional only). */
	reason: string | null;
	/** The change summary itself (without the marker line). */
	detail: string;
};

/** Remove a trailing "(watched: …)" note from a triage reason. */
function stripWatchedNote(reason: string): string {
	return reason.replace(/\s*\(watched:[^)]*\)\s*$/i, "").trim();
}

/** Split a stored summary into its marker reason and the change detail. */
export function parseSummaryParts(summary?: string | null): SummaryParts {
	const text = (summary ?? "").trim();
	if (!text) return { kind: "plain", reason: null, detail: "" };

	if (text.startsWith(TRIAGE_MARKER) || text.startsWith(CONDITIONAL_MARKER)) {
		const kind: SummaryKind = text.startsWith(TRIAGE_MARKER) ? "triage" : "conditional";
		const newlineAt = text.indexOf("\n");
		const head = newlineAt === -1 ? text : text.slice(0, newlineAt);
		const detail = newlineAt === -1 ? "" : text.slice(newlineAt + 1).trim();
		let reason = head.slice(head.indexOf("]") + 1).trim();
		if (kind === "triage") reason = stripWatchedNote(reason);
		return { kind, reason: reason || null, detail };
	}

	return { kind: "plain", reason: null, detail: text };
}

/**
 * Remove the legacy decorations from a summary: a leading "Title: " prefix
 * (only when it matches the stored title) and a trailing "(impact: …)".
 */
export function stripDecoration(summary: string, title?: string | null): string {
	let out = (summary ?? "").trim();
	const trimmedTitle = (title ?? "").trim();
	if (trimmedTitle && out.startsWith(`${trimmedTitle}:`)) {
		out = out.slice(trimmedTitle.length + 1).trim();
	}
	out = out.replace(/\s*\(impact:\s*(low|medium|high|critical)\)\s*$/i, "").trim();
	return out;
}

/** Legacy helper kept for the dashboard/alert list: impact from the text. */
export function parseImpact(summary: string | null | undefined): string | null {
	if (!summary) return null;
	const m = summary.match(/\(impact:\s*(low|medium|high|critical)\)/i);
	return m ? m[1].toLowerCase() : null;
}

/** Legacy helper kept for the dashboard/alert list: drop the impact suffix. */
export function stripImpact(summary: string): string {
	return (summary ?? "").replace(/\s*\(impact:\s*(low|medium|high|critical)\)\s*$/i, "").trim();
}

/**
 * Build the one-line headline shown in list rows: the triage reason when the
 * change was held back, otherwise the title and the summary.
 */
export function composeHeadline(parts: SummaryParts, title?: string | null): string {
	if (parts.reason) return parts.reason;
	const raw = parts.detail.trim();
	const body = stripImpact(raw);
	const trimmedTitle = (title ?? "").trim();
	if (!trimmedTitle) return body;
	// Legacy rows still carry the title inline ("Title: body") — keep it.
	if (body.startsWith(`${trimmedTitle}:`)) return body;
	return `${trimmedTitle} — ${body}`;
}
