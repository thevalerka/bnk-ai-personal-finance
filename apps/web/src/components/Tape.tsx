import { fetchTape, type Quote } from "@/lib/market";
import styles from "./Tape.module.css";

function TapeItems({ quotes }: { quotes: Quote[] }) {
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
        return (
          <span key={quote.symbol} className={styles.item}>
            <span className={styles.symbol}>{quote.symbol}</span>
            <span className={`${styles.price} tabular-nums`}>
              {quote.price >= 1000 ? quote.price.toLocaleString("en-US", { maximumFractionDigits: 0 }) : quote.price.toFixed(2)}
            </span>
            {pct !== null && pct !== undefined ? (
              <span className={`${direction} ${styles.pill} tabular-nums`}>
                {arrow} {Math.abs(pct).toFixed(2)}%
              </span>
            ) : null}
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
            <TapeItems quotes={quotes} />
          </div>
        </div>
      </div>
    </div>
  );
}
