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
			const now = new Date();
			const hours = String(now.getHours()).padStart(2, "0");
			const minutes = String(now.getMinutes()).padStart(2, "0");
			const seconds = String(now.getSeconds()).padStart(2, "0");
			setTime(`${hours}:${minutes}:${seconds}`);
		};

		updateTime();
		const interval = setInterval(updateTime, 1000);
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
				{time || <span className="opacity-0">00:00:00</span>}
			</span>
		</span>
	);
}
