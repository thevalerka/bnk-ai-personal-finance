import Link from "next/link";
import { fetchCandles, fetchMarketGraph, fetchQuote, type MarketGraphNode } from "@/lib/market";
import { DeltaLabel, formatPrice } from "./QuoteGrid";
import { CandleChart } from "./CandleChart";
import { Unavailable } from "./Block";
import styles from "./SpyChart.module.css";
import candleChartStyles from "./CandleChart.module.css";

const DRIVER_COUNT = 5;

function DriversStrip({ nodes }: { nodes: MarketGraphNode[] }) {
  const top = nodes.filter((n) => n.id !== "SPY").slice(0, DRIVER_COUNT);
  if (top.length === 0) return null;

  return (
    <div className={candleChartStyles.driversRow}>
      <span className={candleChartStyles.driversLabel}>Today&apos;s drivers:</span>
      {top.map((node) => {
        const trendClass =
          node.change_pct === null || node.change_pct === undefined
            ? ""
            : node.change_pct > 0
              ? candleChartStyles.driverChipUp
              : node.change_pct < 0
                ? candleChartStyles.driverChipDown
                : "";
        const label =
          node.change_pct === null || node.change_pct === undefined
            ? node.label
            : `${node.label} ${node.change_pct > 0 ? "▲" : node.change_pct < 0 ? "▼" : "•"} ${Math.abs(node.change_pct).toFixed(2)}%`;

        if (node.asset_class === "equity") {
          return (
            <Link
              key={node.id}
              href={`/stock/${node.symbol}`}
              className={`${candleChartStyles.driverChip} ${trendClass}`}
              title={`Rank #${node.rank} today — view ${node.symbol}`}
            >
              {label}
            </Link>
          );
        }
        return (
          <a
            key={node.id}
            href="#market-graph"
            className={`${candleChartStyles.driverChip} ${trendClass}`}
            title={`Rank #${node.rank} today — see it in the Market Drivers graph`}
          >
            {label}
          </a>
        );
      })}
    </div>
  );
}

// First thing a visitor sees (user request) — the broad market's own
// benchmark, not a curated symbol list. Same fetchQuote/fetchCandles calls
// QuoteGrid already makes for SPY (Tape row) — zero new backend for the
// price header. The candle chart itself (CandleChart.tsx) is a client
// component: this stays a server component so the first paint is already
// populated with real daily candles, and the driver strip below the chart
// comes from the same /market/graph snapshot the standalone MarketGraph
// panel renders in full (docs/DECISIONS.md ADR-0031).
export async function SpyChart() {
  const [quotes, candles, graph] = await Promise.all([
    fetchQuote("equity_quote", ["SPY"]),
    fetchCandles("equity_candles", "SPY", "1d", 90),
    fetchMarketGraph(),
  ]);

  const quote = quotes?.[0];

  return (
    <div className={styles.wrap}>
      <div className={styles.header}>
        <span className={styles.symbol}>SPY</span>
        {quote ? (
          <div className={styles.priceRow}>
            <span className={styles.price}>{formatPrice(quote.price)}</span>
            <DeltaLabel quote={quote} />
          </div>
        ) : (
          <span className={styles.symbol}>—</span>
        )}
      </div>
      {candles && candles.length > 1 ? (
        <CandleChart symbol="SPY" capability="equity_candles" initialCandles={candles} />
      ) : (
        <Unavailable reason="SPY price history unavailable — no provider reachable." />
      )}
      {graph ? <DriversStrip nodes={graph.nodes} /> : null}
    </div>
  );
}
