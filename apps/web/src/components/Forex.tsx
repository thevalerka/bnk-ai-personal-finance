import { fetchQuote, fetchCandles, type Candle } from "@/lib/market";
import { Sparkline } from "./Sparkline";
import { Unavailable } from "./Block";
import styles from "./QuoteGrid.module.css";

// FRED's daily H.10 FX release, same series already verified live for the
// World Map's currency labels (docs/DECISIONS.md ADR-0016) — no new
// provider. FredProvider.quote() doesn't compute change/change_percent
// (single-observation fetch, unlike Finnhub/Alpaca), so trend and % change
// here are derived client-side from the last two candle closes instead —
// candles are already fetched for the sparkline anyway.
const PAIRS: { symbol: string; label: string }[] = [
  { symbol: "DEXUSEU", label: "EUR/USD" },
  { symbol: "DEXUSUK", label: "GBP/USD" },
  { symbol: "DEXUSAL", label: "AUD/USD" },
  { symbol: "DEXJPUS", label: "USD/JPY" },
  { symbol: "DEXCAUS", label: "USD/CAD" },
  { symbol: "DEXSZUS", label: "USD/CHF" },
  { symbol: "DEXCHUS", label: "USD/CNY" },
];

function formatRate(price: number): string {
  return price < 10 ? price.toFixed(4) : price.toFixed(2);
}

function DeltaPill({ pct }: { pct: number | null }) {
  if (pct === null) {
    return <span className={`${styles.delta} ${styles.deltaFlat}`}>—</span>;
  }
  const direction = pct > 0 ? styles.deltaUp : pct < 0 ? styles.deltaDown : styles.deltaFlat;
  const arrow = pct > 0 ? "▲" : pct < 0 ? "▼" : "•";
  return (
    <span className={`${styles.delta} ${direction} tabular-nums`}>
      {arrow} {Math.abs(pct).toFixed(2)}%
    </span>
  );
}

export async function Forex() {
  const [quotes, ...candleResults] = await Promise.all([
    fetchQuote(
      "macro_series",
      PAIRS.map((p) => p.symbol),
    ),
    ...PAIRS.map((p) => fetchCandles("macro_series", p.symbol, "1d", 20)),
  ]);

  const quoteBySymbol = new Map((quotes ?? []).map((q) => [q.symbol, q]));
  const candlesBySymbol = new Map<string, Candle[]>();
  PAIRS.forEach((pair, i) => {
    const candles = candleResults[i];
    if (candles && candles.length > 0) candlesBySymbol.set(pair.symbol, candles);
  });

  if (quoteBySymbol.size === 0) {
    return <Unavailable reason="No live FX rates reachable right now." />;
  }

  return (
    <div className={styles.grid}>
      {PAIRS.map(({ symbol, label }) => {
        const quote = quoteBySymbol.get(symbol);
        if (!quote) {
          return (
            <div key={symbol} className={styles.tileUnavailable}>
              <div className={styles.symbol}>{label}</div>
              <div className={styles.unavailableLabel}>unavailable</div>
            </div>
          );
        }
        const candles = candlesBySymbol.get(symbol);
        const pct =
          candles && candles.length >= 2
            ? ((candles[candles.length - 1].close - candles[candles.length - 2].close) /
                candles[candles.length - 2].close) *
              100
            : null;
        const trend = pct === null || pct === 0 ? "flat" : pct > 0 ? "up" : "down";
        return (
          <div key={symbol} className={styles.tile}>
            <div className={styles.tileTop}>
              <span className={styles.symbol}>{label}</span>
              <DeltaPill pct={pct} />
            </div>
            <div className={styles.price}>{formatRate(quote.price)}</div>
            {candles ? (
              <div className={styles.sparklineRow}>
                <Sparkline candles={candles} width={140} height={32} trend={trend} />
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
