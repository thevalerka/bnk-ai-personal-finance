import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SpyChart } from "../SpyChart";
import { fetchCandles, fetchMarketGraph, fetchQuote, type MarketGraphSnapshot } from "@/lib/market";

vi.mock("@/lib/market", async () => {
  const actual = await vi.importActual<typeof import("@/lib/market")>("@/lib/market");
  return { ...actual, fetchQuote: vi.fn(), fetchCandles: vi.fn(), fetchMarketGraph: vi.fn() };
});

// CandleChart itself (lightweight-charts + jsdom canvas) is covered by its
// own test — SpyChart's tests are about the price header + driver strip
// composition around it, so the chart is stubbed to a plain marker here.
vi.mock("../CandleChart", () => ({
  CandleChart: ({ symbol }: { symbol: string }) => <div role="img" aria-label={`${symbol} candle chart`} />,
}));

const mockedFetchQuote = vi.mocked(fetchQuote);
const mockedFetchCandles = vi.mocked(fetchCandles);
const mockedFetchMarketGraph = vi.mocked(fetchMarketGraph);

function candle(ts: string, close: number) {
  return { symbol: "SPY", ts, open: close, high: close, low: close, close, volume: 1, source: "alpaca" };
}

const emptyGraph: MarketGraphSnapshot = { computed_at: "2026-08-19T12:00:00Z", nodes: [], edges: [] };

describe("SpyChart", () => {
  it("renders SPY's price, delta, and a candle chart", async () => {
    mockedFetchQuote.mockResolvedValue([
      { symbol: "SPY", price: 561.23, ts: "2026-08-18", change: 3.1, change_percent: 0.55, source: "finnhub" },
    ]);
    mockedFetchCandles.mockResolvedValue([candle("2026-08-01", 555), candle("2026-08-18", 560.5)]);
    mockedFetchMarketGraph.mockResolvedValue(emptyGraph);

    render(await SpyChart());

    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getByText("561.23")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "SPY candle chart" })).toBeInTheDocument();
  });

  it("shows an unavailable message when candles can't be fetched", async () => {
    mockedFetchQuote.mockResolvedValue([
      { symbol: "SPY", price: 561.23, ts: "2026-08-18", change: 3.1, change_percent: 0.55, source: "finnhub" },
    ]);
    mockedFetchCandles.mockResolvedValue(null);
    mockedFetchMarketGraph.mockResolvedValue(emptyGraph);

    render(await SpyChart());

    expect(screen.getByText(/price history unavailable/i)).toBeInTheDocument();
  });

  it("shows a link chip to each of today's top non-SPY drivers", async () => {
    mockedFetchQuote.mockResolvedValue([
      { symbol: "SPY", price: 561.23, ts: "2026-08-18", change: 3.1, change_percent: 0.55, source: "finnhub" },
    ]);
    mockedFetchCandles.mockResolvedValue([candle("2026-08-01", 555), candle("2026-08-18", 560.5)]);
    mockedFetchMarketGraph.mockResolvedValue({
      computed_at: "2026-08-19T12:00:00Z",
      nodes: [
        {
          id: "SPY",
          label: "S&P 500 (SPY)",
          asset_class: "equity",
          symbol: "SPY",
          last_price: 561.23,
          change_pct: 0.55,
          dominance_score: 0.9,
          rank: 1,
        },
        {
          id: "XLK",
          label: "Technology (XLK)",
          asset_class: "equity",
          symbol: "XLK",
          last_price: 240.1,
          change_pct: 2.1,
          dominance_score: 0.8,
          rank: 2,
        },
        {
          id: "DGS10",
          label: "10Y Treasury",
          asset_class: "rates",
          symbol: "DGS10",
          last_price: 4.1,
          change_pct: -0.3,
          dominance_score: 0.6,
          rank: 3,
        },
      ],
      edges: [],
    });

    render(await SpyChart());

    const xlkLink = screen.getByRole("link", { name: /technology \(xlk\)/i });
    expect(xlkLink).toHaveAttribute("href", "/stock/XLK");
    const dgs10Link = screen.getByRole("link", { name: /10y treasury/i });
    expect(dgs10Link).toHaveAttribute("href", "#market-graph");
    expect(screen.queryByRole("link", { name: /s&p 500/i })).not.toBeInTheDocument(); // SPY excludes itself
  });
});
