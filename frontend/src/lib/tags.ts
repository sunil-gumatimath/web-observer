/** Comma-separated tag input <-> string[] helpers (mirrors backend normalize_tags). */
export function parseTagInput(raw: string): string[] {
	const seen: string[] = [];
	for (const part of raw.split(",")) {
		const t = part.trim().toLowerCase();
		if (t && !seen.includes(t)) seen.push(t);
	}
	return seen.slice(0, 10);
}

export function formatTags(tags: string[] | null | undefined): string {
	return (tags ?? []).join(", ");
}
