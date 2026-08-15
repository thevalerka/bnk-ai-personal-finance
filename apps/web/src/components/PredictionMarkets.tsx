import { fetchPredictions } from "@/lib/market";
import { Unavailable } from "./Block";
import styles from "./PredictionMarkets.module.css";

function formatVolume(volume: number): string {
  if (volume >= 1e6) return `$${(volume / 1e6).toFixed(1)}M vol`;
  if (volume >= 1e3) return `$${(volume / 1e3).toFixed(0)}K vol`;
  return `$${volume.toFixed(0)} vol`;
}

function formatEndDate(iso: string | null): string | null {
  if (!iso) return null;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function probabilityTone(pct: number): string {
  if (pct >= 60) return styles.probabilityHigh;
  if (pct <= 40) return styles.probabilityLow;
  return styles.probabilityMid;
}

// Real-money prediction markets, keyless (Polymarket) — market-implied odds,
// not a forecast the agent asserts as fact. Polymarket has no meaningful
// per-company earnings markets at real volume (verified live,
// docs/DECISIONS.md ADR-0024); its genuine finance/macro depth is Fed
// rate-decision markets and daily index-direction markets, so that's what
// this renders — an honest "what's actually there," not an aspirational
// "earnings calendar."
export async function PredictionMarkets() {
  const markets = await fetchPredictions();

  if (!markets || markets.length === 0) {
    return <Unavailable reason="No prediction markets reachable right now." />;
  }

  return (
    <ul className={styles.list}>
      {markets.slice(0, 10).map((market) => (
        <li key={market.question} className={styles.item}>
          <div className={styles.row}>
            <a href={market.url} target="_blank" rel="noreferrer" className={styles.question}>
              {market.question}
            </a>
            <span className={`${styles.probability} ${probabilityTone(market.probability_pct)}`}>
              {market.probability_pct.toFixed(0)}%
            </span>
          </div>
          <div className={styles.bar}>
            <div
              className={styles.barFill}
              style={{ width: `${Math.min(100, Math.max(0, market.probability_pct))}%` }}
            />
          </div>
          <div className={styles.meta}>
            <span>{formatVolume(market.volume_24h)}</span>
            {market.end_date ? <span>resolves {formatEndDate(market.end_date)}</span> : null}
          </div>
        </li>
      ))}
    </ul>
  );
}
