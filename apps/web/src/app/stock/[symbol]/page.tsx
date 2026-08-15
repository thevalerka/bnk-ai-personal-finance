import Link from "next/link";
import { Shell } from "@/components/Shell";
import { Unavailable } from "@/components/Block";
import { DeltaLabel, formatPrice } from "@/components/QuoteGrid";
import { PriceHistoryChart } from "@/components/PriceHistoryChart";
import { CompanyFinancials } from "@/components/CompanyFinancials";
import { fetchStockDetail, type NewsItem } from "@/lib/market";
import newsStyles from "@/components/NewsList.module.css";
import styles from "@/app/detail.module.css";

// .source's CSS only capitalizes the first letter of the whole string
// (text-transform: capitalize doesn't split on "_") — "sec_edgar" rendered
// as "Sec_edgar" until this replaces underscores with spaces first.
function formatSource(source: string): string {
  return source.replace(/_/g, " ");
}

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diffMs / 60_000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function ItemList({ items }: { items: NewsItem[] }) {
  return (
    <ul className={newsStyles.list}>
      {items.map((item) => (
        <li key={item.id} className={newsStyles.item}>
          <a href={item.url} target="_blank" rel="noreferrer" className={newsStyles.headline}>
            {item.headline}
            <svg className={newsStyles.linkIcon} width="11" height="11" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path
                d="M7 17 17 7M17 7H9m8 0v8"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </a>
          <div className={newsStyles.meta}>
            <span className={newsStyles.source}>{formatSource(item.source)}</span>
            <span>{relativeTime(item.ts)}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}

export default async function StockDetailPage({
  params,
}: {
  params: Promise<{ symbol: string }>;
}) {
  const { symbol: rawSymbol } = await params;
  const symbol = rawSymbol.toUpperCase();
  const detail = await fetchStockDetail(symbol);

  return (
    <main className={styles.main}>
      <Shell />
      <div className={styles.page}>
        <Link href="/" className={styles.back}>
          ← Back to dashboard
        </Link>

        <header className={styles.header}>
          <span className={styles.title}>{symbol}</span>
          {detail?.quote ? (
            <div className={styles.priceRow}>
              <span className={styles.price}>{formatPrice(detail.quote.price)}</span>
              <DeltaLabel quote={detail.quote} />
            </div>
          ) : (
            <Unavailable reason="Quote unavailable — no provider reachable." />
          )}
        </header>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Price History</h2>
          {detail && detail.candles.length > 1 ? (
            <PriceHistoryChart candles={detail.candles} />
          ) : (
            <Unavailable reason="Price history unavailable — no provider reachable." />
          )}
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Financials</h2>
          {detail && detail.financials.length > 0 ? (
            <CompanyFinancials periods={detail.financials} />
          ) : (
            <>
              <Unavailable reason="No financial statement data tracked for this ticker." />
              <p className={styles.sectionNote}>
                Financials come from the same curated ticker set as SEC filings
                (docs/DECISIONS.md ADR-0021) — this isn&apos;t necessarily an
                outage, {symbol} may just be outside that set.
              </p>
            </>
          )}
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>SEC Filings</h2>
          {detail && detail.filings.length > 0 ? (
            <ItemList items={detail.filings.slice(0, 15)} />
          ) : (
            <>
              <Unavailable reason="No SEC filings tracked for this ticker." />
              <p className={styles.sectionNote}>
                Filings are only wired up for a curated set of tickers today
                (docs/DECISIONS.md ADR-0019) — this isn&apos;t necessarily an
                outage, {symbol} may just be outside that set.
              </p>
            </>
          )}
        </section>

        <section className={styles.section}>
          <h2 className={styles.sectionTitle}>Recent News</h2>
          {detail && detail.news.length > 0 ? (
            <ItemList items={detail.news.slice(0, 10)} />
          ) : (
            <Unavailable reason="No recent company news reachable." />
          )}
        </section>
      </div>
    </main>
  );
}
