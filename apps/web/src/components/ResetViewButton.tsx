"use client";

import { useState } from "react";
import { resetProfile } from "@/lib/attention";
import styles from "./ResetViewButton.module.css";

const PANEL_PREFS_KEY = "amt-panel-prefs";

// Top-right "start over" control (user request) — distinct from
// PersonaSwitcher's "View as: Default" (that resets just the interest
// vector, buried inside a dropdown). This wipes both halves of a visitor's
// accumulated state in one click: the server-side interest vector
// (POST /profile/reset, same endpoint PersonaSwitcher's "Default" option
// already uses) and the client-side manual panel expand/icon/delete
// overrides (PanelPrefs.tsx's localStorage blob) — then reloads so every
// part of the page (DynamicGrid's layout fetch, PanelSlot's per-panel
// state) picks the clean state back up consistently.
export function ResetViewButton() {
  const [resetting, setResetting] = useState(false);

  async function handleReset() {
    if (resetting) return;
    setResetting(true);
    const result = await resetProfile();
    window.localStorage.removeItem(PANEL_PREFS_KEY);
    if (result) {
      window.location.reload();
    } else {
      setResetting(false);
    }
  }

  return (
    <button
      type="button"
      className={styles.button}
      onClick={() => void handleReset()}
      disabled={resetting}
      title="Reset the dashboard back to its default layout"
    >
      <svg
        className={styles.icon}
        width="12"
        height="12"
        viewBox="0 0 24 24"
        fill="none"
        aria-hidden="true"
      >
        <path
          d="M20 12a8 8 0 1 1-2.34-5.66M20 4v5h-5"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {resetting ? "Resetting…" : "Reset view"}
    </button>
  );
}
