"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

export type PanelState = "normal" | "expanded" | "icon" | "deleted";

const STORAGE_KEY = "amt-panel-prefs";

// Every panel a user can expand/minimize/delete, with a stable id
// (independent of its display title, which the dashboard may relabel
// without breaking a visitor's saved preference) and the title the
// restore tray shows for a deleted one. Kept as one static registry
// rather than each panel self-registering, since the restore tray needs
// to list a deleted panel's name without that panel being mounted
// anywhere to ask.
export const PANEL_REGISTRY: { id: string; title: string }[] = [
  { id: "quotes", title: "Quotes" },
  { id: "yield_curve", title: "US Treasury Yield Curve" },
  { id: "heatmap", title: "Sector Heatmap" },
  { id: "news", title: "News" },
  { id: "calendar", title: "Calendar" },
  { id: "most_traded", title: "Most Traded" },
  { id: "world_map", title: "World Indices" },
  // forex/predictions were missing from this registry even though both
  // already render inside a PanelSlot — found while adding
  // earnings_calendar below: deleting either one made it vanish with no
  // way to restore it, since useDeletedPanels() filters against this list.
  { id: "forex", title: "Forex" },
  { id: "predictions", title: "Prediction Markets" },
  { id: "earnings_calendar", title: "Earnings Calendar" },
];

interface PanelPrefsContextValue {
  getState: (id: string) => PanelState;
  setState: (id: string, state: PanelState) => void;
}

const PanelPrefsContext = createContext<PanelPrefsContextValue | null>(null);

function loadPrefs(): Record<string, PanelState> {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Record<string, PanelState>) : {};
  } catch {
    return {};
  }
}

export function PanelPrefsProvider({ children }: { children: ReactNode }) {
  // Starts empty (server-rendered default = "normal" for everything,
  // matching what a first-time visitor with no saved prefs sees anyway) and
  // hydrates from localStorage on mount — same server/client-mismatch-safe
  // pattern as ThemeToggle.tsx's default-until-mount handling.
  const [prefs, setPrefs] = useState<Record<string, PanelState>>({});

  useEffect(() => {
    setPrefs(loadPrefs());
  }, []);

  const getState = useCallback((id: string) => prefs[id] ?? "normal", [prefs]);

  const setState = useCallback((id: string, state: PanelState) => {
    setPrefs((prev) => {
      const next = { ...prev, [id]: state };
      // "normal" is the default — dropping it instead of storing it keeps
      // the persisted blob (and the deleted-panel restore tray's source of
      // truth) limited to actual customizations.
      if (state === "normal") delete next[id];
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  return (
    <PanelPrefsContext.Provider value={{ getState, setState }}>
      {children}
    </PanelPrefsContext.Provider>
  );
}

export function usePanelState(id: string): { state: PanelState; setState: (s: PanelState) => void } {
  const ctx = useContext(PanelPrefsContext);
  if (!ctx) throw new Error("usePanelState must be used within PanelPrefsProvider");
  return { state: ctx.getState(id), setState: (s) => ctx.setState(id, s) };
}

/** For the restore tray: every panel currently hidden, id+title only —
 * doesn't need the panel itself mounted anywhere. */
export function useDeletedPanels(): { id: string; title: string }[] {
  const ctx = useContext(PanelPrefsContext);
  if (!ctx) throw new Error("useDeletedPanels must be used within PanelPrefsProvider");
  return PANEL_REGISTRY.filter((p) => ctx.getState(p.id) === "deleted");
}

export function useSetPanelState(): (id: string, state: PanelState) => void {
  const ctx = useContext(PanelPrefsContext);
  if (!ctx) throw new Error("useSetPanelState must be used within PanelPrefsProvider");
  return ctx.setState;
}
