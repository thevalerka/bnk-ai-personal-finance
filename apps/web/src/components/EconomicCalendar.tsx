import { fetchCalendar } from "@/lib/market";
import { Unavailable } from "./Block";
import styles from "./EconomicCalendar.module.css";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

// Categorical identity dots, assigned in fixed order per the dataviz skill:
// first kind encountered (earnings) gets slot 1 (accent blue), the second
// (macro_release) gets slot 2 (series-2 orange) — never reassigned per
// filter or sort, so a symbol keeps its color everywhere it appears.
function kindDot(kind: string): string {
  return kind === "earnings" ? styles.dotEarnings : styles.dotMacro;
}

export async function EconomicCalendar() {
  const events = await fetchCalendar();

  if (!events || events.length === 0) {
    return <Unavailable reason="Calendar unavailable — no provider reachable." />;
  }

  return (
    <ul className={styles.list}>
      {events.slice(0, 10).map((event, i) => (
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
