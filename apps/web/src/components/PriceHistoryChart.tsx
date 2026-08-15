"use client";

import { useMemo, useState, type PointerEvent as ReactPointerEvent } from "react";
import type { Candle } from "@/lib/market";
import styles from "./PriceHistoryChart.module.css";

const WIDTH = 680;
const HEIGHT = 220;
const PAD_X = 8;
const PAD_Y = 20;
const AXIS_LABEL_COUNT = 6;

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// Hand-rolled SVG, same discipline as YieldCurveChart/Sparkline — no
// charting library. Closing price only (this is a "how has it moved"
// history view, not an OHLC/volume trading chart).
export function PriceHistoryChart({ candles }: { candles: Candle[] }) {
  const [hover, setHover] = useState<number | null>(null);

  const { coords, path, areaPath, min, max, trend } = useMemo(() => {
    const closes = candles.map((c) => c.close);
    const min = Math.min(...closes);
    const max = Math.max(...closes);
    const range = max - min || 1;
    const stepX = (WIDTH - PAD_X * 2) / (candles.length - 1);

    const coords = candles.map((c, i) => ({
      x: PAD_X + i * stepX,
      y: PAD_Y + (HEIGHT - PAD_Y * 2) * (1 - (c.close - min) / range),
      ts: c.ts,
      close: c.close,
    }));

    const path = coords.map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ");
    const areaPath = `${path} L${coords[coords.length - 1].x.toFixed(1)},${HEIGHT - PAD_Y} L${coords[0].x.toFixed(1)},${HEIGHT - PAD_Y} Z`;

    const trend: "up" | "down" | "flat" =
      closes[closes.length - 1] > closes[0] ? "up" : closes[closes.length - 1] < closes[0] ? "down" : "flat";

    return { coords, path, areaPath, min, max, trend };
  }, [candles]);

  const color = trend === "up" ? "var(--positive)" : trend === "down" ? "var(--negative)" : "var(--accent)";

  function handlePointerMove(event: ReactPointerEvent<SVGSVGElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    const scaleX = WIDTH / rect.width;
    const xInSvg = (event.clientX - rect.left) * scaleX;
    let nearest = 0;
    let nearestDist = Infinity;
    coords.forEach((c, i) => {
      const dist = Math.abs(c.x - xInSvg);
      if (dist < nearestDist) {
        nearestDist = dist;
        nearest = i;
      }
    });
    setHover(nearest);
  }

  const active = hover !== null ? coords[hover] : null;
  const tooltipWidth = 78;
  const tooltipX = active ? Math.min(Math.max(active.x - tooltipWidth / 2, 2), WIDTH - tooltipWidth - 2) : 0;

  // Thin the x-axis to a handful of evenly spaced dates rather than one per
  // candle — same over-plotting fix YieldCurveChart's mobile breakpoint and
  // WorldMap's label-area cutoff both apply, just computed instead of a
  // media query since candle count varies with the requested window.
  const axisStep = Math.max(1, Math.floor(coords.length / AXIS_LABEL_COUNT));

  return (
    <div className={styles.wrap}>
      <svg
        width="100%"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`Price history, ${formatDate(candles[0].ts)} to ${formatDate(candles[candles.length - 1].ts)}, ranging from ${min.toFixed(2)} to ${max.toFixed(2)}`}
        onPointerMove={handlePointerMove}
        onPointerLeave={() => setHover(null)}
        className={styles.svg}
      >
        <defs>
          <linearGradient id="priceHistoryArea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.18" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>

        {[0, 0.5, 1].map((t) => {
          const y = PAD_Y + (HEIGHT - PAD_Y * 2) * (1 - t);
          return <line key={t} x1={PAD_X} x2={WIDTH - PAD_X} y1={y} y2={y} className={styles.gridline} />;
        })}

        <path d={areaPath} className={styles.area} fill="url(#priceHistoryArea)" />
        <path d={path} className={styles.line} stroke={color} />

        {active ? (
          <line x1={active.x} x2={active.x} y1={PAD_Y} y2={HEIGHT - PAD_Y} className={styles.crosshair} />
        ) : null}

        <circle
          cx={coords[coords.length - 1].x}
          cy={coords[coords.length - 1].y}
          r={hover === null || hover === coords.length - 1 ? 4 : 0}
          className={styles.dot}
          fill={color}
        />
        {active ? <circle cx={active.x} cy={active.y} r={4} className={styles.dot} fill={color} /> : null}

        {/* Left-aligned, sitting right on their gridline — the right edge
            is already claimed by the last-point dot, and anchoring these at
            the bottom would collide with the x-axis date row underneath. */}
        <text x={PAD_X} y={PAD_Y - 6} textAnchor="start" className={styles.priceLabel}>
          {max.toFixed(2)}
        </text>
        <text x={PAD_X} y={HEIGHT - PAD_Y - 6} textAnchor="start" className={styles.priceLabel}>
          {min.toFixed(2)}
        </text>

        {coords.map((c, i) =>
          i % axisStep === 0 || i === coords.length - 1 ? (
            <text key={c.ts} x={c.x} y={HEIGHT - 2} textAnchor="middle" className={styles.axisLabel}>
              {formatDate(c.ts)}
            </text>
          ) : null,
        )}

        {active ? (
          <g transform={`translate(${tooltipX}, ${Math.max(active.y - 40, 4)})`} className={styles.tooltip}>
            <rect width={tooltipWidth} height={28} rx={6} className={styles.tooltipBg} />
            <text x={tooltipWidth / 2} y={12} textAnchor="middle" className={styles.tooltipDate}>
              {formatDate(active.ts)}
            </text>
            <text x={tooltipWidth / 2} y={23} textAnchor="middle" className={styles.tooltipValue}>
              {active.close.toFixed(2)}
            </text>
          </g>
        ) : null}

        {/* Transparent SVG regions don't receive pointer events by default
            (only painted ones do) — this hit rect is what makes hovering
            over empty chart space, not just the line itself, work. */}
        <rect x={0} y={0} width={WIDTH} height={HEIGHT} fill="transparent" />
      </svg>
    </div>
  );
}
