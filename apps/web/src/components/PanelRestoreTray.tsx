"use client";

import { useDeletedPanels, useSetPanelState } from "./PanelPrefs";
import styles from "./PanelRestoreTray.module.css";

/** The only way to bring back a deleted panel — Block.tsx's delete button
 * has no undo of its own, and the panel itself isn't rendered anywhere to
 * click on. Renders nothing when no panel is currently deleted. */
export function PanelRestoreTray() {
  const deleted = useDeletedPanels();
  const setState = useSetPanelState();

  if (deleted.length === 0) return null;

  return (
    <div className={styles.tray} role="group" aria-label="Hidden panels">
      <span className={styles.label}>Hidden:</span>
      {deleted.map((panel) => (
        <button
          key={panel.id}
          type="button"
          className={styles.chip}
          onClick={() => setState(panel.id, "normal")}
          title={`Restore ${panel.title}`}
        >
          {panel.title}
          <span className={styles.plus} aria-hidden="true">
            +
          </span>
        </button>
      ))}
    </div>
  );
}
