import { fetchCalendar, type MarketEvent } from "@/lib/market";
import { Unavailable } from "./Block";
import styles from "./EconomicCalendar.module.css";

const VISIBLE_COUNT = 10;

// Finnhub's earnings feed is an unfiltered universe of every public
// company reporting on a given day — hundreds of same-day entries, mostly
// obscure small-caps. A pure chronological slice lets that volume bury
// the primary-source additions (Treasury auctions, FRED macro releases)
// entirely: verified live that /market/calendar's real top-10 was 100%
// earnings despite 7 non-earnings events being in the (larger) response.
// Reserve slots for non-earnings kinds first, then backfill with the
// earliest earnings, so every source that's actually wired stays visible.
function selectVisible(events: MarketEvent[]): MarketEvent[] {
  const nonEarnings = events.filter((e) => e.kind !== "earnings");
  const earnings = events.filter((e) => e.kind === "earnings");
  return [...nonEarnings, ...earnings]
    .slice(0, VISIBLE_COUNT)
    .sort((a, b) => a.ts.localeCompare(b.ts));
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// Categorical identity dots, assigned in fixed order per the dataviz skill:
// earnings gets slot 1 (accent blue), macro_release slot 2 (series-2
// orange) — never reassigned per filter or sort, so a symbol keeps its
// color everywhere it appears. Auction reuses the neutral/muted slot
// rather than a third invented hue (no new color needs palette
// re-validation, and it fits: auctions are the lowest-importance kind here).
function kindDot(kind: string): string {
  if (kind === "earnings") return styles.dotEarnings;
  if (kind === "auction") return styles.dotAuction;
  return styles.dotMacro;
}

export async function EconomicCalendar() {
  const events = await fetchCalendar();

  if (!events || events.length === 0) {
    return <Unavailable reason="Calendar unavailable — no provider reachable." />;
  }

  return (
    <ul className={styles.list}>
      {selectVisible(events).map((event, i) => (
        <li key={`${event.ts}-${i}`} className={styles.item}>
          <span className={`${styles.date} tabular-nums`}>{formatDate(event.ts)}</span>
          <span className={styles.title}>{event.title}</span>
          <span className={styles.kind}>
            <span className={`${styles.dot} ${kindDot(event.kind)}`} aria-hidden="true" />
            {event.kind.replace("_", " ")}
          </span>
        </li>
      ))}
    </ul>
  );
}
