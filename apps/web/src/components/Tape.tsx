import Link from "next/link";
import { fetchTape, type Quote } from "@/lib/market";
import styles from "./Tape.module.css";

// Raw FRED series IDs read as noise in a ticker tape — display-only labels,
// same convention as YieldCurve.tsx's tenor labels. Everything else (equity
// tickers, BTC/ETH) is already a recognizable symbol as-is.
const SYMBOL_LABELS: Record<string, string> = {
  VIXCLS: "VIX",
  DCOILWTICO: "WTI",
  DGS2: "2Y",
  DGS10: "10Y",
};

// Mirrors TAPE_SPEC's equity_quote list (apps/api/app/api/market.py) — same
// hand-maintained-parallel convention as SYMBOL_LABELS above. Only equities
// link to a stock detail page; BTC/ETH and the FRED macro series don't have
// one (QuoteGrid.tsx applies the same equity_quote-only restriction).
const EQUITY_TAPE_SYMBOLS = new Set([
  "SPY",
  "QQQ",
  "DIA",
  "IWM",
  "AAPL",
  "MSFT",
  "NVDA",
  "AMZN",
  "GOOGL",
  "META",
  "TSLA",
]);

function TapeItems({ quotes, hidden = false }: { quotes: Quote[]; hidden?: boolean }) {
  return (
    <>
      {quotes.map((quote) => {
        const pct = quote.change_percent;
        const direction = pct === null || pct === undefined || pct === 0
          ? styles.deltaFlat
          : pct > 0
            ? styles.deltaUp
            : styles.deltaDown;
        const arrow = pct === null || pct === undefined ? "" : pct > 0 ? "▲" : pct < 0 ? "▼" : "";
        const content = (
          <>
            <span className={styles.symbol}>{SYMBOL_LABELS[quote.symbol] ?? quote.symbol}</span>
            <span className={`${styles.price} tabular-nums`}>
              {quote.price >= 1000 ? quote.price.toLocaleString("en-US", { maximumFractionDigits: 0 }) : quote.price.toFixed(2)}
            </span>
            {pct !== null && pct !== undefined ? (
              <span className={`${direction} ${styles.pill} tabular-nums`}>
                {arrow} {Math.abs(pct).toFixed(2)}%
              </span>
            ) : null}
          </>
        );
        return EQUITY_TAPE_SYMBOLS.has(quote.symbol) ? (
          <Link
            key={quote.symbol}
            href={`/stock/${quote.symbol}`}
            className={`${styles.item} ${styles.itemLink}`}
            // The marquee's second copy (aria-hidden, purely visual for the
            // seamless scroll loop) would otherwise still be a real,
            // keyboard-focusable link — aria-hidden alone doesn't remove
            // focusability, so tabIndex=-1 does that explicitly.
            tabIndex={hidden ? -1 : undefined}
          >
            {content}
          </Link>
        ) : (
          <span key={quote.symbol} className={styles.item}>
            {content}
          </span>
        );
      })}
    </>
  );
}

export async function Tape() {
  const quotes = await fetchTape();

  if (!quotes || quotes.length === 0) {
    return (
      <div className={styles.tape}>
        <span className={styles.empty}>Global tape unavailable — no provider reachable.</span>
      </div>
    );
  }

  return (
    <div className={styles.tape} role="marquee" aria-label="global market tape">
      <div className={styles.viewport}>
        <div className={styles.track}>
          <div className={styles.trackSegment}>
            <TapeItems quotes={quotes} />
          </div>
          <div className={styles.trackSegment} aria-hidden="true">
            <TapeItems quotes={quotes} hidden />
          </div>
        </div>
      </div>
    </div>
  );
}
