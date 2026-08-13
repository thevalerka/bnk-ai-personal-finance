import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { YieldCurve } from "../YieldCurve";
import { fetchQuote } from "@/lib/market";

vi.mock("@/lib/market", () => ({
  fetchQuote: vi.fn(),
}));

const mockedFetchQuote = vi.mocked(fetchQuote);

describe("YieldCurve", () => {
  it("plots a point per reachable tenor and direct-labels the last one", async () => {
    mockedFetchQuote.mockResolvedValue([
      { symbol: "DGS1", price: 4.5, ts: "2026-01-01", change: null, change_percent: null, source: "fred" },
      { symbol: "DGS10", price: 4.2, ts: "2026-01-01", change: null, change_percent: null, source: "fred" },
      { symbol: "DGS30", price: 4.4, ts: "2026-01-01", change: null, change_percent: null, source: "fred" },
    ]);

    const { container } = render(await YieldCurve());

    expect(container.querySelectorAll("circle")).toHaveLength(3);
    expect(screen.getByText("4.40%")).toBeInTheDocument();
  });

  it("shows an unavailable message when FRED can't be reached", async () => {
    mockedFetchQuote.mockResolvedValue(null);

    render(await YieldCurve());

    expect(screen.getByText(/yield curve unavailable/i)).toBeInTheDocument();
  });
});
