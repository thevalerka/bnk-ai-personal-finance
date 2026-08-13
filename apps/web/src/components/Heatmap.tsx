import { fetchQuote } from "@/lib/market";
import styles from "./Heatmap.module.css";

// Modest sector-ETF universe — kept small deliberately to stay well inside
// Finnhub's free-tier budget (60 req/min, 1 call per symbol per quote —
// see config/budgets.yaml) for a block that renders on every page load.
const UNIVERSE = ["XLK", "XLF", "XLV", "XLY", "XLP", "XLE", "XLI", "XLB", "XLRE", "XLU", "XLC"];

const CLAMP_PCT = 3;

function cellColor(pct: number): string {
  const clamped = Math.max(-CLAMP_PCT, Math.min(CLAMP_PCT, pct));
  const intensity = Math.abs(clamped) / CLAMP_PCT;
  const hue = clamped >= 0 ? "57, 135, 229" : "230, 103, 103"; // accent blue / negative red
  return `rgba(${hue}, ${(0.12 + intensity * 0.68).toFixed(2)})`;
}

export async function Heatmap() {
  const quotes = await fetchQuote("equity_quote", UNIVERSE);

  if (!quotes || quotes.length === 0) {
    return <p style={{ color: "var(--text-muted)", fontSize: 13 }}>Heatmap unavailable — no equity quotes reachable.</p>;
  }

  return (
    <div className={styles.grid}>
      {quotes.map((quote) => {
        const pct = quote.change_percent ?? 0;
        return (
          <div key={quote.symbol} className={styles.cell} style={{ background: cellColor(pct) }}>
            <span className={styles.symbol}>{quote.symbol}</span>
            <span className={`${styles.pct} tabular-nums`}>
              {pct > 0 ? "+" : ""}
              {pct.toFixed(1)}%
            </span>
          </div>
        );
      })}
    </div>
  );
}
