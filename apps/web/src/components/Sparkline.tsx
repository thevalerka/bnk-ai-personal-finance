import type { Candle } from "@/lib/market";

// Trend line + a soft area wash: 2px line, rounded caps/joins, filled end-dot,
// ~10% opacity area fill under the line (dataviz skill mark spec). No axis,
// no gridlines — recessive-by-omission, a sparkline's job is shape, not
// precision. Color follows trend direction (up/down/flat) so it echoes the
// delta pill beside it rather than sitting neutral.
export function Sparkline({
  candles,
  width = 96,
  height = 28,
  trend = "flat",
}: {
  candles: Candle[];
  width?: number;
  height?: number;
  trend?: "up" | "down" | "flat";
}) {
  if (candles.length < 2) return null;

  const color = trend === "up" ? "var(--positive)" : trend === "down" ? "var(--negative)" : "var(--text-muted)";
  const gradientId = `sparkline-fill-${trend}`;

  const closes = candles.map((c) => c.close);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;
  const stepX = width / (closes.length - 1);
  const pad = 4;

  const points = closes.map((value, i) => {
    const x = i * stepX;
    const y = pad + (height - pad * 2) * (1 - (value - min) / range);
    return [x, y] as const;
  });

  const path = points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const [firstX] = points[0];
  const [lastX, lastY] = points[points.length - 1];
  const areaPath = `${path} L${lastX.toFixed(1)},${height} L${firstX.toFixed(1)},${height} Z`;

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`price trend, ${trend}`}>
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.22" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gradientId})`} stroke="none" />
      <path d={path} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={lastX} cy={lastY} r={3} fill={color} stroke="var(--surface-1)" strokeWidth={2} />
    </svg>
  );
}
