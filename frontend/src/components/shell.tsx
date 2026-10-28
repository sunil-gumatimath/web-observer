"use client";

import { UserButton, useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { Logo } from "@/components/logo";
import { cn } from "@/components/ui";
import { ThemeToggle } from "@/components/theme-toggle";
import { NavClock } from "@/components/nav-clock";
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
		href: "/logs",
		label: "Logs",
		match: (p: string) => p.startsWith("/logs"),
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
			className="flex items-center gap-2.5 tracking-tight text-[var(--fg)]"
		>
			<Logo compact={compact} iconSize={32} />
		</Link>
	);
}

function ClerkAuthControls() {
	if (!config.clerkEnabled) {
		// Dev mode: no Clerk session. The app authenticates via the backend
		// X-Internal-Token; show a static dev indicator instead of auth buttons.
		return (
			<span
				suppressHydrationWarning
				title="Dev mode — internal token auth"
				className="rounded-[8px] border border-[var(--hairline)] bg-[var(--surface-1)] px-2.5 py-1 text-xs font-medium text-[var(--muted)]"
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
			<span suppressHydrationWarning className="h-7 w-7 animate-pulse-soft rounded-full bg-[var(--surface-2)]" />
		);
	}
	if (!isSignedIn) {
		return (
			<div className="flex items-center gap-2" suppressHydrationWarning>
				<Link
					href="/sign-in"
					className="rounded-[8px] border border-[var(--hairline)] bg-[var(--surface-1)] px-2.5 py-1 text-xs font-medium text-[var(--fg)] transition hover:bg-[var(--surface-2)] hover:border-[var(--hairline-strong)] active:bg-[var(--surface-3)]"
				>
					Sign in
				</Link>
				<Link
					href="/sign-up"
					className="rounded-[8px] bg-[var(--primary)] px-2.5 py-1 text-xs font-medium text-white transition hover:bg-[var(--primary-hover)] active:bg-[var(--primary-focus)]"
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
					avatarBox: "h-7 w-7 ring-1 ring-[var(--hairline-strong)]",
				},
			}}
		/>
	);
}

/** Workspace switcher — switch between workspaces you belong to. */
function WorkspaceSwitcher() {
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
			className="hidden max-w-[10rem] rounded-[8px] border border-[var(--hairline)] bg-[var(--surface-1)] px-2 py-1 text-xs text-[var(--fg)] sm:block"
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

	return (
		<div className="min-h-screen bg-[var(--bg)] text-[var(--fg)]" suppressHydrationWarning>
			<header
				className="sticky top-0 z-40 h-14 border-b border-[var(--hairline)] bg-[var(--bg)]/90 backdrop-blur-md"
				suppressHydrationWarning
			>
				<div className="mx-auto flex h-full max-w-6xl items-center justify-between gap-4 px-4" suppressHydrationWarning>
					<div className="flex items-center gap-4" suppressHydrationWarning>
						<HeaderLogo />
						<nav className="hidden items-center gap-1 md:flex" suppressHydrationWarning>
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

					<div className="flex items-center gap-2 sm:gap-2.5" suppressHydrationWarning>
						<WorkspaceSwitcher />
						<NavClock className="hidden md:inline-flex px-1" />
						<ThemeToggle />
						<div className="hidden items-center border-l border-[var(--hairline)] pl-2.5 sm:flex" suppressHydrationWarning>
							<ClerkAuthControls />
						</div>
						<button
							type="button"
							className="inline-flex h-8 w-8 items-center justify-center rounded-[8px] border border-[var(--hairline)] bg-[var(--surface-1)] text-[var(--muted)] transition hover:text-[var(--fg)] hover:bg-[var(--surface-2)] active:bg-[var(--surface-3)] md:hidden"
							onClick={() => setOpen((v) => !v)}
							aria-label="Toggle menu"
							aria-expanded={open}
							aria-controls="mobile-nav"
						>
							{open ? (
								<svg
									className="h-4 w-4"
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
									className="h-4 w-4"
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
						className="border-b border-[var(--hairline)] bg-[var(--surface-1)] px-4 py-3 md:hidden"
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
											"nav-link flex min-h-[36px] items-center px-3",
											active && "nav-link-active",
										)}
									>
										{item.label}
									</Link>
								);
							})}
						</nav>
						<div className="mt-3 flex items-center border-t border-[var(--hairline)] pt-3 sm:hidden" suppressHydrationWarning>
							<ClerkAuthControls />
						</div>
					</div>
				) : null}
			</header>

			<main
				key={pathname}
				className="mx-auto max-w-6xl px-4 py-8 animate-fade-in-up"
				suppressHydrationWarning
			>
				{children}
			</main>
		</div>
	);
}
