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
export function useAutoRefresh(onTick: () => void, intervalMs = 15_000): void {
	const tickRef = useRef(onTick);

	useEffect(() => {
		tickRef.current = onTick;
	}, [onTick]);

	useEffect(() => {
		let id: number | null = null;

		const start = () => {
			if (id != null) return;
			id = window.setInterval(() => tickRef.current(), intervalMs);
		};
		const stop = () => {
			if (id == null) return;
			window.clearInterval(id);
			id = null;
		};

		const onVisibilityChange = () => {
			if (document.visibilityState === "visible") {
				// Data is stale by definition after being away: refresh now
				// rather than waiting out the remaining interval.
				tickRef.current();
				start();
			} else {
				stop();
			}
		};
		const onFocus = () => tickRef.current();

		if (document.visibilityState === "visible") start();
		document.addEventListener("visibilitychange", onVisibilityChange);
		window.addEventListener("focus", onFocus);

		return () => {
			stop();
			document.removeEventListener("visibilitychange", onVisibilityChange);
			window.removeEventListener("focus", onFocus);
		};
	}, [intervalMs]);
}
