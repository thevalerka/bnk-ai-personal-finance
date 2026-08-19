import { fetchQuote } from "@/lib/market";
import { Unavailable } from "./Block";
import styles from "./Heatmap.module.css";

// Modest sector-ETF universe — kept small deliberately to stay well inside
// Finnhub's free-tier budget (60 req/min, 1 call per symbol per quote —
// see config/budgets.yaml) for a block that renders on every page load.
const UNIVERSE = ["XLK", "XLF", "XLV", "XLY", "XLP", "XLE", "XLI", "XLB", "XLRE", "XLU", "XLC"];

// Sector-ETF tickers on their own ("XLK", "XLB", ...) aren't comprehensible
// to anyone who doesn't already have the SPDR sector-fund lineup memorized
// (user feedback) — the cell's primary label is the real sector name now,
// with the ticker kept underneath (smaller, muted) for anyone who does.
const SECTOR_NAMES: Record<string, string> = {
  XLK: "Technology",
  XLF: "Financials",
  XLV: "Health Care",
  XLY: "Cons. Discretionary",
  XLP: "Cons. Staples",
  XLE: "Energy",
  XLI: "Industrials",
  XLB: "Materials",
  XLRE: "Real Estate",
  XLU: "Utilities",
  XLC: "Comm. Services",
};

const CLAMP_PCT = 3;

function cellColor(pct: number): string {
  const clamped = Math.max(-CLAMP_PCT, Math.min(CLAMP_PCT, pct));
  const intensity = Math.abs(clamped) / CLAMP_PCT;
  // rgba(var(--x-rgb), alpha): a raw custom property, substituted by the
  // browser at paint time — stays theme-reactive even though this string is
  // built here in a Server Component with no knowledge of the client's
  // chosen theme (globals.css, --accent-rgb/--negative-rgb).
  const rgbVar = clamped >= 0 ? "var(--accent-rgb)" : "var(--negative-rgb)";
  return `rgba(${rgbVar}, ${(0.14 + intensity * 0.66).toFixed(2)})`;
}

export async function Heatmap() {
  const quotes = await fetchQuote("equity_quote", UNIVERSE);

  if (!quotes || quotes.length === 0) {
    return <Unavailable reason="Heatmap unavailable — no equity quotes reachable." />;
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.grid}>
        {quotes.map((quote) => {
          const pct = quote.change_percent ?? 0;
          const name = SECTOR_NAMES[quote.symbol] ?? quote.symbol;
          return (
            <div
              key={quote.symbol}
              className={styles.cell}
              style={{ background: cellColor(pct) }}
              tabIndex={0}
              title={`${name} (${quote.symbol}): ${pct > 0 ? "+" : ""}${pct.toFixed(2)}% (${quote.price.toLocaleString("en-US", { maximumFractionDigits: 2 })})`}
            >
              <span className={styles.name}>{name}</span>
              <span className={styles.symbol}>{quote.symbol}</span>
              <span className={`${styles.pct} tabular-nums`}>
                {pct > 0 ? "+" : ""}
                {pct.toFixed(1)}%
              </span>
            </div>
          );
        })}
      </div>
      <div className={styles.legend} aria-hidden="true">
        <span>−{CLAMP_PCT}%</span>
        <div className={styles.legendBar} />
        <span>+{CLAMP_PCT}%</span>
      </div>
    </div>
  );
}
