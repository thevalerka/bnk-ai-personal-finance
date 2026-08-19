import { fetchMarketGraph } from "@/lib/market";
import { Unavailable } from "./Block";
import { MarketGraphChart } from "./MarketGraphChart";

// The "20 main nodes of the moment" (user request) — a graph over the
// cross-asset universe this app already has real data for, with edges from
// correlation/lead-lag/Markov-transition dominance plus real breaking news
// (docs/DECISIONS.md ADR-0031). Server component fetches the (server-side
// cached, 15min) snapshot; MarketGraphChart.tsx does the client-side
// force-layout + interaction, same split as WorldMap.tsx/WorldMapChart.tsx.
export async function MarketGraph() {
  const snapshot = await fetchMarketGraph();

  if (!snapshot || snapshot.nodes.length === 0) {
    return <Unavailable reason="Market drivers graph unavailable — not enough live data reachable yet." />;
  }

  return <MarketGraphChart snapshot={snapshot} />;
}
