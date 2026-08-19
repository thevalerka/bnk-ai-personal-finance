"use client";

import { useMemo, useState, type KeyboardEvent } from "react";
import Link from "next/link";
import type { MarketGraphEdge, MarketGraphNode, MarketGraphSnapshot } from "@/lib/market";
import styles from "./MarketGraph.module.css";

const WIDTH = 720;
const HEIGHT = 460;
const MIN_RADIUS = 9;
const MAX_RADIUS = 24;

// 3 grouped hues, not 7 raw asset classes (docs/DECISIONS.md ADR-0031 /
// globals.css comment above --graph-risk) — a same-hued categorical
// palette past 3 slots fails CVD separation on a scatter/bubble-like chart
// where many same-class dots are visible at once (dataviz skill, "all-pairs"
// case). NEWS_FLOW is a singleton, so it doesn't need a competing hue at
// all — it gets --accent plus a diamond marker (shape, not just color).
function nodeColor(node: MarketGraphNode): string {
  switch (node.asset_class) {
    case "equity":
    case "crypto":
      return "var(--graph-risk)";
    case "rates":
    case "macro":
    case "commodity":
      return "var(--graph-macro)";
    case "fx":
      return "var(--graph-fx)";
    case "news":
      return "var(--accent)";
  }
}

function edgeClass(kind: MarketGraphEdge["kind"]): string {
  switch (kind) {
    case "correlation":
      return styles.edgeCorrelation;
    case "lead_lag":
      return styles.edgeLeadLag;
    case "markov":
      return styles.edgeMarkov;
    case "news":
      return styles.edgeNews;
  }
}

function edgeKindLabel(kind: MarketGraphEdge["kind"]): string {
  switch (kind) {
    case "correlation":
      return "correlated with";
    case "lead_lag":
      return "leads (next-day)";
    case "markov":
      return "shifts next-state odds of";
    case "news":
      return "mentioned in headlines about";
  }
}

function formatPct(pct: number | null): string | null {
  if (pct === null) return null;
  return `${pct > 0 ? "+" : ""}${pct.toFixed(2)}%`;
}

interface LaidOutNode extends MarketGraphNode {
  x: number;
  y: number;
}

// A deterministic, one-shot force simulation (repulsion + spring edges +
// light centering), run synchronously for a fixed number of ticks rather
// than an animated rAF loop — 20 nodes is cheap enough (~n^2 * ticks) that
// this settles well under a millisecond, and a static final layout is
// easier to reason about and test than a continuously-moving one.
function computeLayout(nodes: MarketGraphNode[], edges: MarketGraphEdge[]): Map<string, { x: number; y: number }> {
  const cx = WIDTH / 2;
  const cy = HEIGHT / 2;
  const startRadius = Math.min(WIDTH, HEIGHT) * 0.32;

  const sim = nodes.map((n, i) => {
    const angle = (i / nodes.length) * Math.PI * 2;
    return { id: n.id, x: cx + startRadius * Math.cos(angle), y: cy + startRadius * Math.sin(angle), vx: 0, vy: 0 };
  });
  const byId = new Map(sim.map((s) => [s.id, s]));

  const REPULSION = 2600;
  const SPRING = 0.02;
  const SPRING_LENGTH = 110;
  const CENTER_PULL = 0.012;
  const DAMPING = 0.82;
  const MARGIN = 36;

  for (let iter = 0; iter < 260; iter++) {
    for (let i = 0; i < sim.length; i++) {
      for (let j = i + 1; j < sim.length; j++) {
        const a = sim[i];
        const b = sim[j];
        const dx = a.x - b.x;
        const dy = a.y - b.y;
        const distSq = Math.max(dx * dx + dy * dy, 0.01);
        const dist = Math.sqrt(distSq);
        const force = REPULSION / distSq;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        a.vx += fx;
        a.vy += fy;
        b.vx -= fx;
        b.vy -= fy;
      }
    }
    for (const edge of edges) {
      const a = byId.get(edge.source);
      const b = byId.get(edge.target);
      if (!a || !b) continue;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const dist = Math.max(Math.sqrt(dx * dx + dy * dy), 0.01);
      const diff = (dist - SPRING_LENGTH) * SPRING;
      const fx = (dx / dist) * diff;
      const fy = (dy / dist) * diff;
      a.vx += fx;
      a.vy += fy;
      b.vx -= fx;
      b.vy -= fy;
    }
    for (const s of sim) {
      s.vx += (cx - s.x) * CENTER_PULL;
      s.vy += (cy - s.y) * CENTER_PULL;
      s.vx *= DAMPING;
      s.vy *= DAMPING;
      s.x = Math.max(MARGIN, Math.min(WIDTH - MARGIN, s.x + s.vx));
      s.y = Math.max(MARGIN, Math.min(HEIGHT - MARGIN, s.y + s.vy));
    }
  }

  return new Map(sim.map((s) => [s.id, { x: s.x, y: s.y }]));
}

