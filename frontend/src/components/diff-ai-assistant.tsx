"use client";

import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "@/components/ui";
import { api } from "@/lib/api";

interface DiffAiAssistantProps {
  workspaceId: string;
  changeId: string;
}

const QUICK_PROMPTS = [
  "Draft an executive briefing",
  "Is there any pricing or fee change?",
  "What was deleted?",
  "Write a Slack team update",
];

export function DiffAiAssistant({ workspaceId, changeId }: DiffAiAssistantProps) {
  const [isOpen, setIsOpen] = useState(true);
  const [copied, setCopied] = useState(false);
  const [activePrompt, setActivePrompt] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [completion, setCompletion] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const askAi = async (promptText: string) => {
    const prompt = promptText.trim();
    if (!prompt || isLoading) return;

    setActivePrompt(prompt);
    setError(null);
    setIsLoading(true);
    try {
      const response = await api.askChangeAi(workspaceId, changeId, prompt);
      setCompletion(response.text);
    } catch (e) {
      setError(e instanceof Error ? e.message : "AI analysis failed");
    } finally {
      setIsLoading(false);
    }
  };

  const handleQuickPrompt = (promptText: string) => {
    setInput(promptText);
    void askAi(promptText);
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    void askAi(input);
  };

  const handleCopy = () => {
    if (!completion) return;
    navigator.clipboard?.writeText(completion).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="rounded-[12px] border border-[var(--hairline)] bg-[var(--surface-1)] overflow-hidden transition-all duration-150">
      {/* Header bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 border-b border-[var(--hairline)]">
        <div className="flex items-center gap-2.5">
          <span className="flex size-6 items-center justify-center rounded-[6px] bg-[var(--primary)]/10 text-[var(--primary-hover)]">
            <svg className="size-3.5" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8L12 2z" />
            </svg>
          </span>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--fg)]">
                Ask AI Analyst
              </h3>
              <span className="rounded-full bg-[var(--primary)]/10 px-2 py-0.2 text-[10px] font-medium text-[var(--primary-hover)] border border-[var(--primary)]/20">
                Workspace AI
              </span>
            </div>
            <p className="text-[11px] text-[var(--muted)]">
              Ask questions about this diff &amp; web change
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
        <div className="p-4 flex flex-col gap-3">
          <p className="text-xs text-[var(--muted)]">
            Your change diff is sent to the workspace-configured external AI provider.
          </p>

          {/* Quick Prompts */}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs font-medium text-[var(--muted)]">
              Quick prompts:
            </span>
            {QUICK_PROMPTS.map((prompt) => (
              <button
                key={prompt}
                type="button"
                disabled={isLoading}
                onClick={() => handleQuickPrompt(prompt)}
                className="rounded-[6px] border border-[var(--hairline)] bg-[var(--surface-2)] px-2.5 py-1 text-xs font-medium text-[var(--ink-muted)] hover:text-[var(--fg)] hover:border-[var(--hairline-strong)] disabled:opacity-50 transition-colors"
              >
                {prompt} →
              </button>
            ))}
          </div>

          {/* Response Container */}
          {completion ? (
            <div className="rounded-[8px] border border-[var(--hairline)] bg-[var(--canvas)] p-3.5 shadow-xs">
              <div className="flex items-center justify-between pb-2 mb-2 border-b border-[var(--hairline)] text-xs text-[var(--muted)]">
                <span className="font-medium text-[var(--primary-hover)] flex items-center gap-1.5">
                  <span className="size-1.5 rounded-full bg-[var(--primary)]" />
                  {activePrompt ? `Analysis: "${activePrompt}"` : "AI Intelligence Analysis"}
                </span>
                <div className="flex items-center gap-2">
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
                      <h1 className="text-sm font-semibold text-[var(--fg)] mt-2.5 mb-1.5 first:mt-0">
                        {children}
                      </h1>
                    ),
                    h2: ({ children }) => (
                      <h2 className="text-xs font-semibold text-[var(--fg)] mt-2 mb-1 border-b border-[var(--hairline)] pb-1">
                        {children}
                      </h2>
                    ),
                    h3: ({ children }) => (
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--primary-hover)] mt-2 mb-0.5">
                        {children}
                      </h3>
                    ),
                    p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed text-xs">{children}</p>,
                    ul: ({ children }) => <ul className="mb-2.5 ml-4 list-disc space-y-1 text-xs">{children}</ul>,
                    ol: ({ children }) => <ol className="mb-2.5 ml-4 list-decimal space-y-1 text-xs">{children}</ol>,
                    li: ({ children }) => <li className="leading-relaxed">{children}</li>,
                    strong: ({ children }) => (
                      <strong className="font-semibold text-[var(--fg)]">{children}</strong>
                    ),
                    table: ({ children }) => (
                      <div className="my-2 overflow-x-auto rounded-[6px] border border-[var(--hairline)]">
                        <table className="min-w-full divide-y divide-[var(--hairline)] text-xs">
                          {children}
                        </table>
                      </div>
                    ),
                    thead: ({ children }) => (
                      <thead className="bg-[var(--surface-2)] font-semibold text-[var(--fg)]">
                        {children}
                      </thead>
                    ),
                    tbody: ({ children }) => (
                      <tbody className="divide-y divide-[var(--hairline)] bg-[var(--surface-1)]">
                        {children}
                      </tbody>
                    ),
                    tr: ({ children }) => (
                      <tr className="hover:bg-[var(--surface-2)] transition-colors">
                        {children}
                      </tr>
                    ),
                    th: ({ children }) => <th className="px-3 py-1.5 text-left font-medium">{children}</th>,
                    td: ({ children }) => <td className="px-3 py-1.5 text-[var(--ink-muted)]">{children}</td>,
                    code: ({ children }) => (
                      <code className="rounded bg-[var(--surface-2)] border border-[var(--hairline)] px-1 py-0.2 font-mono text-[11px] text-[var(--primary-hover)]">
                        {children}
                      </code>
                    ),
                    blockquote: ({ children }) => (
                      <blockquote className="border-l-2 border-[var(--primary)] pl-2.5 my-1.5 text-[var(--muted)] italic">
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
            <div className="rounded-[8px] border border-[var(--hairline)] bg-[var(--surface-2)] p-4 text-center">
              <div className="flex items-center justify-center gap-2 text-xs text-[var(--primary-hover)] font-medium">
                <div className="size-1.5 rounded-full bg-[var(--primary)] animate-pulse" />
                <span>AI Analyst is preparing analysis…</span>
              </div>
            </div>
          ) : null}

          {error && (
            <div className="rounded-[6px] border border-red-500/30 bg-red-500/10 p-2.5 text-xs text-red-400">
              Analysis error: {error}
            </div>
          )}

          {/* Input Form */}
          <form onSubmit={handleFormSubmit} className="flex gap-2 pt-1">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask anything about this diff (e.g. security risks, executive summary, pricing changes)..."
              disabled={isLoading}
              className="field flex-1 text-xs"
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
