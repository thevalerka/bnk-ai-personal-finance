import { fetchCandles, fetchQuote, type Candle, type Quote } from "@/lib/market";
import { Sparkline } from "./Sparkline";
import styles from "./QuoteGrid.module.css";

export interface QuoteGroup {
  capability: string;
  candleCapability?: string;
  symbols: string[];
}

function formatPrice(price: number): string {
  return price >= 1000 ? price.toLocaleString("en-US", { maximumFractionDigits: 0 }) : price.toFixed(2);
}

function DeltaLabel({ quote }: { quote: Quote }) {
  const pct = quote.change_percent;
  if (pct === null || pct === undefined) {
    return <span className={`${styles.delta} ${styles.deltaFlat}`}>—</span>;
  }
  const direction = pct > 0 ? styles.deltaUp : pct < 0 ? styles.deltaDown : styles.deltaFlat;
  const arrow = pct > 0 ? "▲" : pct < 0 ? "▼" : "•";
  return (
    <span className={`${styles.delta} ${direction}`}>
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

  const symbols = groups.flatMap((g) => g.symbols);

  if (quotesBySymbol.size === 0) {
    return <p style={{ color: "var(--text-muted)", fontSize: 13 }}>No live quotes reachable right now.</p>;
  }

  return (
    <div className={styles.grid}>
      {symbols.map((symbol) => {
        const quote = quotesBySymbol.get(symbol);
        if (!quote) {
          return (
            <div key={symbol} className={styles.tileUnavailable}>
              <div className={styles.symbol}>{symbol}</div>
              <div>unavailable</div>
            </div>
          );
        }
        const candles = candlesBySymbol.get(symbol);
        return (
          <div key={symbol} className={styles.tile}>
            <div className={styles.symbol}>{symbol}</div>
            <div className={`${styles.price} tabular-nums`}>{formatPrice(quote.price)}</div>
            <div className={styles.deltaRow}>
              <DeltaLabel quote={quote} />
              {candles ? <Sparkline candles={candles} width={72} height={22} /> : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}
