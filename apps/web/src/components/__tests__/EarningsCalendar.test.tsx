import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EarningsCalendar } from "../EarningsCalendar";
import { fetchEarningsCalendar } from "@/lib/market";

vi.mock("@/lib/market", () => ({
  fetchEarningsCalendar: vi.fn(),
}));

const mockedFetch = vi.mocked(fetchEarningsCalendar);

describe("EarningsCalendar", () => {
  it("renders a ticker, EPS estimate, and beat probability grouped by report date", async () => {
    mockedFetch.mockResolvedValue([
      {
        ticker: "HD",
        company: "Home Depot",
        eps_estimate: "$4.73",
        probability_pct: 76.5,
        volume: 3763,
        report_date: "2026-08-18T13:00:00Z",
        url: "https://polymarket.com/event/hd-earnings",
        source: "polymarket",
      },
      {
        ticker: "TGT",
        company: "Target",
        eps_estimate: "$2.28",
        probability_pct: 88.5,
        volume: 1861,
        report_date: "2026-08-19T13:00:00Z",
        url: "https://polymarket.com/event/tgt-earnings",
        source: "polymarket",
      },
    ]);

    render(await EarningsCalendar());

    expect(screen.getByText("HD")).toBeInTheDocument();
    expect(screen.getByText("est. $4.73")).toBeInTheDocument();
    expect(screen.getByText("77%")).toBeInTheDocument();
    expect(screen.getByText("TGT")).toBeInTheDocument();
  });

  it("skips markets with no parseable report date rather than crashing", async () => {
    mockedFetch.mockResolvedValue([
      {
        ticker: "XYZ",
        company: "Unknown Co",
        eps_estimate: null,
        probability_pct: 50,
        volume: 0,
        report_date: null,
        url: "https://polymarket.com/event/xyz",
        source: "polymarket",
      },
    ]);

    render(await EarningsCalendar());

    expect(screen.queryByText("XYZ")).not.toBeInTheDocument();
  });

  it("shows an unavailable message rather than a fabricated calendar when the provider is down", async () => {
    mockedFetch.mockResolvedValue(null);

    render(await EarningsCalendar());

    expect(screen.getByText(/no earnings markets reachable/i)).toBeInTheDocument();
  });
});
