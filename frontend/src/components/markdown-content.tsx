"use client";

import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { useMemo } from "react";
import { readmeAssetBase, resolveMarkdownAssetUrl } from "@/lib/image-md";
import { htmlToMarkdown } from "@/lib/markdown";

/**
 * Faithful markdown renderer for README monitors.
 *
 * `ReadableContent` is tuned for *scraped page text*: it strips HTML tags
 * and decodes entities, which mangles a README (code samples lose their
 * `<div>` tags, entities inside code blocks are rewritten, nested lists
 * collapse). This renderer keeps the markdown semantics intact and styles
 * them with the app design tokens.
 */
export function MarkdownContent({
	text,
	baseUrl,
	className = "",
}: {
	text: string;
	/** Monitor URL — used to resolve relative image/asset paths. */
	baseUrl?: string | null;
	className?: string;
}) {
	const content = text || "";
	// READMEs often embed raw HTML for layout (badges, centered logos).
	// Convert it to markdown so it renders instead of showing as text.
	const markdown = useMemo(() => htmlToMarkdown(content), [content]);
	const assetBase = readmeAssetBase(baseUrl);

	if (!content.trim()) {
		return <p className="text-sm text-[var(--ink-subtle)]">No content.</p>;
	}

	const components: Components = {
		h1: ({ children }) => (
			<h1 className="border-b border-[var(--hairline)] pb-2 pt-3 text-2xl font-bold tracking-tight text-[var(--ink)]">
				{children}
			</h1>
		),
		h2: ({ children }) => (
			<h2 className="border-b border-[var(--hairline)] pb-1.5 pt-4 text-xl font-semibold tracking-tight text-[var(--ink)]">
				{children}
			</h2>
		),
		h3: ({ children }) => (
			<h3 className="pt-3 text-lg font-semibold tracking-tight text-[var(--ink)]">{children}</h3>
		),
		h4: ({ children }) => (
			<h4 className="pt-2.5 text-base font-semibold text-[var(--ink)]">{children}</h4>
		),
		h5: ({ children }) => (
			<h5 className="pt-2 text-sm font-semibold text-[var(--ink)]">{children}</h5>
		),
		h6: ({ children }) => (
			<h6 className="pt-2 text-sm font-semibold uppercase tracking-wide text-[var(--ink-subtle)]">
				{children}
			</h6>
		),
		p: ({ children }) => (
			<p className="whitespace-pre-line leading-relaxed text-[var(--fg)]">{children}</p>
		),
		a: ({ children, href }) => (
			<a
				href={href}
				target="_blank"
				rel="noopener noreferrer"
				className="font-medium text-[var(--primary)] underline decoration-[var(--primary)]/40 underline-offset-2 hover:opacity-80"
			>
				{children}
			</a>
		),
		ul: ({ children }) => (
			<ul className="list-disc space-y-1.5 pl-6 marker:text-[var(--primary)]">{children}</ul>
		),
		ol: ({ children }) => (
			<ol className="list-decimal space-y-1.5 pl-6 marker:text-[var(--ink-subtle)]">{children}</ol>
		),
		li: ({ children }) => <li className="pl-1 leading-relaxed">{children}</li>,
		blockquote: ({ children }) => (
			<blockquote className="rounded-r-lg border-l-2 border-[var(--primary)] bg-[var(--surface-2)] px-4 py-2.5 text-[var(--ink-muted)] italic">
				{children}
			</blockquote>
		),
		hr: () => <hr className="my-4 border-[var(--hairline)]" />,
		table: ({ children }) => (
			<div className="my-3 overflow-x-auto rounded-lg border border-[var(--hairline)]">
				<table className="w-full border-collapse text-left text-sm">{children}</table>
			</div>
		),
		thead: ({ children }) => <thead className="bg-[var(--surface-2)]">{children}</thead>,
		tr: ({ children }) => (
			<tr className="border-b border-[var(--hairline)] last:border-b-0">{children}</tr>
		),
		th: ({ children }) => (
			<th className="px-3.5 py-2.5 text-left align-top text-[13.5px] font-semibold text-[var(--ink)]">
				{children}
			</th>
		),
		td: ({ children }) => (
			<td className="px-3.5 py-2.5 align-top text-[13.5px] text-[var(--ink-muted)]">{children}</td>
		),
		pre: ({ children }) => (
			<pre className="overflow-x-auto rounded-lg border border-[var(--hairline)] bg-[var(--surface-2)] p-4 text-[12.5px] leading-relaxed text-[var(--ink)]">
				{children}
			</pre>
		),
		code: ({ children, className: codeClassName }) => {
			const isBlock = Boolean(codeClassName?.startsWith("language-"));
			if (isBlock) {
				return <code className={`font-mono ${codeClassName}`}>{children}</code>;
			}
			return (
				<code className="rounded border border-[var(--hairline)] bg-[var(--surface-2)] px-1.5 py-0.5 font-mono text-[13px] text-[var(--ink)]">
					{children}
				</code>
			);
		},
		img: ({ src, alt }) => {
			const resolved = resolveMarkdownAssetUrl(typeof src === "string" ? src : "", assetBase);
			if (!resolved) {
				return <span className="italic text-[var(--ink-subtle)]">[{alt || "image"}]</span>;
			}
			return (
				// eslint-disable-next-line @next/next/no-img-element
				<img
					src={resolved}
					alt={alt || ""}
					loading="lazy"
					className="my-3 max-h-96 w-auto max-w-full rounded-lg border border-[var(--hairline)] bg-[var(--surface-2)] object-contain"
				/>
			);
		},
		input: (props) => (
			<input
				{...props}
				disabled
				className="mr-1.5 h-3.5 w-3.5 accent-[var(--primary)]"
			/>
		),
	};

	return (
		<div className={`space-y-4 text-[14.5px] leading-relaxed text-[var(--fg)] ${className}`}>
			<ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
				{markdown}
			</ReactMarkdown>
		</div>
	);
}
