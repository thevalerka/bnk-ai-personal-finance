import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MarketOverview } from "../MarketOverview";
import { fetchPredictions, fetchQuote } from "@/lib/market";

vi.mock("@/lib/market", () => ({
  fetchQuote: vi.fn(),
  fetchPredictions: vi.fn(),
}));

const mockedFetchQuote = vi.mocked(fetchQuote);
const mockedFetchPredictions = vi.mocked(fetchPredictions);

function isoIn(hours: number): string {
  return new Date(Date.now() + hours * 60 * 60 * 1000).toISOString();
}

describe("MarketOverview", () => {
  it("shows market status quotes, the top prediction, and breaking Polymarket odds", async () => {
    mockedFetchQuote.mockImplementation(async (capability) =>
      capability === "crypto_quote"
        ? [{ symbol: "BTC", price: 61000, ts: "2026-08-18", change: 100, change_percent: 0.2, source: "alpaca" }]
        : [
            { symbol: "SPY", price: 561.23, ts: "2026-08-18", change: 3.1, change_percent: 0.55, source: "finnhub" },
            { symbol: "QQQ", price: 480.1, ts: "2026-08-18", change: -1.2, change_percent: -0.25, source: "finnhub" },
            { symbol: "DIA", price: 400.5, ts: "2026-08-18", change: 0.5, change_percent: 0.1, source: "finnhub" },
          ],
    );
    mockedFetchPredictions.mockResolvedValue([
      {
        question: "Will the Fed cut rates this week?",
        probability_pct: 62,
        volume_24h: 500000,
        end_date: isoIn(6),
        url: "https://polymarket.com/event/fed-this-week",
        source: "polymarket",
      },
      {
        question: "Will the S&P close green today?",
        probability_pct: 55,
        volume_24h: 120000,
        end_date: isoIn(24 * 30),
        url: "https://polymarket.com/event/spx-today",
        source: "polymarket",
      },
    ]);

    render(await MarketOverview());

    expect(screen.getByText("Market status")).toBeInTheDocument();
    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getByText("BTC")).toBeInTheDocument();
    expect(screen.getByText("Top prediction")).toBeInTheDocument();
    // Renders twice: PredictionOfDay's own pick (only market due within 24h)
    // and again in the Breaking list (which isn't date-filtered).
    expect(screen.getAllByText("Will the Fed cut rates this week?")).toHaveLength(2);
    expect(screen.getByText("Breaking · Polymarket")).toBeInTheDocument();
    expect(screen.getByText("Will the S&P close green today?")).toBeInTheDocument();
  });

  it("degrades each section independently when its own data is unreachable", async () => {
    mockedFetchQuote.mockResolvedValue(null);
    mockedFetchPredictions.mockResolvedValue(null);

    render(await MarketOverview());

    expect(screen.getByText(/no live quotes reachable/i)).toBeInTheDocument();
    // Appears twice: PredictionOfDay's own degrade (Top prediction) and
    // MarketOverview's own Breaking section, each with an independent fetch.
    expect(screen.getAllByText(/no prediction markets reachable/i)).toHaveLength(2);
  });
});
