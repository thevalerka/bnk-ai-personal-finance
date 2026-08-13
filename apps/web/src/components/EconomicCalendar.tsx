import { fetchCalendar } from "@/lib/market";
import styles from "./EconomicCalendar.module.css";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export async function EconomicCalendar() {
  const events = await fetchCalendar();

  if (!events || events.length === 0) {
    return <p style={{ color: "var(--text-muted)", fontSize: 13 }}>Calendar unavailable — no provider reachable.</p>;
  }

  return (
    <ul className={styles.list}>
      {events.slice(0, 10).map((event, i) => (
        <li key={`${event.ts}-${i}`} className={styles.item}>
          <span className={`${styles.date} tabular-nums`}>{formatDate(event.ts)}</span>
          <span className={styles.title}>{event.title}</span>
          <span className={styles.kind}>{event.kind}</span>
        </li>
      ))}
    </ul>
  );
}
