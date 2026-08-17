import Link from "next/link";
import { fetchXStocksTeaser } from "@/lib/market";
import { Unavailable } from "./Block";
import styles from "./PredictionMarkets.module.css";

// Read-only dashboard teaser for the full swap UI on /xstocks
// (docs/DECISIONS.md ADR-0029) — same real-prices-or-nothing discipline as
// every other block, just a shorter list with a link to the rest.
export async function XStocksTeaser() {
  const xstocks = await fetchXStocksTeaser();

  if (!xstocks || xstocks.length === 0) {
    return <Unavailable reason="No xStocks reachable right now." />;
  }

  return (
    <div>
      <ul className={styles.list}>
        {xstocks.slice(0, 6).map((x) => (
          <li key={x.symbol} className={styles.item}>
            <div className={styles.row}>
              <span className={styles.question}>
                {x.symbol}
                {x.category === "pre_ipo" ? " · pre-IPO" : ""}
              </span>
              <span className={styles.probability}>${x.price_usd.toFixed(2)}</span>
            </div>
          </li>
        ))}
      </ul>
      <Link href="/xstocks" className={styles.question}>
        View all xStocks →
      </Link>
    </div>
  );
}
