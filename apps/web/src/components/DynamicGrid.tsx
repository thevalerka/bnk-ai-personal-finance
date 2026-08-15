"use client";

import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
  type RefObject,
} from "react";
import { useExplainPanel } from "./ExplainPanel";
import { usePanelState } from "./PanelPrefs";
import { PanelIconChip } from "./PanelControls";
import { useAttentionTracking } from "@/hooks/useAttentionTracking";
import { fetchLayout, type LayoutPlan } from "@/lib/attention";
import styles from "@/app/page.module.css";

type BlockType = "quotes" | "yield_curve" | "heatmap";

// Each block maps to several taxonomy leaf nodes (app/attention/layout.py's
// BLOCK_NODES) — block-level tracking (as opposed to YieldCurveChart's own
// per-tenor-segment tracking) picks one representative node rather than
// splitting a single impression/hover/click across all of them. Heatmap's
// 11 sector nodes don't have one obvious "most representative" pick the way
// quotes/yield_curve do; per-cell tracking is a natural next step (each
// sector already has its own leaf node) but isn't wired yet.
const REPRESENTATIVE_NODE: Record<BlockType, string> = {
  quotes: "equities.us_large_cap.broad_market",
  yield_curve: "fixed_income.rates_ust.belly",
  heatmap: "equities.us_large_cap.technology",
};

// What renders before the first /profile/layout response lands, and the
// fallback if a visitor's layout call ever fails — an even 3-way split,
// matching what compute_layout() itself returns for a fresh profile with
// no interest signal yet (app/attention/layout.py).
const DEFAULT_COLUMNS: Record<BlockType, number> = { quotes: 4, yield_curve: 4, heatmap: 4 };

// docs/PLAN.md section 4.4: "visibly and sensibly reshapes the page" over
// the course of a browsing session, not on every keystroke — a poll this
// infrequent is plenty to demo without hammering the API.
const POLL_INTERVAL_MS = 30_000;

// Matches page.module.css's @media (max-width: 1023px) breakpoint, below
// which the CSS module takes over column spans directly (full-width
// stacked blocks) — the layout solver's spans are computed against a
// 12-column row and don't translate proportionally onto a narrower grid,
// so this component simply stays out of the way below that width rather
// than fighting the stylesheet with a competing inline style.
function useIsDesktop(): boolean {
  const [isDesktop, setIsDesktop] = useState(true);
  useEffect(() => {
    const mql = window.matchMedia("(min-width: 1024px)");
    setIsDesktop(mql.matches);
    const onChange = () => setIsDesktop(mql.matches);
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, []);
  return isDesktop;
}

/** FLIP (First-Last-Invert-Play): capture an element's rect before a
 * layout-changing render, then on the next commit invert the visual delta
 * and transition it away — turns an instant CSS Grid column-span jump into
 * a smooth ~400ms reflow (docs/PLAN.md section 4.4). */
function useFlip(ref: RefObject<HTMLDivElement | null>, dep: unknown): void {
  const prevRect = useRef<DOMRect | null>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (el && prevRect.current) {
      const first = prevRect.current;
      const last = el.getBoundingClientRect();
      const dx = first.left - last.left;
      const scaleX = first.width / last.width;
      if (dx !== 0 || scaleX !== 1) {
        el.style.transition = "none";
        el.style.transformOrigin = "left center";
        el.style.transform = `translateX(${dx}px) scaleX(${scaleX})`;
        // Force a reflow so the inverted transform actually paints before
        // it's cleared below — otherwise the browser would coalesce both
        // style writes into one frame and there'd be nothing to animate.
        el.getBoundingClientRect();
        el.style.transition = "transform 400ms cubic-bezier(0.4, 0, 0.2, 1)";
        el.style.transform = "";
      }
    }
    prevRect.current = el ? el.getBoundingClientRect() : null;
  }, [ref, dep]);
}

