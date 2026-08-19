import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarketGraphChart } from "../MarketGraphChart";
import type { MarketGraphSnapshot } from "@/lib/market";

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
    {
      id: "DGS10",
      label: "10Y Treasury",
      asset_class: "rates",
      symbol: "DGS10",
      last_price: 4.1,
      change_pct: -0.5,
      dominance_score: 0.4,
      rank: 2,
    },
    {
      id: "NEWS_FLOW",
      label: "Breaking News",
      asset_class: "news",
      symbol: "NEWS_FLOW",
      last_price: null,
      change_pct: null,
      dominance_score: 0.3,
      rank: 3,
    },
  ],
  edges: [
    { source: "SPY", target: "DGS10", weight: 0.6, kind: "lead_lag" },
    { source: "NEWS_FLOW", target: "SPY", weight: 0.8, kind: "news" },
  ],
};

describe("MarketGraphChart", () => {
  it("renders one interactive node per graph node", () => {
    render(<MarketGraphChart snapshot={snapshot} />);

    expect(screen.getByRole("img", { name: /market drivers graph/i })).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(3);
  });

  it("clicking a node opens a popup with its rank, today's move, and outgoing edges", () => {
    render(<MarketGraphChart snapshot={snapshot} />);

    fireEvent.click(screen.getByRole("button", { name: /S&P 500 \(SPY\)/i }));

    expect(screen.getByRole("dialog", { name: /S&P 500 \(SPY\) details/i })).toBeInTheDocument();
    expect(screen.getByText(/leads \(next-day\)/i)).toBeInTheDocument();
    expect(screen.getByText("10Y Treasury")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /view spy details/i })).toHaveAttribute("href", "/stock/SPY");
  });

  it("a non-equity node's popup has no stock detail link", () => {
    render(<MarketGraphChart snapshot={snapshot} />);

    fireEvent.click(screen.getByRole("button", { name: /10Y Treasury/i }));

    expect(screen.getByRole("dialog", { name: /10Y Treasury details/i })).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("closing the popup via its close button removes the dialog", () => {
    render(<MarketGraphChart snapshot={snapshot} />);

    fireEvent.click(screen.getByRole("button", { name: /S&P 500 \(SPY\)/i }));
    fireEvent.click(screen.getByRole("button", { name: /close/i }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
