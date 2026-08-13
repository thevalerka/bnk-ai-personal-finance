import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { QuoteGrid } from "../QuoteGrid";
import { fetchCandles, fetchQuote } from "@/lib/market";

vi.mock("@/lib/market", () => ({
  fetchQuote: vi.fn(),
  fetchCandles: vi.fn(),
}));

const mockedFetchQuote = vi.mocked(fetchQuote);
const mockedFetchCandles = vi.mocked(fetchCandles);

describe("QuoteGrid", () => {
  it("renders a live price and change for a reachable symbol", async () => {
    mockedFetchQuote.mockResolvedValue([
      { symbol: "SPY", price: 512.34, ts: "2026-01-01T00:00:00Z", change: 1.2, change_percent: 0.23, source: "finnhub" },
    ]);
    mockedFetchCandles.mockResolvedValue(null);

    const element = await QuoteGrid({ groups: [{ capability: "equity_quote", symbols: ["SPY"] }] });
    render(element);

    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getByText("512.34")).toBeInTheDocument();
  });

  it("shows 'unavailable' instead of a fabricated number when the provider chain fails", async () => {
    mockedFetchQuote.mockResolvedValue(null);
    mockedFetchCandles.mockResolvedValue(null);

    const element = await QuoteGrid({ groups: [{ capability: "equity_quote", symbols: ["SPY"] }] });
    render(element);

    expect(screen.getByText(/no live quotes reachable/i)).toBeInTheDocument();
    expect(screen.queryByText("512.34")).not.toBeInTheDocument();
  });

  it("marks an individual symbol as unavailable when only some symbols come back", async () => {
    mockedFetchQuote.mockResolvedValue([
      { symbol: "SPY", price: 512.34, ts: "2026-01-01T00:00:00Z", change: 1.2, change_percent: 0.23, source: "finnhub" },
    ]);
    mockedFetchCandles.mockResolvedValue(null);

    const element = await QuoteGrid({
      groups: [{ capability: "equity_quote", symbols: ["SPY", "QQQ"] }],
    });
    render(element);

    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getByText("QQQ")).toBeInTheDocument();
    expect(screen.getByText("unavailable")).toBeInTheDocument();
  });
});
