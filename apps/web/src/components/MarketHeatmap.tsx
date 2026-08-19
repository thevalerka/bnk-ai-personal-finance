"use client";

import { useMemo, useState, type KeyboardEvent } from "react";
import Link from "next/link";
import type { MarketGraphNode, MarketGraphSnapshot } from "@/lib/market";
import { fetchMarketGraphPublic } from "@/lib/marketClient";
import styles from "./MarketGraph.module.css";

const GRID_COLS = 100;
const GRID_ROWS = 50;
const TOTAL_CELLS = GRID_COLS * GRID_ROWS;

const TIMEFRAMES: { label: string; tf: string }[] = [
  { label: "5M", tf: "5m" },
  { label: "15M", tf: "15m" },
  { label: "1H", tf: "1h" },
  { label: "4H", tf: "4h" },
  { label: "24H", tf: "1d" },
];

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

function pairKey(a: string, b: string): string {
  return a < b ? `${a}|${b}` : `${b}|${a}`;
}

// Largest-remainder apportionment: block count per node proportional to
// dominance, integers summing to exactly GRID_COLS*GRID_ROWS ("the total
// must be 100*50" — user spec), every node guaranteed at least 1 block.
export function apportionCells(nodes: MarketGraphNode[], totalCells: number): Map<string, number> {
  const weights = nodes.map((n) => ({ id: n.id, value: Math.max(n.dominance_score, 1e-6) }));
  const sum = weights.reduce((acc, w) => acc + w.value, 0);
  const base = weights.map((w) => {
    const raw = (w.value / sum) * totalCells;
    return { id: w.id, floor: Math.max(1, Math.floor(raw)), remainder: raw - Math.floor(raw) };
  });

  const result = new Map(base.map((b) => [b.id, b.floor]));
  let remaining = totalCells - [...result.values()].reduce((a, b) => a + b, 0);

  const byRemainderDesc = [...base].sort((a, b) => b.remainder - a.remainder);
  let i = 0;
  while (remaining > 0 && byRemainderDesc.length > 0) {
    const id = byRemainderDesc[i % byRemainderDesc.length].id;
    result.set(id, (result.get(id) ?? 1) + 1);
    remaining--;
    i++;
  }
  while (remaining < 0) {
    const largest = [...result.entries()].sort((a, b) => b[1] - a[1]).find(([, c]) => c > 1);
    if (!largest) break;
    result.set(largest[0], largest[1] - 1);
    remaining++;
  }
  return result;
}

// Greedy nearest-fragment seriation: builds a 1D ordering where adjacent
// entries are as correlated as possible, so the squarified treemap below
// (which places consecutive input items in the same row/column) puts
// correlated nodes spatially near each other on the grid (user spec:
// "the most correlated elements shall be near").
export function seriate(ids: string[], distance: (a: string, b: string) => number): string[] {
  if (ids.length === 0) return [];
  const remaining = new Set(ids.slice(1));
  const order = [ids[0]];
  while (remaining.size > 0) {
    let bestId: string | null = null;
    let bestEnd: "front" | "back" = "back";
    let bestDist = Infinity;
    for (const id of remaining) {
      const dFront = distance(id, order[0]);
      const dBack = distance(id, order[order.length - 1]);
      if (dFront < bestDist) {
        bestDist = dFront;
        bestId = id;
        bestEnd = "front";
      }
      if (dBack < bestDist) {
        bestDist = dBack;
        bestId = id;
        bestEnd = "back";
      }
    }
    if (!bestId) break;
    remaining.delete(bestId);
    if (bestEnd === "front") order.unshift(bestId);
    else order.push(bestId);
  }
  return order;
}

function worstAspectRatio(row: number[], length: number): number {
  const sum = row.reduce((a, b) => a + b, 0);
  const maxA = Math.max(...row);
  const minA = Math.min(...row);
  if (sum === 0 || minA === 0) return Infinity;
  return Math.max((length * length * maxA) / (sum * sum), (sum * sum) / (length * length * minA));
}

