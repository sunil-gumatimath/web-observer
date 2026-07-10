"use client";

import { SignIn } from "@clerk/nextjs";
import Link from "next/link";

const clerkAppearance = {
  variables: {
    colorPrimary: "#0ea5e9",
    colorBackground: "#0b1220",
    colorInputBackground: "#020617",
    colorInputText: "#e2e8f0",
    colorText: "#e2e8f0",
    colorTextSecondary: "#94a3b8",
    borderRadius: "0.75rem",
  },
  elements: {
    rootBox: "mx-auto w-full max-w-md",
    card: "border border-white/10 bg-slate-900/80 shadow-2xl shadow-black/40 backdrop-blur-xl",
    headerTitle: "text-white",
    headerSubtitle: "text-slate-400",
    socialButtonsBlockButton:
      "border border-white/10 bg-slate-950/60 text-slate-100 hover:bg-slate-800",
    formButtonPrimary:
      "bg-sky-600 hover:bg-sky-500 text-white shadow-lg shadow-sky-500/20",
    footerActionLink: "text-sky-400 hover:text-sky-300",
    formFieldInput: "border-white/10 bg-slate-950 text-slate-100",
  },
};

export default function SignInPage() {
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center gap-8 overflow-hidden px-4 py-12">
      <div className="pointer-events-none absolute inset-0 hero-grid" />
      <div className="relative z-10 text-center">
        <Link href="/" className="inline-flex items-center gap-2.5 font-semibold tracking-tight text-white">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-sky-400 to-indigo-500 text-sm font-bold shadow-glow-sm">
            M
          </span>
          <span>
            Monitor<span className="text-slate-400">-the-</span>Web
          </span>
        </Link>
        <h1 className="mt-4 text-2xl font-semibold text-white">Welcome back</h1>
        <p className="mt-1 text-sm text-slate-400">Sign in to manage your monitors</p>
      </div>
      <div className="relative z-10 w-full max-w-md">
        <SignIn
          routing="path"
          path="/sign-in"
          signUpUrl="/sign-up"
          fallbackRedirectUrl="/dashboard"
          forceRedirectUrl="/dashboard"
          appearance={clerkAppearance}
        />
      </div>
    </div>
  );
}
