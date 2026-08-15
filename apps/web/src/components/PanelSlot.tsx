"use client";

import type { CSSProperties, ReactNode } from "react";
import { usePanelState } from "./PanelPrefs";
import { PanelIconChip } from "./PanelControls";

/** Wraps a static (non-attention-engine) dashboard panel's grid cell —
 * News/Calendar/Most-Traded/World-Map — applying whatever state the user
 * last chose for it (Block.tsx's header controls write that state; this
 * reads it). Deleted panels render nothing at all, so the grid genuinely
 * reflows around the gap rather than leaving an empty cell; DynamicGrid.tsx
 * does the equivalent for the 3 attention-engine blocks, which need their
 * own ref/tracking wiring alongside the same state. */
export function PanelSlot({
  id,
  title,
  spanClassName,
  children,
}: {
  id: string;
  title: string;
  spanClassName: string;
  children: ReactNode;
}) {
  const { state } = usePanelState(id);

  if (state === "deleted") return null;

  if (state === "icon") {
    return (
      <div style={{ gridColumn: "span 2" }}>
        <PanelIconChip id={id} title={title} />
      </div>
    );
  }

  const style: CSSProperties | undefined = state === "expanded" ? { gridColumn: "1 / -1" } : undefined;
  return (
    <div className={state === "expanded" ? undefined : spanClassName} style={style}>
      {children}
    </div>
  );
}
