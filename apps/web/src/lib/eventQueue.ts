// Module-level singleton queue: batches attention events and flushes them
// together every FLUSH_INTERVAL_MS (docs/PLAN.md section 4.3: "batched,
// ~2s debounce") rather than one HTTP request per hover/impression.
import { postEvents, type EventIn } from "./attention";

const FLUSH_INTERVAL_MS = 2000;

let queue: EventIn[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;

function flush(): void {
  timer = null;
  if (queue.length === 0) return;
  const batch = queue;
  queue = [];
  void postEvents(batch);
}

export function queueEvent(event: EventIn): void {
  queue.push(event);
  if (!timer) timer = setTimeout(flush, FLUSH_INTERVAL_MS);
}

if (typeof window !== "undefined") {
  // Best-effort flush of whatever's queued when the tab closes/backgrounds
  // — fetch(..., {keepalive: true}) (lib/attention.ts) is what actually
  // lets this survive navigation, pagehide/beforeunload just trigger it
  // promptly instead of waiting out the rest of the debounce window.
  window.addEventListener("pagehide", flush);
  window.addEventListener("beforeunload", flush);
}
