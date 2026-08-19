import { fetchMarketGraph } from "@/lib/market";
import { Unavailable } from "./Block";
import { MarketHeatmap } from "./MarketHeatmap";

// The "20 main nodes of the moment" (user request) — a treemap heatmap over
// the cross-asset universe this app already has real data for: block size
// is dominance, block position clusters correlated instruments, color is
// change over the selected timeframe, and a translucent fill gauge is
// recent volatility vs. this node's own 1-year norm (docs/DECISIONS.md
// ADR-0031/0032). Server component fetches the (server-side cached, 15min)
// daily snapshot for first paint; MarketHeatmap.tsx does the client-side
// layout + timeframe switching, same split as WorldMap.tsx/WorldMapChart.tsx
// and SpyChart.tsx/CandleChart.tsx.
export async function MarketGraph() {
  const snapshot = await fetchMarketGraph();

  if (!snapshot || snapshot.nodes.length === 0) {
    return <Unavailable reason="Market drivers graph unavailable — not enough live data reachable yet." />;
  }

  return <MarketHeatmap initialSnapshot={snapshot} />;
}
