import { fetchQuote } from "@/lib/market";
import styles from "./YieldCurve.module.css";

const TENORS: Array<{ series: string; label: string }> = [
  { series: "DGS1MO", label: "1M" },
  { series: "DGS3MO", label: "3M" },
  { series: "DGS6MO", label: "6M" },
  { series: "DGS1", label: "1Y" },
  { series: "DGS2", label: "2Y" },
  { series: "DGS3", label: "3Y" },
  { series: "DGS5", label: "5Y" },
  { series: "DGS7", label: "7Y" },
  { series: "DGS10", label: "10Y" },
  { series: "DGS20", label: "20Y" },
  { series: "DGS30", label: "30Y" },
];

const WIDTH = 560;
const HEIGHT = 160;
const PAD_X = 24;
const PAD_Y = 20;

export async function YieldCurve() {
  const quotes = await fetchQuote(
    "macro_series",
    TENORS.map((t) => t.series),
  );

  const bySeries = new Map((quotes ?? []).map((q) => [q.symbol, q.price]));
  const points = TENORS.map((t) => ({ label: t.label, value: bySeries.get(t.series) }))
    .filter((p): p is { label: string; value: number } => p.value !== undefined);

  if (points.length < 2) {
    return <p style={{ color: "var(--text-muted)", fontSize: 13 }}>Yield curve unavailable — FRED not reachable.</p>;
  }

  const values = points.map((p) => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const stepX = (WIDTH - PAD_X * 2) / (points.length - 1);

  const coords = points.map((p, i) => {
    const x = PAD_X + i * stepX;
    const y = PAD_Y + (HEIGHT - PAD_Y * 2) * (1 - (p.value - min) / range);
    return { ...p, x, y };
  });

  const path = coords.map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ");
  const gridTicks = [0, 0.5, 1];
  const last = coords[coords.length - 1];

  return (
    <svg width="100%" viewBox={`0 0 ${WIDTH} ${HEIGHT + 20}`} role="img" aria-label="US Treasury yield curve">
      {gridTicks.map((t) => {
        const y = PAD_Y + (HEIGHT - PAD_Y * 2) * (1 - t);
        return <line key={t} x1={PAD_X} x2={WIDTH - PAD_X} y1={y} y2={y} className={styles.gridline} />;
      })}
      <path d={path} fill="none" className={styles.line} />
      {coords.map((c) => (
        <circle key={c.label} cx={c.x} cy={c.y} r={3} className={styles.dot}>
          <title>
            {c.label}: {c.value.toFixed(2)}%
          </title>
        </circle>
      ))}
      <text x={last.x} y={last.y - 10} textAnchor="end" className={styles.endLabel}>
        {last.value.toFixed(2)}%
      </text>
      {coords.map((c) => (
        <text key={c.label} x={c.x} y={HEIGHT + 14} textAnchor="middle" className={styles.axisLabel}>
          {c.label}
        </text>
      ))}
    </svg>
  );
}
