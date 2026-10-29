"use client";

import { useEffect, useState } from "react";
import { cn } from "@/components/ui";

interface NavClockProps {
	className?: string;
}

export function NavClock({ className }: NavClockProps) {
	const [time, setTime] = useState<string>("");

	useEffect(() => {
		const updateTime = () => {
			setTime(
				new Intl.DateTimeFormat(undefined, {
					hour: "numeric",
					minute: "2-digit",
					hour12: true,
				}).format(new Date()),
			);
		};

		updateTime();
		const interval = setInterval(updateTime, 60_000);
		return () => clearInterval(interval);
	}, []);

	return (
		<span
			className={cn(
				"_navClock _navClock_1rexy_252 inline-flex items-center select-none text-xs text-[var(--muted,#8a8f98)] font-mono sm:font-sans tracking-tight",
				className,
			)}
			aria-hidden="true"
		>
			<span
				className="navClock tabular-nums font-normal"
				aria-label="Local time"
				title="Local time"
			>
				{time || <span className="opacity-0">0:00 AM</span>}
			</span>
		</span>
	);
}