// Classic squarified treemap (Bruls/Huizing/van Wijk 1999) over a fixed
// input order: each recursive row/column is grown greedily while it keeps
// the worst aspect ratio in that row from getting worse, which is what
// keeps blocks close to square/rectangular rather than one long strip
// (user spec: "not 1 line with 20 consecutive blocks").
export function squarify(
  ids: string[],
  areas: number[],
  x: number,
  y: number,
  w: number,
  h: number,
  out: Map<string, Rect>,
): void {
  if (ids.length === 0) return;
  if (ids.length === 1) {
    out.set(ids[0], { x, y, w, h });
    return;
  }

  const shortSide = Math.min(w, h);
  let row = [areas[0]];
  let rowIds = [ids[0]];
  let i = 1;
  while (i < areas.length) {
    const candidateRow = [...row, areas[i]];
    if (worstAspectRatio(candidateRow, shortSide) <= worstAspectRatio(row, shortSide)) {
      row = candidateRow;
      rowIds = [...rowIds, ids[i]];
      i++;
    } else {
      break;
    }
  }

  const rowTotal = row.reduce((a, b) => a + b, 0);
  if (w <= h) {
    const rowHeight = rowTotal / w;
    let cx = x;
    for (let k = 0; k < row.length; k++) {
      const cw = (row[k] / rowTotal) * w;
      out.set(rowIds[k], { x: cx, y, w: cw, h: rowHeight });
      cx += cw;
    }
    squarify(ids.slice(row.length), areas.slice(row.length), x, y + rowHeight, w, h - rowHeight, out);
  } else {
    const colWidth = rowTotal / h;
    let cy = y;
    for (let k = 0; k < row.length; k++) {
      const ch = (row[k] / rowTotal) * h;
      out.set(rowIds[k], { x, y: cy, w: colWidth, h: ch });
      cy += ch;
    }
    squarify(ids.slice(row.length), areas.slice(row.length), x + colWidth, y, w - colWidth, h, out);
  }
}

export function buildLayout(snapshot: MarketGraphSnapshot): Map<string, Rect> {
  if (snapshot.nodes.length === 0) return new Map();
  const cellsById = apportionCells(snapshot.nodes, TOTAL_CELLS);

  const corrMap = new Map<string, number>();
  for (const c of snapshot.correlations ?? []) corrMap.set(pairKey(c.a, c.b), c.corr);
  const distance = (a: string, b: string) =>
    a === b ? 0 : 1 - Math.abs(corrMap.get(pairKey(a, b)) ?? 0);

  // Seriate starting from the most dominant node, so the "main driver"
  // anchors the layout and its neighbors are whatever's most correlated
  // with it, working outward.
  const byDominanceDesc = [...snapshot.nodes].sort((a, b) => b.dominance_score - a.dominance_score);
  const order = seriate(
    byDominanceDesc.map((n) => n.id),
    distance,
  );

  const areas = order.map((id) => cellsById.get(id) ?? 1);
  const out = new Map<string, Rect>();
  squarify(order, areas, 0, 0, GRID_COLS, GRID_ROWS, out);
  return out;
}

// ratio == 1 (as volatile as its own 1-year norm) fills the gauge halfway;
// 0 is empty, 2x-or-more historical vol caps it full (user spec).
export function volatilityFraction(ratio: number | null): number {
  if (ratio === null) return 0;
  return Math.max(0, Math.min(1, ratio * 0.5));
}

export function changeFill(node: MarketGraphNode, maxAbsChange: number): string {
  if (node.asset_class === "news" || node.change_pct === null) {
    return "var(--accent-wash-strong)";
  }
  const intensity = maxAbsChange > 0 ? Math.min(1, Math.abs(node.change_pct) / maxAbsChange) : 0;
  const rgbVar = node.change_pct >= 0 ? "var(--positive-rgb)" : "var(--negative-rgb)";
  return `rgba(${rgbVar}, ${(0.22 + intensity * 0.62).toFixed(2)})`;
}

function formatPct(pct: number | null): string | null {
  if (pct === null) return null;
  return `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`;
}

function edgeKindLabel(kind: string): string {
  switch (kind) {
    case "correlation":
      return "correlated with";
    case "lead_lag":
      return "leads";
    case "markov":
      return "shifts next-state odds of";
    case "news":
      return "mentioned in headlines about";
    default:
      return kind;
  }
}

