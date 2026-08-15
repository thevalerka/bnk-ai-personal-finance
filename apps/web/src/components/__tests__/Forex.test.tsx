import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Forex } from "../Forex";
import { fetchCandles, fetchQuote } from "@/lib/market";

vi.mock("@/lib/market", () => ({
  fetchQuote: vi.fn(),
  fetchCandles: vi.fn(),
}));

const mockedFetchQuote = vi.mocked(fetchQuote);
const mockedFetchCandles = vi.mocked(fetchCandles);

function candle(close: number) {
  return { symbol: "DEXUSEU", ts: "2026-01-01T00:00:00Z", open: close, high: close, low: close, close, volume: null, source: "fred" };
}

describe("Forex", () => {
  it("renders a pair label and rate, with % change derived from the last two candle closes", async () => {
    mockedFetchQuote.mockResolvedValue([
      { symbol: "DEXUSEU", price: 1.1559, ts: "2026-01-01T00:00:00Z", change: null, change_percent: null, source: "fred" },
    ]);
    mockedFetchCandles.mockImplementation(async (_capability, symbol) =>
      symbol === "DEXUSEU" ? [candle(1.15), candle(1.1559)] : null,
    );

    render(await Forex());

    expect(screen.getByText("EUR/USD")).toBeInTheDocument();
    expect(screen.getByText("1.1559")).toBeInTheDocument();
    // (1.1559 - 1.15) / 1.15 * 100 ≈ 0.51%
    expect(screen.getByText(/0\.51%/)).toBeInTheDocument();
  });

  it("shows 'unavailable' instead of a fabricated rate when no provider is reachable", async () => {
    mockedFetchQuote.mockResolvedValue(null);
    mockedFetchCandles.mockResolvedValue(null);

    render(await Forex());

    expect(screen.getByText(/no live fx rates reachable/i)).toBeInTheDocument();
  });

  it("marks an individual pair unavailable when only some symbols come back", async () => {
    mockedFetchQuote.mockResolvedValue([
      { symbol: "DEXUSEU", price: 1.1559, ts: "2026-01-01T00:00:00Z", change: null, change_percent: null, source: "fred" },
    ]);
    mockedFetchCandles.mockResolvedValue(null);

    render(await Forex());

    expect(screen.getByText("EUR/USD")).toBeInTheDocument();
    expect(screen.getByText("GBP/USD")).toBeInTheDocument();
    expect(screen.getAllByText("unavailable").length).toBeGreaterThan(0);
  });
});
