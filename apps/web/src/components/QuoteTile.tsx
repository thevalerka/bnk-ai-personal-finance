"use client";

import Link from "next/link";
import type { Candle, Quote } from "@/lib/market";
import { DeltaLabel, formatPrice } from "./QuoteGrid";
import { Sparkline } from "./Sparkline";
import styles from "./QuoteGrid.module.css";

// A plain <div> tile would only ever open the ancestor DynamicGrid card's
// "why am I seeing this" explain panel (its onClick wraps the whole block,
// see DynamicGrid.tsx) — stopPropagation here is what lets a tile navigate
// to its own stock detail page instead, same fix PanelControls.tsx already
// applies for its own buttons inside that same click zone.
export function QuoteTile({
  symbol,
  quote,
  candles,
  trend,
}: {
  symbol: string;
  quote: Quote;
  candles?: Candle[];
  trend: "up" | "down" | "flat";
}) {
  return (
    <Link
      href={`/stock/${encodeURIComponent(symbol)}`}
      className={`${styles.tile} ${styles.tileLink}`}
      onClick={(event) => event.stopPropagation()}
    >
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
    </Link>
  );
}
