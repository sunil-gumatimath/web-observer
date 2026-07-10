"use client";

import { UserButton, useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode, useState } from "react";
import { cn } from "@/components/ui";

const nav = [
  { href: "/dashboard", label: "Overview", match: (p: string) => p === "/dashboard" },
  {
    href: "/monitors",
    label: "Monitors",
    match: (p: string) => p.startsWith("/monitors") && p !== "/monitors/new",
  },
  { href: "/monitors/new", label: "New", match: (p: string) => p === "/monitors/new" },
  { href: "/import", label: "Import", match: (p: string) => p.startsWith("/import") },
  { href: "/settings", label: "Settings", match: (p: string) => p.startsWith("/settings") },
];

function Logo({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/dashboard" className="group flex items-center gap-2.5 font-semibold tracking-tight text-white">
      <span className="relative flex h-9 w-9 items-center justify-center">
        <span className="absolute inset-0 rounded-xl bg-gradient-to-br from-sky-400 to-indigo-500 opacity-90 shadow-glow-sm transition group-hover:opacity-100" />
        <span className="relative text-sm font-bold text-white">M</span>
      </span>
      {!compact ? (
        <span className="hidden sm:inline">
          Monitor<span className="text-slate-400">-the-</span>Web
        </span>
      ) : null}
    </Link>
  );
}

function ClerkAuthControls() {
  const { isSignedIn, isLoaded } = useAuth();
  if (!isLoaded) {
    return <span className="h-8 w-8 animate-pulse-soft rounded-full bg-slate-800" />;
  }
  if (!isSignedIn) {
    return (
      <div className="flex items-center gap-2">
        <Link
          href="/sign-in"
          className="rounded-lg border border-white/10 px-3 py-1.5 text-sm font-medium text-slate-200 transition hover:bg-white/5"
        >
          Sign in
        </Link>
        <Link
          href="/sign-up"
          className="rounded-lg bg-gradient-to-b from-sky-500 to-sky-600 px-3 py-1.5 text-sm font-medium text-white shadow-glow-sm transition hover:from-sky-400 hover:to-sky-500"
        >
          Sign up
        </Link>
      </div>
    );
  }
  return (
    <UserButton
      appearance={{
        elements: {
          avatarBox: "h-8 w-8 ring-2 ring-sky-500/30",
        },
      }}
    />
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname() || "";
  const [open, setOpen] = useState(false);

  return (
    <div className="min-h-screen text-slate-100">
      <header className="sticky top-0 z-40 border-b border-white/5 bg-slate-950/75 backdrop-blur-xl">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-3">
            <Logo />
            <nav className="ml-2 hidden items-center gap-0.5 md:flex">
              {nav.map((item) => {
                const active = item.match(pathname);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn("nav-link", active && "nav-link-active")}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>

          <div className="flex items-center gap-3">
            <div className="hidden items-center border-l border-white/10 pl-3 sm:flex">
              <ClerkAuthControls />
            </div>
            <button
              type="button"
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-white/10 text-slate-300 hover:bg-white/5 md:hidden"
              onClick={() => setOpen((v) => !v)}
              aria-label="Toggle menu"
            >
              {open ? (
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                </svg>
              ) : (
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.75}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
                </svg>
              )}
            </button>
          </div>
        </div>

        {open ? (
          <div className="border-t border-white/5 px-4 py-3 md:hidden">
            <nav className="flex flex-col gap-1">
              {nav.map((item) => {
                const active = item.match(pathname);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setOpen(false)}
                    className={cn("nav-link block", active && "nav-link-active")}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
            <div className="mt-3 flex items-center border-t border-white/5 pt-3 sm:hidden">
              <ClerkAuthControls />
            </div>
          </div>
        ) : null}
      </header>

      <main className="mx-auto max-w-6xl px-4 py-8 animate-fade-in-up">{children}</main>
    </div>
  );
}
