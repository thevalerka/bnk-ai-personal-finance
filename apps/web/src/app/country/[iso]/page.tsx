import Link from "next/link";
import { Shell } from "@/components/Shell";
import { Unavailable } from "@/components/Block";
import { DeltaLabel, formatPrice } from "@/components/QuoteGrid";
import { PriceHistoryChart } from "@/components/PriceHistoryChart";
import { YieldCurve } from "@/components/YieldCurve";
import { fetchWorldIndices, fetchCandles, type WorldIndexPoint } from "@/lib/market";
import detailStyles from "@/app/detail.module.css";
import styles from "./page.module.css";

// US Treasury is the only full yield curve this stack can reach (FRED's
// daily tenor series are US-only) — every other country falls back to the
// single OECD long-term benchmark point already used in the World Map
// popup (docs/DECISIONS.md ADR-0016), when FRED has one at all.
const US_ISO = "840";

function hasQuote(
  point: WorldIndexPoint,
): point is WorldIndexPoint & { quote: NonNullable<WorldIndexPoint["quote"]> } {
  return point.quote !== null;
}

export default async function CountryDetailPage({
  params,
}: {
  params: Promise<{ iso: string }>;
}) {
  const { iso } = await params;
  const points = await fetchWorldIndices();
  const country = points?.find((p) => p.iso_numeric === iso) ?? null;

  if (!points || !country) {
    return (
      <main className={detailStyles.main}>
        <Shell />
        <div className={detailStyles.page}>
          <Link href="/" className={detailStyles.back}>
            ← Back to dashboard
          </Link>
          <Unavailable reason="Country not found or not tracked." />
        </div>
      </main>
    );
  }

  const candles = country.quote
    ? await fetchCandles("equity_candles", country.symbol, "1d", 180)
    : null;

  const otherIndices = points
    .filter(hasQuote)
    .sort((a, b) => (b.quote.change_percent ?? 0) - (a.quote.change_percent ?? 0));

  return (
    <main className={detailStyles.main}>
      <Shell />
      <div className={detailStyles.page}>
        <Link href="/" className={detailStyles.back}>
          ← Back to dashboard
        </Link>

        <header className={detailStyles.header}>
          <span className={detailStyles.title}>{country.name}</span>
          {country.quote ? (
            <div className={detailStyles.priceRow}>
              <span className={detailStyles.price}>{formatPrice(country.quote.price)}</span>
              <DeltaLabel quote={country.quote} />
            </div>
          ) : (
            <Unavailable reason="Index quote unavailable — no provider reachable." />
          )}
        </header>

        <section className={detailStyles.section}>
          <h2 className={detailStyles.sectionTitle}>Index Price History</h2>
          {candles && candles.length > 1 ? (
            <PriceHistoryChart candles={candles} />
          ) : (
            <>
              <Unavailable reason="Price history unavailable — no provider reachable." />
              <p className={detailStyles.sectionNote}>
                Index level is proxied by {country.symbol}, {country.name}&apos;s largest
                US-listed single-country ETF (docs/DECISIONS.md ADR-0015) — no per-country
                index-level provider is wired.
              </p>
            </>
          )}
        </section>

        <section className={detailStyles.section}>
          <h2 className={detailStyles.sectionTitle}>Currency vs USD</h2>
          {country.fx_label ? (
            <p className={styles.fxValue}>{country.fx_label}</p>
          ) : (
            <Unavailable reason="No FX rate tracked for this currency." />
          )}
        </section>

        <section className={detailStyles.section}>
          <h2 className={detailStyles.sectionTitle}>
            {iso === US_ISO ? "US Treasury Yield Curve" : "Government Bond Yield"}
          </h2>
          {iso === US_ISO ? (
            <YieldCurve />
          ) : country.bond_yield_pct !== null ? (
            <p className={styles.yieldValue}>
              {country.bond_yield_pct.toFixed(2)}%
              <span className={styles.yieldNote}>~10Y benchmark, OECD via FRED</span>
            </p>
          ) : (
            <>
              <Unavailable reason="No government bond yield tracked for this country." />
              <p className={detailStyles.sectionNote}>
                FRED mirrors OECD long-term benchmark yields for a subset of countries
                (docs/DECISIONS.md ADR-0016) — {country.name} isn&apos;t one of them.
              </p>
            </>
          )}
        </section>

        <section className={detailStyles.section}>
          <h2 className={detailStyles.sectionTitle}>Main World Indices</h2>
          <ul className={styles.indexList}>
            {otherIndices.map((point) => (
              <li
                key={point.iso_numeric}
                className={point.iso_numeric === iso ? styles.indexRowActive : styles.indexRow}
              >
                <Link href={`/country/${point.iso_numeric}`} className={styles.indexName}>
                  {point.name} ({point.symbol})
                </Link>
                <div className={styles.indexRight}>
                  <span className={styles.indexPrice}>{formatPrice(point.quote.price)}</span>
                  <DeltaLabel quote={point.quote} />
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </main>
  );
}
