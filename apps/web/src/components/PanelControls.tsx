"use client";

import type { MouseEvent } from "react";
import { usePanelState } from "./PanelPrefs";
import styles from "./PanelControls.module.css";

// Several blocks (DynamicGrid.tsx's Quotes/Heatmap) have their own onClick
// on the surrounding card, wired to open the attention engine's explain
// panel — without stopPropagation, clicking a control here bubbles up and
// fires that too (confirmed live: expanding Sector Heatmap also popped
// open "why am I seeing this"). Every button below stops it.
function stop(handler: () => void) {
  return (event: MouseEvent) => {
    event.stopPropagation();
    handler();
  };
}

/** The three per-panel controls (Block.tsx's header): expand to full width,
 * minimize to a small icon chip, or delete outright — every choice
 * persists via PanelPrefsProvider (localStorage), same as ThemeToggle. */
export function PanelControls({ id }: { id: string }) {
  const { state, setState } = usePanelState(id);
  const expanded = state === "expanded";

  return (
    <div className={styles.controls}>
      <button
        type="button"
        className={styles.button}
        onClick={stop(() => setState(expanded ? "normal" : "expanded"))}
        aria-label={expanded ? "Restore panel size" : "Expand panel to full width"}
        title={expanded ? "Restore panel size" : "Expand to full width"}
      >
        {expanded ? (
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M9 15v5H4M15 9V4h5M9 15l-6 6M15 9l6-6"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        ) : (
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M15 4h5v5M4 9V4h5M9 20H4v-5M20 15v5h-5M20 4l-6 6M4 20l6-6"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        )}
      </button>
      <button
        type="button"
        className={styles.button}
        onClick={stop(() => setState("icon"))}
        aria-label="Minimize to icon"
        title="Minimize to icon"
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M5 12h14" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </button>
      <button
        type="button"
        className={`${styles.button} ${styles.buttonDanger}`}
        onClick={stop(() => setState("deleted"))}
        aria-label="Delete panel"
        title="Delete panel"
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M6 6l12 12M18 6L6 18"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      </button>
    </div>
  );
}

/** What a "minimize to icon" panel collapses down to — click to restore.
 * Deliberately tiny (a fixed 2-column grid slot, not the panel's normal
 * span) rather than the full card at a smaller height, so minimizing
 * several panels actually reclaims most of the row. */
export function PanelIconChip({ id, title }: { id: string; title: string }) {
  const { setState } = usePanelState(id);
  return (
    <button
      type="button"
      className={styles.iconChip}
      onClick={stop(() => setState("normal"))}
      aria-label={`Restore ${title}`}
      title={`Restore ${title}`}
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <rect x="3" y="4" width="18" height="16" rx="1" stroke="currentColor" strokeWidth="1.6" />
        <path d="M3 9h18" stroke="currentColor" strokeWidth="1.6" />
      </svg>
      <span className={styles.iconChipLabel}>{title}</span>
    </button>
  );
}
