import { Suspense } from "react";
import { Shell } from "@/components/Shell";
import { Tape } from "@/components/Tape";
import { Block, BlockSkeleton } from "@/components/Block";
import { QuoteGrid, type QuoteGroup } from "@/components/QuoteGrid";
import { YieldCurve } from "@/components/YieldCurve";
import { Heatmap } from "@/components/Heatmap";
import { NewsList } from "@/components/NewsList";
import { EconomicCalendar } from "@/components/EconomicCalendar";
import styles from "./page.module.css";

const TAPE_GROUPS: QuoteGroup[] = [
  { capability: "equity_quote", candleCapability: "equity_candles", symbols: ["SPY", "QQQ"] },
  { capability: "crypto_quote", candleCapability: "crypto_candles", symbols: ["BTC"] },
];

export default function Home() {
  return (
    <main className={styles.main}>
      <Shell />
      <Suspense fallback={null}>
        <Tape />
      </Suspense>

      <div className={styles.dashboard}>
        <div className={styles.quoteGrid}>
          <Suspense fallback={<BlockSkeleton title="Quotes" minHeight={180} />}>
            <Block title="Quotes">
              <QuoteGrid groups={TAPE_GROUPS} />
            </Block>
          </Suspense>
        </div>

        <div className={styles.yieldCurve}>
          <Suspense fallback={<BlockSkeleton title="US Treasury Yield Curve" minHeight={220} />}>
            <Block title="US Treasury Yield Curve" source="FRED">
              <YieldCurve />
            </Block>
          </Suspense>
        </div>

        <div className={styles.heatmap}>
          <Suspense fallback={<BlockSkeleton title="Sector Heatmap" minHeight={180} />}>
            <Block title="Sector Heatmap">
              <Heatmap />
            </Block>
          </Suspense>
        </div>

        <div className={styles.newsList}>
          <Suspense fallback={<BlockSkeleton title="News" minHeight={300} />}>
            <Block title="News">
              <NewsList />
            </Block>
          </Suspense>
        </div>

        <div className={styles.calendar}>
          <Suspense fallback={<BlockSkeleton title="Calendar" minHeight={300} />}>
            <Block title="Calendar">
              <EconomicCalendar />
            </Block>
          </Suspense>
        </div>
      </div>
    </main>
  );
}
