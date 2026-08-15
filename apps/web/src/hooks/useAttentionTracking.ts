"use client";

import { useCallback, useEffect, useRef, type RefObject } from "react";
import { queueEvent } from "@/lib/eventQueue";

// docs/PLAN.md section 4.3's event/weight table.
const IMPRESSION_DELAY_MS = 1000; // ">1s in viewport"
const DWELL_INTERVAL_MS = 5000; // "per additional 5s visible"
const HOVER_DEBOUNCE_MS = 10_000; // don't refire on every re-hover of the same block

/** Wires impression/dwell/hover/click tracking onto `ref`'s element for a
 * given taxonomy leaf node — the caller owns the ref (usually because it's
 * also measuring the same element for something else, e.g. DynamicGrid's
 * FLIP animation) and just spreads the returned handlers onto it. Pass
 * `nodeId={null}` for anything not mapped to a taxonomy node (News/
 * Calendar — see docs/DECISIONS.md ADR-0012) to no-op. */
export function useAttentionTracking(
  ref: RefObject<HTMLElement | null>,
  nodeId: string | null,
) {
  const lastHoverAt = useRef(0);

  useEffect(() => {
    const el = ref.current;
    if (!nodeId || !el) return;

    let impressionTimer: ReturnType<typeof setTimeout> | null = null;
    let dwellTimer: ReturnType<typeof setInterval> | null = null;

    const clearTimers = () => {
      if (impressionTimer) clearTimeout(impressionTimer);
      if (dwellTimer) clearInterval(dwellTimer);
      impressionTimer = null;
      dwellTimer = null;
    };

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          impressionTimer = setTimeout(() => {
            queueEvent({ node_id: nodeId, kind: "impression" });
            dwellTimer = setInterval(() => {
              queueEvent({ node_id: nodeId, kind: "dwell" });
            }, DWELL_INTERVAL_MS);
          }, IMPRESSION_DELAY_MS);
        } else {
          clearTimers();
        }
      },
      { threshold: 0.5 },
    );
    observer.observe(el);

    return () => {
      observer.disconnect();
      clearTimers();
    };
  }, [ref, nodeId]);

  const onMouseEnter = useCallback(() => {
    if (!nodeId) return;
    const now = Date.now();
    if (now - lastHoverAt.current < HOVER_DEBOUNCE_MS) return;
    lastHoverAt.current = now;
    queueEvent({ node_id: nodeId, kind: "hover" });
  }, [nodeId]);

  const onClick = useCallback(() => {
    if (nodeId) queueEvent({ node_id: nodeId, kind: "click" });
  }, [nodeId]);

  return { onMouseEnter, onClick };
}
