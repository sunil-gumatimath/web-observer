import { describe, expect, it, vi, afterEach } from "vitest";
import { relativeTime } from "@/lib/format";

afterEach(() => {
	vi.useRealTimers();
});

describe("relativeTime", () => {
	it("says just now under a minute", () => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date("2026-09-11T12:00:30Z"));
		expect(relativeTime("2026-09-11T12:00:00Z")).toBe("just now");
	});

	it("formats minutes, hours, days", () => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date("2026-09-11T12:00:00Z"));
		expect(relativeTime("2026-09-11T11:55:00Z")).toBe("5m ago");
		expect(relativeTime("2026-09-11T09:00:00Z")).toBe("3h ago");
		expect(relativeTime("2026-08-30T12:00:00Z")).toBe("12d ago");
	});
});
