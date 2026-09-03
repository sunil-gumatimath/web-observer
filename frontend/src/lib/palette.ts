export type PaletteRoute = {
	href: string;
	label: string;
	hint: string;
};

export type PaletteMonitor = {
	id: string;
	name: string;
	url: string;
	mode: string;
};

/** Case-insensitive substring match over name + url + mode. */
export function filterMonitors<T extends PaletteMonitor>(
	monitors: T[],
	query: string,
	limit = 6,
): T[] {
	const q = query.trim().toLowerCase();
	if (!q) return monitors.slice(0, limit);
	return monitors
		.filter((m) => `${m.name} ${m.url} ${m.mode}`.toLowerCase().includes(q))
		.slice(0, limit);
}

export function filterRoutes(routes: PaletteRoute[], query: string): PaletteRoute[] {
	const q = query.trim().toLowerCase();
	if (!q) return routes;
	return routes.filter((r) =>
		`${r.label} ${r.hint}`.toLowerCase().includes(q),
	);
}

/** Clamp a selection index to a valid item — Enter must never dead-end. */
export function clampIndex(active: number, length: number): number {
	if (length <= 0) return 0;
	return Math.min(Math.max(0, active), length - 1);
}
