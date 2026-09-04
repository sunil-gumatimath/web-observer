/**
 * Resilient CSS selector synthesis for the visual element picker.
 *
 * Deliberately DOM-library-free: it works against the small structural
 * {@link PickElement} interface (real `Element`s are adapted at the call
 * site), so this module unit-tests under the node vitest environment with
 * hand-rolled fakes and no jsdom dependency.
 */

/** Minimal structural view of a DOM element needed for synthesis. */
export interface PickElement {
	/** Lower-case tag name, e.g. "a". */
	readonly tag: string;
	/** Element id (`""` when absent). */
	readonly id: string;
	/** Attribute value or null. */
	attr(name: string): string | null;
	/** Class list (no leading dots). */
	classes(): string[];
	/** Parent element or null at the root. */
	parent(): PickElement | null;
	/** 1-based position among same-tag siblings (0 when unknown). */
	indexOfType(): number;
}

export interface SynthesizedSelector {
	selector: string;
	/** How many elements the selector matches (1 = unique). */
	matches: number;
}

const TEST_ATTRS = ["data-testid", "data-cy", "data-qa", "data-test"] as const;
const MAX_DEPTH = 4;

function cssEscape(value: string): string {
	const g = globalThis as unknown as { CSS?: { escape?: (s: string) => string } };
	const fn = g.CSS?.escape;
	if (typeof fn === "function") return fn.call(g.CSS, value);
	return value.replace(/[^a-zA-Z0-9_-]/g, "\\$&");
}

function attrEscape(value: string): string {
	return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

function isUsableId(id: string): boolean {
	return /^[A-Za-z][\w:.-]*$/.test(id);
}

/** Simplest selector for one element, most-resilient first. */
function simpleFor(el: PickElement): string {
	const tag = el.tag.toLowerCase() || "*";

	if (el.id && isUsableId(el.id)) return `#${cssEscape(el.id)}`;

	for (const name of TEST_ATTRS) {
		const v = el.attr(name);
		if (v) return `${tag}[${name}="${attrEscape(v)}"]`;
	}

	if (["input", "select", "textarea", "button"].includes(tag)) {
		const name = el.attr("name");
		if (name) return `${tag}[name="${attrEscape(name)}"]`;
	}

	const stable = el
		.classes()
		.map((c) => c.trim())
		.filter((c) => c.length > 0 && c.length <= 40)
		.slice(0, 2);
	if (stable.length > 0) return `${tag}.${stable.map(cssEscape).join(".")}`;

	const idx = el.indexOfType();
	if (idx >= 1) return `${tag}:nth-of-type(${idx})`;
	return tag;
}

/**
 * Build the shortest unique-anchored selector for `el`.
 * `count` reports how many elements a candidate matches in the preview root.
 */
export function synthesizeSelector(
	el: PickElement,
	count: (selector: string) => number,
	maxDepth: number = MAX_DEPTH,
): SynthesizedSelector {
	let selector = simpleFor(el);
	let matches = safeCount(count, selector);
	if (matches === 1) return { selector, matches };

	let node = el.parent();
	let depth = 0;
	while (node && depth < maxDepth && matches !== 1) {
		selector = `${simpleFor(node)} > ${selector}`;
		matches = safeCount(count, selector);
		node = node.parent();
		depth += 1;
	}
	return { selector, matches };
}

function safeCount(count: (selector: string) => number, selector: string): number {
	try {
		const n = count(selector);
		return Number.isFinite(n) && n >= 0 ? Math.floor(n) : 0;
	} catch {
		return 0;
	}
}

/** Adapt a live DOM `Element` for {@link synthesizeSelector}. */
export function fromDomElement(el: Element): PickElement {
	const element = el as HTMLElement;
	return {
		tag: (el.tagName || "*").toLowerCase(),
		id: element.id || "",
		attr: (name: string) => el.getAttribute(name),
		classes: () => Array.from(el.classList ?? []),
		parent: () => {
			const p = el.parentElement;
			return p ? fromDomElement(p) : null;
		},
		indexOfType: () => {
			const p = el.parentElement;
			if (!p) return 0;
			const tag = el.tagName;
			let i = 0;
			for (const child of Array.from(p.children)) {
				if (child.tagName === tag) i += 1;
				if (child === el) return i;
			}
			return 0;
		},
	};
}
