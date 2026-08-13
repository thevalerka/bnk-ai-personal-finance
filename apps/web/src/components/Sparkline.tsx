import type { Candle } from "@/lib/market";

// Minimal trend line: no axis, no gridlines (recessive-by-omission — a
// sparkline's job is shape, not precision). 2px line, rounded caps/joins,
// filled end-dot in the accent, per the dataviz skill's mark spec.
export function Sparkline({
  candles,
  width = 96,
  height = 28,
  color = "var(--accent)",
}: {
  candles: Candle[];
  width?: number;
  height?: number;
  color?: string;
}) {
  if (candles.length < 2) return null;

  const closes = candles.map((c) => c.close);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;
  const stepX = width / (closes.length - 1);
  const pad = 3;

  const points = closes.map((value, i) => {
    const x = i * stepX;
    const y = pad + (height - pad * 2) * (1 - (value - min) / range);
    return [x, y] as const;
  });

  const path = points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const [lastX, lastY] = points[points.length - 1];

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="price trend">
      <path d={path} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={lastX} cy={lastY} r={2.5} fill={color} stroke="var(--surface-1)" strokeWidth={2} />
    </svg>
  );
}
