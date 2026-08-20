"use client";

import { SignIn } from "@clerk/nextjs";
import { useSyncExternalStore } from "react";
import { useTheme } from "next-themes";
import Link from "next/link";
import { LogoIcon } from "@/components/logo";
import { clerkAppearance } from "@/lib/clerk-appearance";
import { config } from "@/lib/config";

export default function SignInPage() {
	const { resolvedTheme } = useTheme();
	const mounted = useSyncExternalStore(
		() => () => undefined,
		() => true,
		() => false,
	);

	const isDark = mounted && resolvedTheme === "dark";

	// Dev mode: no Clerk keys — there is no hosted sign-in to render.
	if (config.devModeEnabled && !config.clerkEnabled) {
		return (
			<div className="relative flex min-h-screen flex-col items-center justify-center gap-6 overflow-hidden px-4 py-12 text-center">
				<div className="pointer-events-none absolute inset-0 hero-grid" />
				<div className="relative z-10">
					<h1 className="text-2xl font-semibold text-[var(--text)]">Sign-in is disabled</h1>
					<p className="mx-auto mt-2 max-w-sm text-sm text-[var(--muted)]">
						This environment runs without Clerk (dev internal-token auth). Head
						straight to the dashboard.
					</p>
					<Link
						href="/dashboard"
						className="mt-6 inline-block rounded-xl bg-gradient-to-b from-sky-500 to-sky-600 px-6 py-3 text-sm font-semibold text-white shadow-glow transition hover:from-sky-400 hover:to-sky-500"
					>
						Go to dashboard
					</Link>
				</div>
			</div>
		);
	}

	return (
		<div className="relative flex min-h-screen flex-col items-center justify-center gap-8 overflow-hidden px-4 py-12">
			<div className="pointer-events-none absolute inset-0 hero-grid" />
			<div className="relative z-10 text-center">
				<Link
					href="/"
					className="inline-flex items-center gap-2.5 font-semibold tracking-tight text-[var(--text)]"
				>
					<LogoIcon size={36} />
					<span>Web Observer</span>
				</Link>
				<h1 className="mt-4 text-2xl font-semibold text-[var(--text)]">Welcome back</h1>
				<p className="mt-1 text-sm text-[var(--muted)]">Sign in to manage your monitors</p>
			</div>
			<div className="relative z-10 w-full max-w-md">
				<SignIn
					routing="path"
					path="/sign-in"
					signUpUrl="/sign-up"
					fallbackRedirectUrl="/dashboard"
					appearance={clerkAppearance(isDark)}
				/>
			</div>
		</div>
	);
}
