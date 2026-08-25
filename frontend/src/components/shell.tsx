"use client";

import { UserButton, useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { Logo } from "@/components/logo";
import { cn } from "@/components/ui";
import { ThemeToggle } from "@/components/theme-toggle";
import { api } from "@/lib/api";
import { config } from "@/lib/config";
import { invalidateWorkspace, setStoredWorkspaceId } from "@/lib/workspace";

const nav = [
	{
		href: "/dashboard",
		label: "Overview",
		match: (p: string) => p === "/dashboard",
	},
	{
		href: "/monitors",
		label: "Monitors",
		match: (p: string) => p.startsWith("/monitors"),
	},
	{
		href: "/alerts",
		label: "Alerts",
		match: (p: string) => p.startsWith("/alerts"),
	},
	{
		href: "/import",
		label: "Import",
		match: (p: string) => p.startsWith("/import"),
	},
	{ href: "/docs", label: "Docs", match: (p: string) => p.startsWith("/docs") },
	{
		href: "/settings",
		label: "Settings",
		match: (p: string) => p.startsWith("/settings"),
	},
];

function HeaderLogo({ compact = false }: { compact?: boolean }) {
	return (
		<Link
			href="/dashboard"
			className="flex items-center gap-2.5 font-semibold tracking-tight text-slate-900 dark:text-white"
		>
			<Logo compact={compact} iconSize={36} />
		</Link>
	);
}

function ClerkAuthControls() {
	if (!config.clerkEnabled) {
		// Dev mode: no Clerk session. The app authenticates via the backend
		// X-Internal-Token; show a static dev indicator instead of auth buttons.
		// suppressHydrationWarning: Retriever / other extensions inject rtrvr-ls attributes before hydrate
		return (
			<span
				suppressHydrationWarning
				title="Dev mode — internal token auth"
				className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 dark:border-white/10 dark:text-slate-300"
			>
				Dev
			</span>
		);
	}
	return <ClerkUserControls />;
}

function ClerkUserControls() {
	const { isSignedIn, isLoaded } = useAuth();
	if (!isLoaded) {
		return (
			<span suppressHydrationWarning className="h-8 w-8 animate-pulse-soft rounded-full bg-slate-200 dark:bg-slate-800" />
		);
	}
	if (!isSignedIn) {
		return (
			<div className="flex items-center gap-2" suppressHydrationWarning>
				<Link
					href="/sign-in"
					className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 transition hover:bg-slate-100 dark:border-white/10 dark:text-slate-200 dark:hover:bg-white/5"
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

/** webdog.ai-parity account switcher — switch between workspaces you belong to. */
function WorkspaceSwitcher() {
	// In dev mode (no Clerk) there is no <ClerkProvider>, so calling useAuth()
	// would throw "useAuth can only be used within the <ClerkProvider />".
	// The switcher only makes sense with a session, so render nothing.
	if (!config.clerkEnabled) return null;
	return <ClerkWorkspaceSwitcher />;
}

function ClerkWorkspaceSwitcher() {
	const [workspaces, setWorkspaces] = useState<Array<{ id: string; name: string }> | null>(null);
	const [current, setCurrent] = useState("");
	const { isLoaded, isSignedIn } = useAuth();

	useEffect(() => {
		if (!isLoaded || !isSignedIn) return;
		api
			.me()
			.then((me) => {
				setWorkspaces(me.workspaces);
				const preferred =
					typeof window !== "undefined"
						? localStorage.getItem("web_observer_workspace_id")
						: null;
				const first = me.workspaces[0]?.id ?? "";
				setCurrent(me.workspaces.some((w) => w.id === preferred) ? String(preferred) : first);
			})
			.catch(() => setWorkspaces(null));
	}, [isLoaded, isSignedIn]);

	if (!workspaces || workspaces.length <= 1) return null;

	return (
		<select
			aria-label="Switch workspace"
			value={current}
			className="hidden max-w-[10rem] rounded-lg border border-[var(--border)] bg-[var(--field-bg)] px-2 py-1.5 text-xs text-[var(--text)] sm:block"
			onChange={(e) => {
				const id = e.target.value;
				setCurrent(id);
				setStoredWorkspaceId(id);
				invalidateWorkspace();
				window.location.href = "/dashboard";
			}}
		>
			{workspaces.map((w) => (
				<option key={w.id} value={w.id}>
					{w.name}
				</option>
			))}
		</select>
	);
}

export function AppShell({ children }: { children: ReactNode }) {
	const pathname = usePathname() || "";
	const [open, setOpen] = useState(false);

	// Close the mobile menu on route change and on Escape.
	useEffect(() => {
		const close = window.setTimeout(() => setOpen(false), 0);
		return () => window.clearTimeout(close);
	}, [pathname]);
	useEffect(() => {
		if (!open) return;
		function onKey(e: KeyboardEvent) {
			if (e.key === "Escape") setOpen(false);
		}
		window.addEventListener("keydown", onKey);
		return () => window.removeEventListener("keydown", onKey);
	}, [open]);

	// suppressHydrationWarning: browser extensions (e.g. Retriever) inject attributes
	// like `rtrvr-ls` into the DOM before React hydrates, which is not an app bug.
	return (
		<div className="min-h-screen text-[var(--text)]" suppressHydrationWarning>
			<header
				className="sticky top-0 z-40 border-b border-[var(--border)] bg-[var(--bg-elevated)]/75 backdrop-blur-xl"
				suppressHydrationWarning
			>
				<div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3" suppressHydrationWarning>
					<div className="flex items-center gap-3" suppressHydrationWarning>
						<HeaderLogo />
						<nav className="ml-2 hidden items-center gap-0.5 md:flex" suppressHydrationWarning>
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

					<div className="flex items-center gap-3" suppressHydrationWarning>
						<WorkspaceSwitcher />
						<ThemeToggle />
						<div className="hidden items-center border-l border-[var(--border)] pl-3 sm:flex" suppressHydrationWarning>
							<ClerkAuthControls />
						</div>
						<button
							type="button"
							className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--border)] text-[var(--muted)] hover:bg-[var(--nav-active-bg)] hover:text-[var(--text)] md:hidden"
							onClick={() => setOpen((v) => !v)}
							aria-label="Toggle menu"
							aria-expanded={open}
							aria-controls="mobile-nav"
						>
							{open ? (
								<svg
									className="h-5 w-5"
									fill="none"
									viewBox="0 0 24 24"
									stroke="currentColor"
									strokeWidth={1.75}
								>
									<path
										strokeLinecap="round"
										strokeLinejoin="round"
										d="M6 18 18 6M6 6l12 12"
									/>
								</svg>
							) : (
								<svg
									className="h-5 w-5"
									fill="none"
									viewBox="0 0 24 24"
									stroke="currentColor"
									strokeWidth={1.75}
								>
									<path
										strokeLinecap="round"
										strokeLinejoin="round"
										d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"
									/>
								</svg>
							)}
						</button>
					</div>
				</div>

				{open ? (
					<div
						id="mobile-nav"
						className="border-t border-[var(--border)] px-4 py-3 md:hidden"
						suppressHydrationWarning
					>
						<nav className="flex flex-col gap-1" suppressHydrationWarning>
							{nav.map((item) => {
								const active = item.match(pathname);
								return (
									<Link
										key={item.href}
										href={item.href}
										onClick={() => setOpen(false)}
										className={cn(
											"nav-link block",
											active && "nav-link-active",
										)}
									>
										{item.label}
									</Link>
								);
							})}
						</nav>
						<div className="mt-3 flex items-center border-t border-[var(--border)] pt-3 sm:hidden" suppressHydrationWarning>
							<ClerkAuthControls />
						</div>
					</div>
				) : null}
			</header>

			<main
				className="mx-auto max-w-6xl px-4 py-8 animate-fade-in-up"
				suppressHydrationWarning
			>
				{children}
			</main>
		</div>
	);
}
