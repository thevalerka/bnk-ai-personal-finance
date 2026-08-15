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

  it("renders an auction event with its own kind label, distinct from earnings/macro", async () => {
    mockedFetchCalendar.mockResolvedValue([
      {
        ts: "2026-08-19T00:00:00Z",
        kind: "auction",
        importance: 1,
        title: "20-Year Bond auction",
        source: "treasury",
        tickers: ["912810UX4"],
        topics: [],
      },
    ]);

    render(await EconomicCalendar());

    expect(screen.getByText("20-Year Bond auction")).toBeInTheDocument();
    expect(screen.getByText("auction")).toBeInTheDocument();
  });

  it("reserves visible slots for non-earnings kinds instead of letting a large same-day earnings batch bury them", async () => {
    const earningsFlood = Array.from({ length: 20 }, (_, i) => ({
      ts: "2026-08-14T00:00:00Z",
      kind: "earnings",
      importance: 2,
      title: `TICK${i} earnings (2Q2026)`,
      source: "finnhub",
      tickers: [`TICK${i}`],
      topics: [],
    }));
    mockedFetchCalendar.mockResolvedValue([
      ...earningsFlood,
      {
        ts: "2026-08-19T00:00:00Z",
        kind: "auction",
        importance: 1,
        title: "20-Year Bond auction",
        source: "treasury",
        tickers: ["912810UX4"],
        topics: [],
      },
    ]);

    render(await EconomicCalendar());

    expect(screen.getByText("20-Year Bond auction")).toBeInTheDocument();
  });

  it("shows an unavailable message when no calendar source is reachable", async () => {
    mockedFetchCalendar.mockResolvedValue(null);

    render(await EconomicCalendar());

    expect(screen.getByText(/calendar unavailable/i)).toBeInTheDocument();
  });
});
