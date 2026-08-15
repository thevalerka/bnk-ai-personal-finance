import { fetchCandles, fetchQuote, type Candle, type Quote } from "@/lib/market";
import { Unavailable } from "./Block";
import { QuoteTile } from "./QuoteTile";
import { Sparkline } from "./Sparkline";
import styles from "./QuoteGrid.module.css";

export interface QuoteGroup {
  capability: string;
  candleCapability?: string;
  symbols: string[];
}

export function formatPrice(price: number): string {
  return price >= 1000 ? price.toLocaleString("en-US", { maximumFractionDigits: 0 }) : price.toFixed(2);
}

export function DeltaLabel({ quote }: { quote: Quote }) {
  const pct = quote.change_percent;
  if (pct === null || pct === undefined) {
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

export async function QuoteGrid({ groups }: { groups: QuoteGroup[] }) {
  const quoteResults = await Promise.all(groups.map((g) => fetchQuote(g.capability, g.symbols)));

  const quotesBySymbol = new Map<string, Quote>();
  for (const result of quoteResults) {
    for (const quote of result ?? []) {
      quotesBySymbol.set(quote.symbol, quote);
    }
  }

  const candleRequests: Array<{ symbol: string; promise: Promise<Candle[] | null> }> = [];
  for (const group of groups) {
    if (!group.candleCapability) continue;
    for (const symbol of group.symbols) {
      candleRequests.push({
        symbol,
        promise: fetchCandles(group.candleCapability, symbol, "1d", 20),
      });
    }
  }
  const candleResults = await Promise.all(candleRequests.map((r) => r.promise));
  const candlesBySymbol = new Map<string, Candle[]>();
  candleRequests.forEach((request, i) => {
    const candles = candleResults[i];
    if (candles && candles.length > 0) candlesBySymbol.set(request.symbol, candles);
  });

  const capabilityBySymbol = new Map<string, string>();
  for (const group of groups) {
    for (const symbol of group.symbols) capabilityBySymbol.set(symbol, group.capability);
  }
  const symbols = groups.flatMap((g) => g.symbols);

  if (quotesBySymbol.size === 0) {
    return <Unavailable reason="No live quotes reachable right now." />;
  }

  return (
    <div className={styles.grid}>
      {symbols.map((symbol) => {
        const quote = quotesBySymbol.get(symbol);
        if (!quote) {
          return (
            <div key={symbol} className={styles.tileUnavailable}>
              <div className={styles.symbol}>{symbol}</div>
              <div className={styles.unavailableLabel}>unavailable</div>
            </div>
          );
        }
        const candles = candlesBySymbol.get(symbol);
        const pct = quote.change_percent;
        const trend = pct === null || pct === undefined || pct === 0 ? "flat" : pct > 0 ? "up" : "down";
        // Only equities have a stock detail page (history + SEC filings) —
        // crypto/macro-series tiles (BTC, VIX, 2Y, ...) stay a plain,
        // non-clickable tile rather than link to a nonsensical stock page.
        if (capabilityBySymbol.get(symbol) !== "equity_quote") {
          return (
            <div key={symbol} className={styles.tile}>
              <div className={styles.tileTop}>
                <span className={styles.symbol}>{symbol}</span>
                <DeltaLabel quote={quote} />
              </div>
              <div className={styles.price}>{formatPrice(quote.price)}</div>
              {candles ? (
                <div className={styles.sparklineRow}>
                  <Sparkline candles={candles} width={140} height={32} trend={trend} />
                </div>
              ) : null}
            </div>
          );
        }
        return (
          <QuoteTile key={symbol} symbol={symbol} quote={quote} candles={candles} trend={trend} />
        );
      })}
    </div>
  );
}
