import { fetchPredictions } from "@/lib/market";
import { Unavailable } from "./Block";
import styles from "./PredictionOfDay.module.css";

const DAY_MS = 24 * 60 * 60 * 1000;

function formatTimeLeft(endDate: string): string {
  const hoursLeft = (new Date(endDate).getTime() - Date.now()) / (60 * 60 * 1000);
  if (hoursLeft < 1) return `${Math.max(1, Math.round(hoursLeft * 60))}m left`;
  return `${Math.round(hoursLeft)}h left`;
}

function formatVolume(volume: number): string {
  if (volume >= 1e6) return `$${(volume / 1e6).toFixed(1)}M vol`;
  if (volume >= 1e3) return `$${(volume / 1e3).toFixed(0)}K vol`;
  return `$${volume.toFixed(0)} vol`;
}

function probabilityTone(pct: number): string {
  if (pct >= 60) return styles.high;
  if (pct <= 40) return styles.low;
  return styles.mid;
}

// Top-left slot, replacing World Map (user request). Reuses the same
// polymarket.probability() feed PredictionMarkets already fetches
// (docs/DECISIONS.md ADR-0024) rather than adding a new endpoint — this
// just narrows it, server-side, to whatever real market from that feed
// actually resolves in the next 24h, picking the highest-volume one. If
// nothing in the ranked feed resolves that soon, say so rather than
// showing a market that isn't really "today."
export async function PredictionOfDay() {
  const markets = await fetchPredictions();
  if (!markets) {
    return <Unavailable reason="No prediction markets reachable right now." />;
  }

  const now = Date.now();
  const dueToday = markets
    .filter((m) => {
      if (!m.end_date) return false;
      const endMs = new Date(m.end_date).getTime();
      return endMs > now && endMs - now <= DAY_MS;
    })
    .sort((a, b) => b.volume_24h - a.volume_24h);

  const pick = dueToday[0];
  if (!pick) {
    return <Unavailable reason="No Polymarket finance market resolves in the next 24 hours right now." />;
  }

  return (
    <a href={pick.url} target="_blank" rel="noreferrer" className={styles.card}>
      <div className={styles.eyebrow}>
        <span>Resolves today</span>
        <span className={styles.timeLeft}>{formatTimeLeft(pick.end_date as string)}</span>
      </div>
      <p className={styles.question}>{pick.question}</p>
      <div className={styles.probabilityRow}>
        <span className={`${styles.probability} ${probabilityTone(pick.probability_pct)}`}>
          {pick.probability_pct.toFixed(0)}%
        </span>
        <span className={styles.probabilityLabel}>market-implied odds</span>
      </div>
      <div className={styles.bar}>
        <div
          className={styles.barFill}
          style={{ width: `${Math.min(100, Math.max(0, pick.probability_pct))}%` }}
        />
      </div>
      <div className={styles.meta}>{formatVolume(pick.volume_24h)}</div>
    </a>
  );
}
