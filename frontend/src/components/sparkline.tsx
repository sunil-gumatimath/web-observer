"use client";

type Props = {
  values: number[];
  width?: number;
  height?: number;
  label?: string;
};

/** Zero-dependency SVG sparkline + area fill. Theme-aware via currentColor. */
export function Sparkline({ values, width = 220, height = 48, label }: Props) {
  const max = Math.max(1, ...values);
  const min = Math.min(0, ...values);
  const span = Math.max(1, max - min);
  const n = values.length;
  const stepX = n > 1 ? width / (n - 1) : width;

  const points = values.map((v, i) => {
    const x = n > 1 ? i * stepX : width / 2;
    const y = height - 4 - ((v - min) / span) * (height - 10);
    return [x, y] as const;
  });

  const line =
    points.length === 1
      ? `M 0 ${points[0][1]} L ${width} ${points[0][1]}`
      : points.map(([x, y], i) => `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  const area = `${line} L ${width} ${height} L 0 ${height} Z`;
  const last = points[points.length - 1];

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={label ?? `Trend over ${n} points`}
      className="text-sky-500 dark:text-sky-400"
    >
      <path d={area} fill="currentColor" opacity={0.12} stroke="none" />
      <path d={line} fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinejoin="round" strokeLinecap="round" />
      {last ? <circle cx={last[0]} cy={last[1]} r={2.75} fill="currentColor" /> : null}
    </svg>
  );
}

/** 14-day bar strip for dashboard activity. Pure divs, no chart lib. */
export function ActivityBars({ values, labels }: { values: number[]; labels: string[] }) {
  const max = Math.max(1, ...values);
  return (
    <div className="flex items-end gap-1" role="img" aria-label="Changes per day, last 14 days">
      {values.map((v, i) => (
        <div
          key={i}
          title={`${labels[i] ?? `Day ${i + 1}`}: ${v} change${v === 1 ? "" : "s"}`}
          className="flex-1 rounded-sm bg-sky-500/70 transition-all hover:bg-sky-400 dark:bg-sky-500/60 dark:hover:bg-sky-400"
          style={{ height: `${6 + (v / max) * 54}px`, opacity: v === 0 ? 0.25 : 1 }}
        />
      ))}
    </div>
  );
}
