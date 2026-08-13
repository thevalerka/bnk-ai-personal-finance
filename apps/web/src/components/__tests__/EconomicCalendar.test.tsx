import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EconomicCalendar } from "../EconomicCalendar";
import { fetchCalendar } from "@/lib/market";

vi.mock("@/lib/market", () => ({
  fetchCalendar: vi.fn(),
}));

const mockedFetchCalendar = vi.mocked(fetchCalendar);

describe("EconomicCalendar", () => {
  it("renders upcoming events", async () => {
    mockedFetchCalendar.mockResolvedValue([
      {
        ts: "2026-01-15T00:00:00Z",
        kind: "earnings",
        importance: 2,
        title: "AAPL earnings (Q1 2026)",
        source: "finnhub",
        tickers: ["AAPL"],
        topics: [],
      },
    ]);

    render(await EconomicCalendar());

    expect(screen.getByText("AAPL earnings (Q1 2026)")).toBeInTheDocument();
  });

  it("shows an unavailable message when no calendar source is reachable", async () => {
    mockedFetchCalendar.mockResolvedValue(null);

    render(await EconomicCalendar());

    expect(screen.getByText(/calendar unavailable/i)).toBeInTheDocument();
  });
});