export function MarketHeatmap({ initialSnapshot }: { initialSnapshot: MarketGraphSnapshot }) {
  const [snapshot, setSnapshot] = useState(initialSnapshot);
  const [tf, setTf] = useState("1d");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const layout = useMemo(() => buildLayout(snapshot), [snapshot]);
  const byId = useMemo(() => new Map(snapshot.nodes.map((n) => [n.id, n])), [snapshot.nodes]);
  const maxAbsChange = Math.max(
    ...snapshot.nodes.map((n) => (n.change_pct === null ? 0 : Math.abs(n.change_pct))),
    0.01,
  );

  const selected = selectedId ? (byId.get(selectedId) ?? null) : null;
  const selectedEdges = selected
    ? (snapshot.edges ?? []).filter((e) => e.source === selected.id).sort((a, b) => b.weight - a.weight)
    : [];

  async function handleTimeframeClick(nextTf: string) {
    if (nextTf === tf || loading) return;
    setLoading(true);
    setError(false);
    const next = await fetchMarketGraphPublic(nextTf);
    setLoading(false);
    if (!next || next.nodes.length === 0) {
      setError(true);
      return;
    }
    setTf(nextTf);
    setSnapshot(next);
  }

  function select(node: MarketGraphNode) {
    setSelectedId((current) => (current === node.id ? null : node.id));
  }

  function onKeyDown(event: KeyboardEvent<SVGGElement>, node: MarketGraphNode) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      select(node);
    }
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.controls}>
        <div className={styles.timeframes} role="group" aria-label="Timeframe">
          {TIMEFRAMES.map((t) => (
            <button
              key={t.tf}
              type="button"
              className={t.tf === tf ? `${styles.tfButton} ${styles.tfButtonActive}` : styles.tfButton}
              onClick={() => void handleTimeframeClick(t.tf)}
              disabled={loading}
              aria-pressed={t.tf === tf}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>
      {error ? (
        <div className={styles.errorNote}>Couldn&apos;t load that timeframe — showing the last available one.</div>
      ) : null}

      <svg
        viewBox={`0 0 ${GRID_COLS} ${GRID_ROWS}`}
        className={styles.gridSvg}
        role="img"
        aria-label="Market drivers heatmap: block size is today's dominance rank, color is the change over the selected timeframe, and the translucent fill height is recent volatility relative to this node's own 1-year norm"
      >
        <defs>
          <linearGradient id="volGaugeGradient" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0%" stopColor="var(--surface-0)" stopOpacity="0.55" />
            <stop offset="100%" stopColor="var(--surface-0)" stopOpacity="0.1" />
          </linearGradient>
        </defs>

        {snapshot.nodes.map((node) => {
          const rect = layout.get(node.id);
          if (!rect) return null;
          const frac = volatilityFraction(node.volatility_ratio);
          const area = rect.w * rect.h;
          const showBoth = Math.min(rect.w, rect.h) >= 1.2 && area >= 6;
          const showSymbolOnly = !showBoth && Math.min(rect.w, rect.h) >= 0.8 && area >= 2;
          const fontSize = Math.max(1.3, Math.min(4.2, Math.min(rect.w, rect.h) * 0.32));
          const cx = rect.x + rect.w / 2;
          const cy = rect.y + rect.h / 2;
          const isDaily = node.data_granularity === "daily_fallback" && tf !== "1d";

          const label = `${node.label}: rank #${node.rank}${
            node.change_pct !== null ? `, ${formatPct(node.change_pct)} this window` : ""
          }${isDaily ? " (daily data, no intraday feed)" : ""}`;

          return (
            <g
              key={node.id}
              tabIndex={0}
              role="button"
              aria-label={label}
              onClick={() => select(node)}
              onKeyDown={(e) => onKeyDown(e, node)}
            >
              <title>{label}</title>
              <rect
                x={rect.x}
                y={rect.y}
                width={rect.w}
                height={rect.h}
                className={styles.cellRect}
                fill={changeFill(node, maxAbsChange)}
              />
              {frac > 0 ? (
                <rect
                  x={rect.x}
                  y={rect.y + rect.h * (1 - frac)}
                  width={rect.w}
                  height={rect.h * frac}
                  fill="url(#volGaugeGradient)"
                  className={styles.volGauge}
                />
              ) : null}
              {showBoth ? (
                <>
                  <text x={cx} y={cy - fontSize * 0.15} fontSize={fontSize} className={styles.cellLabel}>
                    {node.symbol}
                  </text>
                  <text x={cx} y={cy + fontSize * 1.05} fontSize={fontSize * 0.82} className={styles.cellChange}>
                    {formatPct(node.change_pct) ?? "—"}
                  </text>
                </>
              ) : showSymbolOnly ? (
                <text x={cx} y={cy + fontSize * 0.3} fontSize={fontSize} className={styles.cellLabel}>
                  {node.symbol}
                </text>
              ) : null}
              {isDaily && rect.w >= 2 && rect.h >= 2 ? (
                <text x={rect.x + rect.w - 1} y={rect.y + 2.6} textAnchor="end" className={styles.cellBadge}>
                  D
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>

      <div className={styles.legend} aria-hidden="true">
        <div className={styles.legendGroup}>
          <span className={styles.legendItem}>
            <div className={styles.legendGradientBar} />
            change, this timeframe
          </span>
        </div>
        <div className={styles.legendGroup}>
          <span className={styles.legendItem}>
            <span className={styles.legendSwatch} style={{ background: "var(--accent-wash-strong)" }} />
            Breaking News
          </span>
          <span>fill height = recent vol ÷ 1yr historical vol</span>
          <span>D = daily data only</span>
        </div>
        <span className={styles.legendNote}>Block size = dominance · nearby blocks = correlated</span>
      </div>

      {selected ? (
        <div className={styles.popupOverlay} onClick={() => setSelectedId(null)}>
          <div
            className={styles.popup}
            role="dialog"
            aria-label={`${selected.label} details`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className={styles.popupHeader}>
              <span className={styles.popupEyebrow}>
                #{selected.rank} {selected.label}
              </span>
              <button type="button" className={styles.popupClose} onClick={() => setSelectedId(null)} aria-label="Close">
                ×
              </button>
            </div>

            <div className={styles.popupRow}>
              <span className={styles.popupLabel}>Last price</span>
              <span className={styles.popupValue}>
                {selected.last_price !== null
                  ? selected.last_price.toLocaleString("en-US", { maximumFractionDigits: 2 })
                  : "—"}
              </span>
            </div>
            <div className={styles.popupRow}>
              <span className={styles.popupLabel}>Change, this window</span>
              <span
                className={`${styles.popupValue} ${
                  selected.change_pct !== null
                    ? selected.change_pct >= 0
                      ? styles.popupDeltaUp
                      : styles.popupDeltaDown
                    : ""
                }`}
              >
                {formatPct(selected.change_pct) ?? "—"}
              </span>
            </div>
            <div className={styles.popupRow}>
              <span className={styles.popupLabel}>Volatility vs 1yr norm</span>
              <span className={styles.popupValue}>
                {selected.volatility_ratio !== null ? `${selected.volatility_ratio.toFixed(2)}×` : "—"}
              </span>
            </div>
            <div className={styles.popupRow}>
              <span className={styles.popupLabel}>Dominance score</span>
              <span className={styles.popupValue}>{selected.dominance_score.toFixed(2)}</span>
            </div>

            {selected.data_granularity === "daily_fallback" && tf !== "1d" ? (
              <div className={styles.popupNote}>
                No intraday feed for this instrument — showing its real latest daily data at every
                timeframe.
              </div>
            ) : null}

            {selectedEdges.length > 0 ? (
              <div className={styles.popupEdges}>
                <div className={styles.popupEdgesTitle}>What this node is doing</div>
                {selectedEdges.map((edge) => {
                  const target = byId.get(edge.target);
                  return (
                    <div key={`${edge.target}-${edge.kind}`} className={styles.popupEdgeRow}>
                      <span>
                        {edgeKindLabel(edge.kind)} <strong>{target?.label ?? edge.target}</strong>
                      </span>
                      <span className={styles.popupEdgeKind}>{edge.weight.toFixed(2)}</span>
                    </div>
                  );
                })}
              </div>
            ) : null}

            {selected.asset_class === "equity" ? (
              <Link href={`/stock/${selected.symbol}`} className={styles.popupDetailLink}>
                View {selected.symbol} details →
              </Link>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
