/**
 * Markdown helpers for the README renderer.
 *
 * Repository READMEs are plain markdown files, but many of them also embed
 * raw HTML for layout (badges in `<p align="center">`, centered logos,
 * `<sub>`/`<sup>` footnotes). GitHub renders that HTML; a markdown renderer
 * does not, so the tags would show up as literal text. This module converts
 * the common HTML constructs to their markdown equivalents — but only
 * *outside* fenced code blocks, where tags are literal content and must be
 * left untouched.
 */

const FENCE_RE = /^\s{0,3}(`{3,}|~{3,})/;
const COMMENT_RE = /<!--[\s\S]*?-->/g;
const IMG_TAG_RE = /<img\b[^>]*>/gi;
const ANCHOR_RE = /<a\b([^>]*)>([\s\S]*?)<\/a>/gi;
const BR_TAG_RE = /<br\s*\/?>/gi;
const OTHER_TAG_RE = /<\/?[a-zA-Z][^<>]*>/g;
const INLINE_CODE_RE = /(`+)([^`]|[\s\S]*?[^`])\1(?!`)/g;
const HREF_ATTR_RE = /href\s*=\s*["']([^"']*)["']/i;
const SRC_ATTR_RE = /src\s*=\s*["']([^"']*)["']/i;
const ALT_ATTR_RE = /alt\s*=\s*["']([^"']*)["']/i;

/** Split markdown into fenced-code and non-code segments. */
function splitFences(markdown: string): Array<{ code: boolean; text: string }> {
	const lines = markdown.split("\n");
	const segments: Array<{ code: boolean; text: string }> = [];
	let buffer: string[] = [];
	let inFence = false;
	let fenceMarker = "";

	const flush = (code: boolean) => {
		if (buffer.length === 0) return;
		segments.push({ code, text: buffer.join("\n") });
		buffer = [];
	};

	for (const line of lines) {
		const match = FENCE_RE.exec(line);
		if (match) {
			const marker = match[1][0];
			if (!inFence) {
				flush(false);
				inFence = true;
				fenceMarker = marker;
			} else if (marker === fenceMarker) {
				buffer.push(line);
				flush(true);
				inFence = false;
				fenceMarker = "";
				continue;
			}
		}
		buffer.push(line);
	}
	flush(inFence);
	return segments;
}

/** Convert raw HTML inside a non-code segment to markdown. */
function convertSegment(text: string): string {
	// Inline code spans hold literal text (`<pkg>`) — protect them from the
	// tag stripping below and restore them afterwards.
	const spans: string[] = [];
	let out = text.replace(INLINE_CODE_RE, (match) => {
		spans.push(match);
		return `\u0000${spans.length - 1}\u0000`;
	});

	out = out.replace(COMMENT_RE, "");
	out = out.replace(IMG_TAG_RE, (tag) => {
		const src = SRC_ATTR_RE.exec(tag)?.[1];
		if (!src) return "";
		const alt = ALT_ATTR_RE.exec(tag)?.[1] ?? "";
		return `![${alt}](${src})`;
	});
	out = out.replace(ANCHOR_RE, (_match, attrs: string, inner: string) => {
		const href = HREF_ATTR_RE.exec(attrs)?.[1];
		if (!href) return inner;
		return `[${inner}](${href})`;
	});
	out = out.replace(BR_TAG_RE, "\n");
	// Everything else (wrappers like <p align="center">, <div>, <b>, …) is
	// dropped while its text content is kept.
	out = out.replace(OTHER_TAG_RE, "");

	return out.replace(/\u0000(\d+)\u0000/g, (_match, idx: string) => spans[Number(idx)] ?? "");
}

/**
 * Convert raw HTML in a markdown document to markdown, leaving fenced code
 * blocks untouched.
 */
export function htmlToMarkdown(markdown: string): string {
	if (!markdown) return "";
	return splitFences(markdown)
		.map((segment) => (segment.code ? segment.text : convertSegment(segment.text)))
		.join("\n");
}
