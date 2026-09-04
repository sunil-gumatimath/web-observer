"use client";

import React, { useState } from "react";
import { useCompletion } from "@ai-sdk/react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "@/components/ui";

interface DiffAiAssistantProps {
  monitorName?: string;
  changeTitle?: string | null;
  impact?: string | null;
  category?: string | null;
  diffText?: string | null;
}

const QUICK_PROMPTS = [
  "Draft an executive briefing",
  "Is there any pricing or fee change?",
  "What was deleted?",
  "Write a Slack team update",
];

export function DiffAiAssistant({
  monitorName,
  changeTitle,
  impact,
  category,
  diffText,
}: DiffAiAssistantProps) {
  const [isOpen, setIsOpen] = useState(true);
  const [copied, setCopied] = useState(false);
  const [activePrompt, setActivePrompt] = useState<string | null>(null);

  const { completion, input, setInput, complete, isLoading, error, stop } = useCompletion({
    api: "/api/ai/ask-diff",
    streamProtocol: "text",
    body: {
      monitorName,
      changeTitle,
      impact,
      category,
      diffText: diffText || "",
    },
  });

  const handleQuickPrompt = (promptText: string) => {
    setInput(promptText);
    setActivePrompt(promptText);
    complete(promptText);
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    setActivePrompt(input);
    complete(input);
  };

  const handleCopy = () => {
    if (!completion) return;
    navigator.clipboard?.writeText(completion).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="rounded-2xl border border-[var(--accent)]/25 bg-[var(--bg)] dark:border-[var(--accent)]/20 overflow-hidden transition-all duration-200">
      {/* Header bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-3.5 border-b border-[var(--border)] dark:border-[var(--border)]">
        <div className="flex items-center gap-2.5">
          <span className="flex size-7 items-center justify-center rounded-lg bg-[var(--accent)]/10 text-[var(--accent)]">
            <svg className="size-4" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8L12 2z" />
            </svg>
          </span>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                Ask AI Analyst
              </h3>
              <span className="rounded-full bg-[var(--accent)]/10 px-2 py-0.5 text-[10px] font-semibold text-[var(--muted)]">
                Vercel AI SDK
              </span>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Interactive streaming analysis of this diff &amp; web change
            </p>
          </div>
        </div>

        <Button
          size="sm"
          variant={isOpen ? "secondary" : "primary"}
          onClick={() => setIsOpen(!isOpen)}
          className="text-xs shrink-0"
        >
          {isOpen ? "Collapse Assistant" : "Open Assistant ✦"}
        </Button>
      </div>

      {/* Expandable Body */}
      {isOpen && (
        <div className="p-5 flex flex-col gap-4">
          {/* Quick Prompts */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400">
              Quick prompts:
            </span>
            {QUICK_PROMPTS.map((prompt) => (
              <button
                key={prompt}
                type="button"
                disabled={isLoading}
                onClick={() => handleQuickPrompt(prompt)}
                className="rounded-lg border border-[var(--border)] bg-white px-2.5 py-1 text-xs font-medium text-[var(--fg-2)] shadow-xs hover:bg-[var(--surface)] disabled:opacity-50 dark:bg-slate-900 transition-colors"
              >
                {prompt} →
              </button>
            ))}
          </div>

          {/* Response Container */}
          {completion ? (
            <div className="rounded-xl border border-slate-200/90 bg-white p-4.5 shadow-xs dark:border-slate-800 dark:bg-slate-900/90">
              <div className="flex items-center justify-between pb-2 mb-2.5 border-b border-slate-100 dark:border-slate-800 text-xs text-slate-500 dark:text-slate-400">
                <span className="font-semibold uppercase tracking-wider text-[var(--accent)] flex items-center gap-1.5">
                  <span className="size-1.5 rounded-full bg-[var(--accent)]" />
                  {activePrompt ? `Analysis: "${activePrompt}"` : "AI Intelligence Analysis"}
                </span>
                <div className="flex items-center gap-2">
                  {isLoading && (
                    <Button size="sm" variant="secondary" onClick={stop} className="text-xs h-6 px-2">
                      Stop generating
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" onClick={handleCopy} className="text-xs h-6 px-2">
                    {copied ? "✓ Copied" : "Copy"}
                  </Button>
                </div>
              </div>
              <div className="text-sm leading-relaxed text-[var(--fg)]">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    h1: ({ children }) => (
                      <h1 className="text-base font-bold text-slate-900 dark:text-white mt-3 mb-2 first:mt-0">
                        {children}
                      </h1>
                    ),
                    h2: ({ children }) => (
                      <h2 className="text-sm font-bold text-slate-900 dark:text-white mt-3 mb-1.5 border-b border-slate-100 dark:border-slate-800 pb-1">
                        {children}
                      </h2>
                    ),
                    h3: ({ children }) => (
                      <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--accent)] mt-2.5 mb-1">
                        {children}
                      </h3>
                    ),
                    p: ({ children }) => <p className="mb-2.5 last:mb-0 leading-relaxed">{children}</p>,
                    ul: ({ children }) => <ul className="mb-3 ml-4 list-disc space-y-1">{children}</ul>,
                    ol: ({ children }) => <ol className="mb-3 ml-4 list-decimal space-y-1">{children}</ol>,
                    li: ({ children }) => <li className="leading-relaxed">{children}</li>,
                    strong: ({ children }) => (
                      <strong className="font-semibold text-slate-950 dark:text-white">{children}</strong>
                    ),
                    table: ({ children }) => (
                      <div className="my-3 overflow-x-auto rounded-xl border border-slate-200 shadow-xs dark:border-slate-800">
                        <table className="min-w-full divide-y divide-slate-200 text-xs dark:divide-slate-800">
                          {children}
                        </table>
                      </div>
                    ),
                    thead: ({ children }) => (
                      <thead className="bg-slate-50 font-semibold text-slate-900 dark:bg-slate-800/60 dark:text-slate-100">
                        {children}
                      </thead>
                    ),
                    tbody: ({ children }) => (
                      <tbody className="divide-y divide-slate-100 bg-white dark:divide-slate-800/40 dark:bg-slate-900/40">
                        {children}
                      </tbody>
                    ),
                    tr: ({ children }) => (
                      <tr className="hover:bg-[var(--surface)] transition-colors">
                        {children}
                      </tr>
                    ),
                    th: ({ children }) => <th className="px-3 py-2 text-left font-semibold">{children}</th>,
                    td: ({ children }) => <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{children}</td>,
                    code: ({ children }) => (
                      <code className="rounded bg-[var(--surface)] border border-[var(--border-soft)] px-1.5 py-0.5 font-mono text-[11px] text-[var(--accent)]">
                        {children}
                      </code>
                    ),
                    blockquote: ({ children }) => (
                      <blockquote className="border-l-2 border-[var(--accent)] pl-3 my-2 text-slate-600 dark:text-slate-400 italic">
                        {children}
                      </blockquote>
                    ),
                  }}
                >
                  {completion}
                </ReactMarkdown>
              </div>
            </div>
          ) : isLoading ? (
            <div className="rounded-xl border border-[var(--border-soft)] bg-[var(--surface)] p-5 text-center">
              <div className="flex items-center justify-center gap-2 text-xs text-[var(--accent)] font-medium">
                <div className="size-2 rounded-full bg-[var(--accent)] animate-pulse" />
                <span>AI Analyst is streaming analysis…</span>
              </div>
            </div>
          ) : null}

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-300">
              Analysis error: {error.message}
            </div>
          )}

          {/* Input Form */}
          <form onSubmit={handleFormSubmit} className="flex gap-2 pt-1">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask anything about this diff (e.g. security risks, executive summary, pricing changes)..."
              disabled={isLoading}
              className="flex-1 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-[var(--focus-purple)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] dark:border-slate-800 dark:bg-slate-900 dark:text-white dark:placeholder:text-slate-500 disabled:opacity-50"
            />
            <Button
              type="submit"
              size="sm"
              disabled={isLoading || !input.trim()}
              className="shrink-0 font-medium"
            >
              {isLoading ? "Analyzing…" : "Ask AI ✦"}
            </Button>
          </form>
        </div>
      )}
    </div>
  );
}
