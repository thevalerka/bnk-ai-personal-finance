import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MarketGraph } from "../MarketGraph";
import { fetchMarketGraph, type MarketGraphSnapshot } from "@/lib/market";

vi.mock("@/lib/market", () => ({
  fetchMarketGraph: vi.fn(),
}));

const mockedFetchMarketGraph = vi.mocked(fetchMarketGraph);

const snapshot: MarketGraphSnapshot = {
  computed_at: "2026-08-19T12:00:00Z",
  nodes: [
    {
      id: "SPY",
      label: "S&P 500 (SPY)",
      asset_class: "equity",
      symbol: "SPY",
      last_price: 561.23,
      change_pct: 1.2,
      dominance_score: 0.9,
      rank: 1,
    },
  ],
  edges: [],
};

describe("MarketGraph", () => {
  it("renders the graph chart when a snapshot is reachable", async () => {
    mockedFetchMarketGraph.mockResolvedValue(snapshot);

    render(await MarketGraph());

    expect(screen.getByRole("img", { name: /market drivers graph/i })).toBeInTheDocument();
  });

  it("shows an unavailable message when the graph is unreachable", async () => {
    mockedFetchMarketGraph.mockResolvedValue(null);

    render(await MarketGraph());

    expect(screen.getByText(/market drivers graph unavailable/i)).toBeInTheDocument();
  });

  it("shows an unavailable message when the graph has no nodes yet", async () => {
    mockedFetchMarketGraph.mockResolvedValue({ ...snapshot, nodes: [] });

    render(await MarketGraph());

    expect(screen.getByText(/market drivers graph unavailable/i)).toBeInTheDocument();
  });
});
