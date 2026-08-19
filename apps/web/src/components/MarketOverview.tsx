import { fetchPredictions, fetchQuote } from "@/lib/market";
import { DeltaLabel, formatPrice } from "./QuoteGrid";
import { PredictionOfDay } from "./PredictionOfDay";
import { Unavailable } from "./Block";
import styles from "./MarketOverview.module.css";

const STATUS_EQUITIES = ["SPY", "QQQ", "DIA"];

function formatVolume(volume: number): string {
  if (volume >= 1e6) return `$${(volume / 1e6).toFixed(1)}M vol`;
  if (volume >= 1e3) return `$${(volume / 1e3).toFixed(0)}K vol`;
  return `$${volume.toFixed(0)} vol`;
}

// First-row "at a glance" panel (user request): market status, the day's
// top prediction, and a few more real Polymarket odds as a "breaking"
// strip — a mix of the three, not a new data source. Zero new backend:
// reuses the same fetchQuote/fetchPredictions calls Tape/QuoteGrid and
// PredictionMarkets already make elsewhere on the page, and embeds
// PredictionOfDay as-is (it already handles its own "nothing resolves
// that soon" degrade) rather than re-deriving that pick here.
export async function MarketOverview() {
  const [equities, crypto, predictions, topPrediction] = await Promise.all([
    fetchQuote("equity_quote", STATUS_EQUITIES),
    fetchQuote("crypto_quote", ["BTC"]),
    fetchPredictions(),
    // Awaited here rather than used as an unresolved `<PredictionOfDay />`
    // JSX child — nesting one async Server Component inside another as a
    // not-yet-awaited element only resolves correctly under Next's own RSC
    // render pipeline, not under a plain `render()` call (including this
    // component's own tests), so this stays composable everywhere.
    PredictionOfDay(),
  ]);

  const statusQuotes = [...(equities ?? []), ...(crypto ?? [])];
  const breaking = (predictions ?? []).slice(0, 3);

  return (
    <div className={styles.wrap}>
      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>Market status</h3>
        {statusQuotes.length > 0 ? (
          <ul className={styles.statusList}>
            {statusQuotes.map((quote) => (
              <li key={quote.symbol} className={styles.statusRow}>
                <span className={styles.statusSymbol}>{quote.symbol}</span>
                <span className={styles.statusPrice}>{formatPrice(quote.price)}</span>
                <DeltaLabel quote={quote} />
              </li>
            ))}
          </ul>
        ) : (
          <Unavailable reason="No live quotes reachable right now." />
        )}
      </section>

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>Top prediction</h3>
        {topPrediction}
      </section>

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>Breaking · Polymarket</h3>
        {breaking.length > 0 ? (
          <ul className={styles.breakingList}>
            {breaking.map((market) => (
              <li key={market.question} className={styles.breakingRow}>
                <a href={market.url} target="_blank" rel="noreferrer" className={styles.breakingQuestion}>
                  {market.question}
                </a>
                <span className={styles.breakingMeta}>
                  {market.probability_pct.toFixed(0)}% · {formatVolume(market.volume_24h)}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          <Unavailable reason="No prediction markets reachable right now." />
        )}
      </section>
    </div>
  );
}