export function DynamicGrid({
  quotes,
  yieldCurve,
  heatmap,
}: {
  quotes: ReactNode;
  yieldCurve: ReactNode;
  heatmap: ReactNode;
}) {
  const [layout, setLayout] = useState<LayoutPlan | null>(null);
  const quotesRef = useRef<HTMLDivElement>(null);
  const yieldCurveRef = useRef<HTMLDivElement>(null);
  const heatmapRef = useRef<HTMLDivElement>(null);
  const { open: openExplain } = useExplainPanel();
  const isDesktop = useIsDesktop();

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      const next = await fetchLayout();
      if (!cancelled && next) setLayout(next);
    }
    void poll();
    const interval = setInterval(poll, POLL_INTERVAL_MS);
    // PromptBar dispatches this the moment an add_block/set_focus tool call
    // mutates the profile (docs/PLAN.md section 5.1's "the page rebuilds
    // itself" demo moment) — an immediate refetch instead of waiting out
    // the normal 30s interval above.
    const onMutation = () => void poll();
    window.addEventListener("amt:layout-refresh", onMutation);
    return () => {
      cancelled = true;
      clearInterval(interval);
      window.removeEventListener("amt:layout-refresh", onMutation);
    };
  }, []);

  useFlip(quotesRef, layout);
  useFlip(yieldCurveRef, layout);
  useFlip(heatmapRef, layout);

  const quotesTracking = useAttentionTracking(quotesRef, REPRESENTATIVE_NODE.quotes);
  // Yield Curve gets its own finer-grained per-segment tracking inside
  // YieldCurveChart (hover -> chart_interaction, click -> explain) — only
  // wire impression tracking here, not onClick, so a click on the chart
  // doesn't also fire a second, less-specific block-level click event.
  const yieldCurveTracking = useAttentionTracking(yieldCurveRef, REPRESENTATIVE_NODE.yield_curve);
  const heatmapTracking = useAttentionTracking(heatmapRef, REPRESENTATIVE_NODE.heatmap);

  // Same expand/icon/delete choice Block.tsx's header controls write for
  // every other panel (PanelPrefs.tsx) — these 3 ids match BlockType
  // exactly since they're the same 3 blocks the attention engine reshapes.
  // A user's manual "expand"/"icon" overrides the attention-driven span
  // below; "deleted" skips the div (and its ref/tracking) entirely, the
  // same no-empty-gap behavior PanelSlot.tsx gives the other 4 panels.
  const quotesPanel = usePanelState("quotes");
  const yieldCurvePanel = usePanelState("yield_curve");
  const heatmapPanel = usePanelState("heatmap");

  const spanStyle = (type: BlockType, panelState: string): CSSProperties | undefined => {
    if (panelState === "expanded") return { gridColumn: "1 / -1" };
    return isDesktop
      ? { gridColumn: `span ${layout?.blocks.find((b) => b.block_type === type)?.columns ?? DEFAULT_COLUMNS[type]}` }
      : undefined;
  };

  return (
    <>
      {quotesPanel.state === "deleted" ? null : quotesPanel.state === "icon" ? (
        <div style={{ gridColumn: "span 2" }}>
          <PanelIconChip id="quotes" title="Quotes" />
        </div>
      ) : (
        <div
          ref={quotesRef}
          className={styles.quoteGrid}
          style={spanStyle("quotes", quotesPanel.state)}
          onMouseEnter={quotesTracking.onMouseEnter}
          onClick={() => {
            quotesTracking.onClick();
            openExplain(REPRESENTATIVE_NODE.quotes);
          }}
        >
          {quotes}
        </div>
      )}
      {yieldCurvePanel.state === "deleted" ? null : yieldCurvePanel.state === "icon" ? (
        <div style={{ gridColumn: "span 2" }}>
          <PanelIconChip id="yield_curve" title="US Treasury Yield Curve" />
        </div>
      ) : (
        <div
          ref={yieldCurveRef}
          className={styles.yieldCurve}
          style={spanStyle("yield_curve", yieldCurvePanel.state)}
          onMouseEnter={yieldCurveTracking.onMouseEnter}
        >
          {yieldCurve}
        </div>
      )}
      {heatmapPanel.state === "deleted" ? null : heatmapPanel.state === "icon" ? (
        <div style={{ gridColumn: "span 2" }}>
          <PanelIconChip id="heatmap" title="Sector Heatmap" />
        </div>
      ) : (
        <div
          ref={heatmapRef}
          className={styles.heatmap}
          style={spanStyle("heatmap", heatmapPanel.state)}
          onMouseEnter={heatmapTracking.onMouseEnter}
          onClick={() => {
            heatmapTracking.onClick();
            openExplain(REPRESENTATIVE_NODE.heatmap);
          }}
        >
          {heatmap}
        </div>
      )}
    </>
  );
}
