"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { fetchExplain, type ExplainResult } from "@/lib/attention";
import styles from "./ExplainPanel.module.css";

interface ExplainPanelContextValue {
  open: (nodeId: string) => void;
}

const ExplainPanelContext = createContext<ExplainPanelContextValue | null>(null);

/** "Why am I seeing this" — docs/PLAN.md section 1: click any block, see
 * the interest weights/decay/source events that put it there. A Context
 * rather than prop-drilling: the trigger lives arbitrarily deep in the
 * tree (a heatmap cell, a yield-curve tenor point), several of them inside
 * Server Components that can't hold client callback state themselves. */
export function useExplainPanel(): ExplainPanelContextValue {
  const ctx = useContext(ExplainPanelContext);
  if (!ctx) throw new Error("useExplainPanel must be used within ExplainPanelProvider");
  return ctx;
}

function formatNodeId(nodeId: string): string {
  return nodeId
    .split(".")
    .map((part) => part.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()))
    .join(" › ");
}

function formatWhen(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const diffHours = diffMs / (1000 * 60 * 60);
  if (diffHours < 1) return `${Math.max(1, Math.round(diffMs / 60_000))}m ago`;
  if (diffHours < 48) return `${Math.round(diffHours)}h ago`;
  return `${Math.round(diffHours / 24)}d ago`;
}

const KIND_LABELS: Record<string, string> = {
  impression: "Viewed",
  dwell: "Kept viewing",
  hover: "Hovered",
  click: "Clicked into",
  chart_interaction: "Interacted with chart",
  search: "Searched",
  agent_mention: "Asked the agent about",
  pin: "Pinned",
  mute: "Muted",
};

export function ExplainPanelProvider({ children }: { children: ReactNode }) {
  const [nodeId, setNodeId] = useState<string | null>(null);
  const [result, setResult] = useState<ExplainResult | null>(null);
  const [loading, setLoading] = useState(false);

  const open = useCallback((id: string) => setNodeId(id), []);
  const close = useCallback(() => setNodeId(null), []);

  useEffect(() => {
    if (!nodeId) {
      setResult(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    void fetchExplain(nodeId).then((r) => {
      if (!cancelled) {
        setResult(r);
        setLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [nodeId]);

  return (
    <ExplainPanelContext.Provider value={{ open }}>
      {children}
      {nodeId ? (
        <div className={styles.overlay} onClick={close}>
          <div className={styles.panel} onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Why am I seeing this">
            <div className={styles.header}>
              <span className={styles.eyebrow}>Why am I seeing this</span>
              <button className={styles.close} onClick={close} aria-label="Close">
                ×
              </button>
            </div>
            <h2 className={styles.title}>{formatNodeId(nodeId)}</h2>

            {loading ? (
              <p className={styles.muted}>Loading…</p>
            ) : result ? (
              <>
                <div className={styles.scoreRow}>
                  <span className={styles.scoreLabel}>Interest score</span>
                  <span className={`${styles.scoreValue} tabular-nums`}>{result.score.toFixed(2)}</span>
                </div>
                {result.muted ? <p className={styles.mutedBadge}>Muted</p> : null}
                <p className={styles.explainer}>
                  Score decays with a 7-day half-life from every interaction below —
                  older engagement counts for less, and a leaf node&apos;s score also
                  feeds its parent bucket and asset class at reduced weight.
                </p>

                <h3 className={styles.sectionTitle}>Source events</h3>
                {result.source_events.length === 0 ? (
                  <p className={styles.muted}>No recorded interactions yet.</p>
                ) : (
                  <ul className={styles.eventList}>
                    {result.source_events.map((event, i) => (
                      <li key={i} className={styles.event}>
                        <span className={styles.eventKind}>
                          {KIND_LABELS[event.kind] ?? event.kind}
                        </span>
                        <span className={styles.eventNode}>{formatNodeId(event.node_id)}</span>
                        <span
                          className={`${styles.eventWeight} ${event.weight < 0 ? styles.eventWeightNegative : ""} tabular-nums`}
                        >
                          {event.weight > 0 ? "+" : ""}
                          {event.weight.toFixed(1)}
                        </span>
                        <span className={styles.eventTime}>{formatWhen(event.ts)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            ) : (
              <p className={styles.muted}>Unavailable right now.</p>
            )}
          </div>
        </div>
      ) : null}
    </ExplainPanelContext.Provider>
  );
}
