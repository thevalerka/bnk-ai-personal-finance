import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Heatmap } from "../Heatmap";
import { fetchQuote } from "@/lib/market";

vi.mock("@/lib/market", () => ({
  fetchQuote: vi.fn(),
}));

const mockedFetchQuote = vi.mocked(fetchQuote);

describe("Heatmap", () => {
  it("renders a cell per reachable symbol with its change percent", async () => {
    mockedFetchQuote.mockResolvedValue([
      { symbol: "XLK", price: 200, ts: "2026-01-01", change: null, change_percent: 1.5, source: "finnhub" },
      { symbol: "XLE", price: 90, ts: "2026-01-01", change: null, change_percent: -0.8, source: "finnhub" },
    ]);

    render(await Heatmap());

    expect(screen.getByText("XLK")).toBeInTheDocument();
    expect(screen.getByText("+1.5%")).toBeInTheDocument();
    expect(screen.getByText("-0.8%")).toBeInTheDocument();
  });

  it("shows an unavailable message when no equity quotes are reachable", async () => {
    mockedFetchQuote.mockResolvedValue(null);

    render(await Heatmap());

    expect(screen.getByText(/heatmap unavailable/i)).toBeInTheDocument();
  });
});
