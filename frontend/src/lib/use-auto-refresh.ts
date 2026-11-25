"use client";

import { useEffect, useRef } from "react";

/**
 * Interval refresh that respects tab visibility and refreshes on return.
 *
 * The list/dashboard/alerts pages previously refreshed on a flat 60s timer with
 * no other trigger, so a completed check could sit invisible for up to a minute
 * and read as "the UI needs a reload". This shortens the cadence and — more
 * importantly — refreshes immediately when the tab becomes visible or the window
 * regains focus, which is exactly when a user looks back expecting current data.
 *
 * The timer is suspended while the tab is hidden so background tabs don't burn
 * requests.
 *
 * The callback is held in a ref, so callers can pass an inline arrow without
 * re-creating the timer on every render.
 */
export function useAutoRefresh(
	onTick: () => void,
	intervalMs = 15_000,
	minRefreshGapMs = 3_000,
): void {
	const tickRef = useRef(onTick);
	const lastTickAtRef = useRef(0);

	useEffect(() => {
		tickRef.current = onTick;
	}, [onTick]);

	useEffect(() => {
		let id: number | null = null;
		// Seed initial mount time so an immediate focus event doesn't double-fetch
		// right after the page's own initial load.
		lastTickAtRef.current = Date.now();

		const fire = () => {
			lastTickAtRef.current = Date.now();
			tickRef.current();
		};

		const fireIfStale = () => {
			if (Date.now() - lastTickAtRef.current < minRefreshGapMs) return;
			fire();
		};

		const start = () => {
			if (id != null) return;
			id = window.setInterval(fire, intervalMs);
		};
		const stop = () => {
			if (id == null) return;
			window.clearInterval(id);
			id = null;
		};

		const onVisibilityChange = () => {
			if (document.visibilityState === "visible") {
				// Data is stale after being away: refresh now rather than waiting
				// out the remaining interval, while coalescing with window focus.
				fireIfStale();
				start();
			} else {
				stop();
			}
		};
		const onFocus = () => {
			if (document.visibilityState === "visible") {
				fireIfStale();
			}
		};

		if (document.visibilityState === "visible") start();
		document.addEventListener("visibilitychange", onVisibilityChange);
		window.addEventListener("focus", onFocus);

		return () => {
			stop();
			document.removeEventListener("visibilitychange", onVisibilityChange);
			window.removeEventListener("focus", onFocus);
		};
	}, [intervalMs, minRefreshGapMs]);
}
