"use client";

import { SignIn } from "@clerk/nextjs";
import { useEffect, useState } from "react";
import { useTheme } from "next-themes";
import Link from "next/link";
import { clerkAppearance } from "@/lib/clerk-appearance";

export default function SignInPage() {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const isDark = mounted && resolvedTheme === "dark";

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center gap-8 overflow-hidden px-4 py-12">
      <div className="pointer-events-none absolute inset-0 hero-grid" />
      <div className="relative z-10 text-center">
        <Link
          href="/"
          className="inline-flex items-center gap-2.5 font-semibold tracking-tight text-slate-900 dark:text-white"
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-sky-400 to-indigo-500 text-sm font-bold shadow-glow-sm">
            W
          </span>
          <span>Web Observer</span>
        </Link>
        <h1 className="mt-4 text-2xl font-semibold text-slate-900 dark:text-white">Welcome back</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Sign in to manage your monitors</p>
      </div>
      <div className="relative z-10 w-full max-w-md">
        <SignIn
          routing="path"
          path="/sign-in"
          signUpUrl="/sign-up"
          fallbackRedirectUrl="/dashboard"
          forceRedirectUrl="/dashboard"
          appearance={clerkAppearance(isDark)}
        />
      </div>
    </div>
  );
}
