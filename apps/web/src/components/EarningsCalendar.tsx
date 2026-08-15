import { fetchEarningsCalendar } from "@/lib/market";
import { Unavailable } from "./Block";
import styles from "./EarningsCalendar.module.css";

function formatDayHeader(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

function probabilityTone(pct: number): string {
  if (pct >= 60) return styles.probabilityHigh;
  if (pct <= 40) return styles.probabilityLow;
  return styles.probabilityMid;
}

function dayKey(iso: string): string {
  return iso.slice(0, 10);
}

// polymarket.com/earnings — real per-company "beat consensus EPS" markets,
// grouped by report date like the source page (docs/DECISIONS.md ADR-0026).
// A distinct feed from the Prediction Markets panel's Fed-rate/S&P-direction
// markets — this one is specifically earnings.
export async function EarningsCalendar() {
  const markets = await fetchEarningsCalendar();

  if (!markets || markets.length === 0) {
    return <Unavailable reason="No earnings markets reachable right now." />;
  }

  const groups = new Map<string, typeof markets>();
  for (const market of markets) {
    if (!market.report_date) continue;
    const key = dayKey(market.report_date);
    const existing = groups.get(key);
    if (existing) {
      existing.push(market);
    } else {
      groups.set(key, [market]);
    }
  }
  const days = [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));

  return (
    <div className={styles.calendar}>
      {days.map(([day, dayMarkets]) => (
        <div key={day} className={styles.day}>
          <div className={styles.dayHeader}>{formatDayHeader(dayMarkets[0].report_date!)}</div>
          <ul className={styles.list}>
            {dayMarkets.map((market) => (
              <li key={market.ticker + market.url} className={styles.item}>
                <a
                  href={market.url}
                  target="_blank"
                  rel="noreferrer"
                  className={styles.row}
                  title={market.company}
                >
                  <span className={styles.ticker}>{market.ticker}</span>
                  <span className={styles.eps}>
                    {market.eps_estimate ? `est. ${market.eps_estimate}` : "—"}
                  </span>
                  <span className={`${styles.probability} ${probabilityTone(market.probability_pct)}`}>
                    {market.probability_pct.toFixed(0)}%
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
