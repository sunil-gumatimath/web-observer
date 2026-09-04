import { describe, expect, it } from "vitest";
import { synthesizeSelector, type PickElement } from "./selector";

interface FakeInit {
	tag?: string;
	id?: string;
	attrs?: Record<string, string>;
	classes?: string[];
	children?: FakeNode[];
}

class FakeNode implements PickElement {
	readonly tag: string;
	readonly id: string;
	private readonly attrs: Record<string, string>;
	private readonly classList: string[];
	private parentNode: FakeNode | null = null;
	private readonly childNodes: FakeNode[];

	constructor(init: FakeInit = {}) {
		this.tag = (init.tag ?? "div").toLowerCase();
		this.id = init.id ?? "";
		this.attrs = init.attrs ?? {};
		this.classList = init.classes ?? [];
		this.childNodes = (init.children ?? []).map((c) => {
			c.parentNode = this;
			return c;
		});
	}

	attr(name: string): string | null {
		return this.attrs[name] ?? null;
	}

	classes(): string[] {
		return [...this.classList];
	}

	parent(): PickElement | null {
		return this.parentNode;
	}

	indexOfType(): number {
		if (!this.parentNode) return 0;
		const siblings = this.parentNode.childNodes.filter((c) => c.tag === this.tag);
		return siblings.indexOf(this) + 1;
	}
}

describe("synthesizeSelector", () => {
	it("prefers a usable id", () => {
		const el = new FakeNode({ tag: "a", id: "main-link" });
		const out = synthesizeSelector(el, () => 1);
		expect(out.selector).toBe("#main-link");
		expect(out.matches).toBe(1);
	});

	it("uses data-testid when there is no id", () => {
		const el = new FakeNode({ tag: "button", attrs: { "data-testid": "save-btn" } });
		const out = synthesizeSelector(el, () => 1);
		expect(out.selector).toBe('button[data-testid="save-btn"]');
	});

	it("uses tag plus stable classes", () => {
		const el = new FakeNode({ tag: "article", classes: ["post", "featured"] });
		const out = synthesizeSelector(el, () => 1);
		expect(out.selector).toBe("article.post.featured");
	});

	it("falls back to nth-of-type for bare elements", () => {
		const second = new FakeNode({ tag: "li" });
		new FakeNode({ tag: "ul", children: [new FakeNode({ tag: "li" }), second] });
		const out = synthesizeSelector(second, () => 1);
		expect(out.selector).toBe("li:nth-of-type(2)");
	});

	it("walks up ancestors until the selector is unique", () => {
		const inner = new FakeNode({ tag: "a", classes: ["title"] });
		const item = new FakeNode({ tag: "li", classes: ["job"], children: [inner] });
		new FakeNode({ tag: "ul", id: "jobs", children: [item] });
		const seen: string[] = [];
		const out = synthesizeSelector(inner, (sel) => {
			seen.push(sel);
			return sel === "a.title" ? 12 : 1;
		});
		expect(seen[0]).toBe("a.title");
		expect(out.selector).toBe("li.job > a.title");
		expect(out.matches).toBe(1);
	});

	it("returns best effort with match count when never unique", () => {
		const el = new FakeNode({ tag: "span", classes: ["x"] });
		const out = synthesizeSelector(el, () => 5, 0);
		expect(out.selector).toBe("span.x");
		expect(out.matches).toBe(5);
	});
});
