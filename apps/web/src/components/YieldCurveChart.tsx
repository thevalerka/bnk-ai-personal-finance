"use client";

import { useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { useExplainPanel } from "./ExplainPanel";
import { queueEvent } from "@/lib/eventQueue";
import styles from "./YieldCurve.module.css";

const WIDTH = 560;
const HEIGHT = 160;
const PAD_X = 24;
const PAD_Y = 24;

// Mirrors apps/api/config/taxonomy.yaml's fixed_income.rates_ust nodes —
// no shared-types codegen yet (docs/STATE.md), same hand-maintained-parallel
// convention as the other components' symbol lists.
const SEGMENT_FOR_LABEL: Record<string, string> = {
  "1M": "fixed_income.rates_ust.short_end",
  "3M": "fixed_income.rates_ust.short_end",
  "6M": "fixed_income.rates_ust.short_end",
  "1Y": "fixed_income.rates_ust.short_end",
  "2Y": "fixed_income.rates_ust.belly",
  "3Y": "fixed_income.rates_ust.belly",
  "5Y": "fixed_income.rates_ust.belly",
  "7Y": "fixed_income.rates_ust.belly",
  "10Y": "fixed_income.rates_ust.long_end",
  "20Y": "fixed_income.rates_ust.long_end",
  "30Y": "fixed_income.rates_ust.long_end",
};

const CHART_INTERACTION_THROTTLE_MS = 3000;

interface TenorPoint {
  label: string;
  value: number;
}

interface Coord extends TenorPoint {
  x: number;
  y: number;
}

// Client component: the hover crosshair needs pointer events, so this is the
// one interactive piece — the server component above still does the fetch
// and hands off plain points. Per dataviz skill interaction.md: crosshair
// snaps to the nearest X, tooltip carries the value, everything shown on
// hover is also visible statically (axis labels + the end-label already
// name every value without hovering).
export function YieldCurveChart({ points }: { points: TenorPoint[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const lastTracked = useRef<{ segment: string; at: number } | null>(null);
  const { open: openExplain } = useExplainPanel();

  const { coords, path, areaPath, min, max } = useMemo(() => {
    const values = points.map((p) => p.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const stepX = (WIDTH - PAD_X * 2) / (points.length - 1);

    const coords: Coord[] = points.map((p, i) => {
      const x = PAD_X + i * stepX;
      const y = PAD_Y + (HEIGHT - PAD_Y * 2) * (1 - (p.value - min) / range);
      return { ...p, x, y };
    });

    const path = coords.map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ");
    const areaPath = `${path} L${coords[coords.length - 1].x.toFixed(1)},${HEIGHT - PAD_Y} L${coords[0].x.toFixed(1)},${HEIGHT - PAD_Y} Z`;

    return { coords, path, areaPath, min, max };
  }, [points]);

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

    const segment = SEGMENT_FOR_LABEL[coords[nearest].label];
    const now = Date.now();
    const last = lastTracked.current;
    if (segment && (!last || last.segment !== segment || now - last.at > CHART_INTERACTION_THROTTLE_MS)) {
      lastTracked.current = { segment, at: now };
      queueEvent({ node_id: segment, kind: "chart_interaction" });
    }
  }

  const gridTicks = [0, 0.5, 1];
  const last = coords[coords.length - 1];
  const active = hover !== null ? coords[hover] : null;

  // Tooltip box, clamped so it never overflows the viewBox.
  const tooltipWidth = 72;
  const tooltipX = active ? Math.min(Math.max(active.x - tooltipWidth / 2, 2), WIDTH - tooltipWidth - 2) : 0;

  return (
    <div className={styles.wrap}>
      <svg
        width="100%"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`US Treasury yield curve, ranging from ${min.toFixed(2)}% to ${max.toFixed(2)}%`}
        onPointerMove={handlePointerMove}
        onPointerLeave={() => setHover(null)}
        className={styles.svg}
      >
        <defs>
          <linearGradient id="yieldArea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.16" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {gridTicks.map((t) => {
          const y = PAD_Y + (HEIGHT - PAD_Y * 2) * (1 - t);
          return <line key={t} x1={PAD_X} x2={WIDTH - PAD_X} y1={y} y2={y} className={styles.gridline} />;
        })}

        <path d={areaPath} fill="url(#yieldArea)" stroke="none" />
        <path d={path} fill="none" className={styles.line} />

        {active ? (
          <line x1={active.x} x2={active.x} y1={PAD_Y} y2={HEIGHT - PAD_Y} className={styles.crosshair} />
        ) : null}

        {coords.map((c, i) => (
          <circle
            key={c.label}
            cx={c.x}
            cy={c.y}
            r={hover === i ? 5 : 3}
            className={styles.dot}
          />
        ))}

        <text x={last.x} y={last.y - 12} textAnchor="end" className={styles.endLabel}>
          {last.value.toFixed(2)}%
        </text>

        <g className={styles.axisLabels}>
          {coords.map((c, i) => (
            <text
              key={c.label}
              x={c.x}
              y={HEIGHT - 4}
              textAnchor="middle"
              className={hover === i ? styles.axisLabelActive : styles.axisLabel}
            >
              {c.label}
            </text>
          ))}
        </g>

        {active ? (
          <g transform={`translate(${tooltipX}, ${Math.max(active.y - 38, 4)})`} className={styles.tooltip}>
            <rect width={tooltipWidth} height={26} rx={6} className={styles.tooltipBg} />
            <text x={tooltipWidth / 2} y={11} textAnchor="middle" className={styles.tooltipLabel}>
              {active.label}
            </text>
            <text x={tooltipWidth / 2} y={22} textAnchor="middle" className={styles.tooltipValue}>
              {active.value.toFixed(2)}%
            </text>
          </g>
        ) : null}

        {/* Wide invisible hit targets — the visible 3px dots stay thin, but
            hover/focus responds well before the pointer is dead-center. */}
        {coords.map((c, i) => {
          const segment = SEGMENT_FOR_LABEL[c.label];
          return (
            <rect
              key={`hit-${c.label}`}
              x={c.x - (WIDTH / coords.length) / 2}
              y={0}
              width={WIDTH / coords.length}
              height={HEIGHT}
              fill="transparent"
              tabIndex={0}
              role="graphics-symbol"
              aria-label={`${c.label}: ${c.value.toFixed(2)}%`}
              style={segment ? { cursor: "pointer" } : undefined}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
              onClick={() => {
                if (!segment) return;
                queueEvent({ node_id: segment, kind: "click" });
                openExplain(segment);
              }}
            />
          );
        })}
      </svg>
    </div>
  );
}
