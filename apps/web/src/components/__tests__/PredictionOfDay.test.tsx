import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PredictionOfDay } from "../PredictionOfDay";
import { fetchPredictions } from "@/lib/market";

vi.mock("@/lib/market", () => ({
  fetchPredictions: vi.fn(),
}));

const mockedFetchPredictions = vi.mocked(fetchPredictions);

function isoIn(hours: number): string {
  return new Date(Date.now() + hours * 60 * 60 * 1000).toISOString();
}

describe("PredictionOfDay", () => {
  it("picks the highest-volume market that resolves within 24h", async () => {
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
        question: "Will the Fed hold rates in September?",
        probability_pct: 74.5,
        volume_24h: 900000,
        end_date: isoIn(24 * 30),
        url: "https://polymarket.com/event/fed-september",
        source: "polymarket",
      },
    ]);

    render(await PredictionOfDay());

    expect(screen.getByText("Will the Fed cut rates this week?")).toBeInTheDocument();
    expect(screen.getByText("62%")).toBeInTheDocument();
    expect(screen.getByText("Resolves today")).toBeInTheDocument();
  });

  it("shows an unavailable message rather than a market that isn't due today", async () => {
    mockedFetchPredictions.mockResolvedValue([
      {
        question: "Will the Fed hold rates in September?",
        probability_pct: 74.5,
        volume_24h: 900000,
        end_date: isoIn(24 * 30),
        url: "https://polymarket.com/event/fed-september",
        source: "polymarket",
      },
    ]);

    render(await PredictionOfDay());

    expect(screen.getByText(/resolves in the next 24 hours/i)).toBeInTheDocument();
  });

  it("shows an unavailable message rather than a fabricated market when the provider is down", async () => {
    mockedFetchPredictions.mockResolvedValue(null);

    render(await PredictionOfDay());

    expect(screen.getByText(/no prediction markets reachable/i)).toBeInTheDocument();
  });
});
