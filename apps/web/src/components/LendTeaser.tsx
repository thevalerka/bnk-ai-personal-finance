import Link from "next/link";
import { fetchLendTokensTeaser } from "@/lib/market";
import { Unavailable } from "./Block";
import styles from "./PredictionMarkets.module.css";

// Read-only dashboard teaser for the full deposit UI on /lend
// (docs/DECISIONS.md ADR-0029) — real current Jupiter Lend supply APYs,
// not a static/aggregated figure.
export async function LendTeaser() {
  const tokens = await fetchLendTokensTeaser();

  if (!tokens || tokens.length === 0) {
    return <Unavailable reason="No stablecoin lend vaults reachable right now." />;
  }

  return (
    <div>
      <ul className={styles.list}>
        {tokens.map((t) => (
          <li key={t.symbol} className={styles.item}>
            <div className={styles.row}>
              <span className={styles.question}>{t.symbol} lending APY</span>
              <span className={`${styles.probability} ${styles.probabilityHigh}`}>
                {t.supply_apy_pct.toFixed(2)}%
              </span>
            </div>
          </li>
        ))}
      </ul>
      <Link href="/lend" className={styles.question}>
        View stablecoin lending →
      </Link>
    </div>
  );
}
