import { money } from "@/lib/format";

/** A small value-over-time line. The lane beside it states the numbers, so this carries
 *  shape only; the accessible label gives the first and latest values. */
export function Sparkline({
  values,
  color,
  width = 220,
  height = 44,
  baseline,
}: {
  values: number[];
  color: string;
  width?: number;
  height?: number;
  /** Draw a hairline at this value (the starting cash), if it's in range. */
  baseline?: number;
}) {
  if (values.length < 2) {
    return <div style={{ width, height }} className="flex items-center text-xs text-muted">Not enough history yet</div>;
  }
  const lo = Math.min(...values, baseline ?? Infinity);
  const hi = Math.max(...values, baseline ?? -Infinity);
  const span = hi - lo || 1;
  const pad = 3;
  const x = (i: number) => (i / (values.length - 1)) * (width - pad * 2) + pad;
  const y = (v: number) => height - pad - ((v - lo) / span) * (height - pad * 2);
  const path = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
  const last = values[values.length - 1] ?? 0;
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`Portfolio value from ${money(values[0] ?? 0)} to ${money(last)}`}
      className="block max-w-full"
    >
      {baseline !== undefined && baseline >= lo && baseline <= hi ? (
        <line x1={0} x2={width} y1={y(baseline)} y2={y(baseline)} stroke="var(--rule-strong)" strokeWidth={1} />
      ) : null}
      <path d={path} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={x(values.length - 1)} cy={y(last)} r={3} fill={color} stroke="var(--surface)" strokeWidth={2} />
    </svg>
  );
}