export function MarketGraphChart({ snapshot }: { snapshot: MarketGraphSnapshot }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const positions = useMemo(() => computeLayout(snapshot.nodes, snapshot.edges), [snapshot]);
  const laidOut: LaidOutNode[] = useMemo(
    () =>
      snapshot.nodes.map((n) => {
        const p = positions.get(n.id) ?? { x: WIDTH / 2, y: HEIGHT / 2 };
        return { ...n, x: p.x, y: p.y };
      }),
    [snapshot.nodes, positions],
  );
  const byId = useMemo(() => new Map(laidOut.map((n) => [n.id, n])), [laidOut]);

  const maxDominance = Math.max(...snapshot.nodes.map((n) => n.dominance_score), 0.0001);
  const radiusFor = (n: MarketGraphNode) => MIN_RADIUS + (n.dominance_score / maxDominance) * (MAX_RADIUS - MIN_RADIUS);

  const selected = selectedId ? (byId.get(selectedId) ?? null) : null;
  const connectedIds = selected
    ? new Set(
        snapshot.edges
          .filter((e) => e.source === selected.id || e.target === selected.id)
          .flatMap((e) => [e.source, e.target]),
      )
    : null;
  const selectedEdges = selected
    ? snapshot.edges.filter((e) => e.source === selected.id).sort((a, b) => b.weight - a.weight)
    : [];

  function select(node: LaidOutNode) {
    setSelectedId((current) => (current === node.id ? null : node.id));
  }

  function onKeyDown(event: KeyboardEvent<SVGGElement>, node: LaidOutNode) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      select(node);
    }
  }

  return (
    <div className={styles.wrap}>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className={styles.svg}
        role="img"
        aria-label="Market drivers graph: nodes sized by today's dominance rank, edges show correlation, lead/lag, Markov, and news relationships"
      >
        {snapshot.edges.map((edge, i) => {
          const a = byId.get(edge.source);
          const b = byId.get(edge.target);
          if (!a || !b) return null;
          const dimmed = selected !== null && edge.source !== selected.id && edge.target !== selected.id;
          return (
            <line
              key={`${edge.source}-${edge.target}-${edge.kind}-${i}`}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              className={`${styles.edge} ${edgeClass(edge.kind)} ${dimmed ? styles.edgeDimmed : ""}`}
              strokeWidth={1 + edge.weight * 2.5}
              opacity={dimmed ? undefined : 0.35 + edge.weight * 0.5}
            />
          );
        })}

        {laidOut.map((node) => {
          const dimmed = connectedIds !== null && !connectedIds.has(node.id) && selected?.id !== node.id;
          const radius = radiusFor(node);
          const label = `${node.label}: rank #${node.rank}${
            node.change_pct !== null ? `, ${formatPct(node.change_pct)} today` : ""
          }`;
          return (
            <g
              key={node.id}
              tabIndex={0}
              role="button"
              aria-label={label}
              onClick={() => select(node)}
              onKeyDown={(e) => onKeyDown(e, node)}
              className={dimmed ? styles.nodeDimmed : undefined}
            >
              <title>{label}</title>
              {node.asset_class === "news" ? (
                <rect
                  x={node.x - radius * 0.75}
                  y={node.y - radius * 0.75}
                  width={radius * 1.5}
                  height={radius * 1.5}
                  transform={`rotate(45 ${node.x} ${node.y})`}
                  className={styles.node}
                  fill={nodeColor(node)}
                />
              ) : (
                <circle cx={node.x} cy={node.y} r={radius} className={styles.node} fill={nodeColor(node)} />
              )}
              <text x={node.x} y={node.y + radius + 11} textAnchor="middle" className={styles.nodeLabel}>
                {node.symbol}
              </text>
            </g>
          );
        })}
      </svg>

      <div className={styles.legend} aria-hidden="true">
        <div className={styles.legendGroup}>
          <span className={styles.legendItem}>
            <span className={styles.legendSwatch} style={{ background: "var(--graph-risk)" }} />
            Equities &amp; crypto
          </span>
          <span className={styles.legendItem}>
            <span className={styles.legendSwatch} style={{ background: "var(--graph-macro)" }} />
            Rates, macro &amp; commodities
          </span>
          <span className={styles.legendItem}>
            <span className={styles.legendSwatch} style={{ background: "var(--graph-fx)" }} />
            FX
          </span>
          <span className={styles.legendItem}>
            <span className={styles.legendSwatchDiamond} style={{ background: "var(--accent)" }} />
            News
          </span>
        </div>
        <div className={styles.legendGroup}>
          <span className={styles.legendItem}>
            <span className={styles.legendLine} style={{ borderColor: "var(--accent)" }} />
            Leads
          </span>
          <span className={styles.legendItem}>
            <span className={styles.legendLine} style={{ borderColor: "var(--series-2)" }} />
            Markov
          </span>
          <span className={styles.legendItem}>
            <span className={styles.legendLine} style={{ borderColor: "var(--text-muted)", borderStyle: "dashed" }} />
            Correlated
          </span>
        </div>
        <span className={styles.legendNote}>Size = today&apos;s dominance rank</span>
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
                {selected.last_price !== null ? selected.last_price.toLocaleString("en-US", { maximumFractionDigits: 2 }) : "—"}
              </span>
            </div>
            <div className={styles.popupRow}>
              <span className={styles.popupLabel}>Today</span>
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
              <span className={styles.popupLabel}>Dominance score</span>
              <span className={styles.popupValue}>{selected.dominance_score.toFixed(2)}</span>
            </div>

            {selectedEdges.length > 0 ? (
              <div className={styles.popupEdges}>
                <div className={styles.popupEdgesTitle}>What this node is doing today</div>
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
