import { Suspense } from "react";
import { Shell } from "@/components/Shell";
import { Tape } from "@/components/Tape";
import { Block, BlockSkeleton } from "@/components/Block";
import { PanelSlot } from "@/components/PanelSlot";
import { DynamicGrid } from "@/components/DynamicGrid";
import { QuoteGrid, type QuoteGroup } from "@/components/QuoteGrid";
import { YieldCurve } from "@/components/YieldCurve";
import { Heatmap } from "@/components/Heatmap";
import { NewsList } from "@/components/NewsList";
import { EconomicCalendar } from "@/components/EconomicCalendar";
import { SpyChart } from "@/components/SpyChart";
import { MarketOverview } from "@/components/MarketOverview";
import { Forex } from "@/components/Forex";
import { PredictionMarkets } from "@/components/PredictionMarkets";
import { EarningsCalendar } from "@/components/EarningsCalendar";
import { MarketGraph } from "@/components/MarketGraph";
import { XStocksTeaser } from "@/components/XStocksTeaser";
import { LendTeaser } from "@/components/LendTeaser";
import styles from "./page.module.css";

const TAPE_GROUPS: QuoteGroup[] = [
  { capability: "equity_quote", candleCapability: "equity_candles", symbols: ["SPY", "QQQ"] },
  { capability: "crypto_quote", candleCapability: "crypto_candles", symbols: ["BTC"] },
];

// Curated by trailing 12-month average daily volume rather than a live
// screener — no free-tier provider here offers a "most active" ranking
// endpoint, and a fixed list still renders every price/delta from a real
// quote (CLAUDE.md non-negotiable), it's just not re-ranked intraday.
const MOST_TRADED_GROUPS: QuoteGroup[] = [
  {
    capability: "equity_quote",
    candleCapability: "equity_candles",
    symbols: ["NVDA", "AAPL", "TSLA", "AMD", "AMZN", "MSFT", "META", "GOOGL", "PLTR", "SOFI"],
  },
];

export default function Home() {
  return (
    <main className={styles.main}>
      <Shell />
      <Suspense fallback={null}>
        <Tape />
      </Suspense>

      <div className={styles.dashboard}>
        <PanelSlot id="spy_chart" title="SPY" spanClassName={styles.spyChart}>
          <Suspense fallback={<BlockSkeleton title="SPY" minHeight={340} />}>
            <Block id="spy_chart" title="SPY">
              <SpyChart />
            </Block>
          </Suspense>
        </PanelSlot>

        <PanelSlot
          id="earnings_calendar"
          title="Earnings Calendar"
          spanClassName={styles.earningsCalendar}
        >
          <Suspense fallback={<BlockSkeleton title="Earnings Calendar" minHeight={340} />}>
            <Block id="earnings_calendar" title="Earnings Calendar" source="Polymarket">
              <EarningsCalendar />
            </Block>
          </Suspense>
        </PanelSlot>

        <PanelSlot id="market_overview" title="Market Overview" spanClassName={styles.marketOverview}>
          <Suspense fallback={<BlockSkeleton title="Market Overview" minHeight={340} />}>
            <Block id="market_overview" title="Market Overview" source="Polymarket">
              <MarketOverview />
            </Block>
          </Suspense>
        </PanelSlot>

        <PanelSlot id="market_graph" title="Market Drivers" spanClassName={styles.marketGraph} anchorId="market-graph">
          <Suspense fallback={<BlockSkeleton title="Market Drivers" minHeight={420} />}>
            <Block id="market_graph" title="Market Drivers" source="Computed">
              <MarketGraph />
            </Block>
          </Suspense>
        </PanelSlot>

        <DynamicGrid
          quotes={
            <Suspense fallback={<BlockSkeleton title="Quotes" minHeight={180} />}>
              <Block id="quotes" title="Quotes">
                <QuoteGrid groups={TAPE_GROUPS} />
              </Block>
            </Suspense>
          }
          yieldCurve={
            <Suspense fallback={<BlockSkeleton title="US Treasury Yield Curve" minHeight={220} />}>
              <Block id="yield_curve" title="US Treasury Yield Curve" source="FRED">
                <YieldCurve />
              </Block>
            </Suspense>
          }
          heatmap={
            <Suspense fallback={<BlockSkeleton title="Sector Heatmap" minHeight={180} />}>
              <Block id="heatmap" title="Sector Heatmap">
                <Heatmap />
              </Block>
            </Suspense>
          }
        />

        <PanelSlot id="news" title="News" spanClassName={styles.newsList}>
          <Suspense fallback={<BlockSkeleton title="News" minHeight={300} />}>
            <Block id="news" title="News">
              <NewsList />
            </Block>
          </Suspense>
        </PanelSlot>

        <PanelSlot id="calendar" title="Calendar" spanClassName={styles.calendar}>
          <Suspense fallback={<BlockSkeleton title="Calendar" minHeight={300} />}>
            <Block id="calendar" title="Calendar">
              <EconomicCalendar />
            </Block>
          </Suspense>
        </PanelSlot>

        <PanelSlot id="most_traded" title="Most Traded" spanClassName={styles.mostTraded}>
          <Suspense fallback={<BlockSkeleton title="Most Traded" minHeight={180} />}>
            <Block id="most_traded" title="Most Traded">
              <QuoteGrid groups={MOST_TRADED_GROUPS} />
            </Block>
          </Suspense>
        </PanelSlot>

        <PanelSlot id="forex" title="Forex" spanClassName={styles.forex}>
          <Suspense fallback={<BlockSkeleton title="Forex" minHeight={180} />}>
            <Block id="forex" title="Forex" source="FRED H.10">
              <Forex />
            </Block>
          </Suspense>
        </PanelSlot>

        <PanelSlot id="predictions" title="Prediction Markets" spanClassName={styles.predictions}>
          <Suspense fallback={<BlockSkeleton title="Prediction Markets" minHeight={300} />}>
            <Block id="predictions" title="Prediction Markets" source="Polymarket">
              <PredictionMarkets />
            </Block>
          </Suspense>
        </PanelSlot>

        <PanelSlot id="xstocks" title="xStocks" spanClassName={styles.xstocks}>
          <Suspense fallback={<BlockSkeleton title="xStocks" minHeight={260} />}>
            <Block id="xstocks" title="xStocks" source="Jupiter (jup.ag)">
              <XStocksTeaser />
            </Block>
          </Suspense>
        </PanelSlot>

        <PanelSlot id="fixed_income" title="Fixed Income" spanClassName={styles.fixedIncome}>
          <Suspense fallback={<BlockSkeleton title="Fixed Income" minHeight={260} />}>
            <Block id="fixed_income" title="Fixed Income" source="Jupiter Lend">
              <LendTeaser />
            </Block>
          </Suspense>
        </PanelSlot>
      </div>
    </main>
  );
}
