import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PredictionMarkets } from "../PredictionMarkets";
import { fetchPredictions } from "@/lib/market";

vi.mock("@/lib/market", () => ({
  fetchPredictions: vi.fn(),
}));

const mockedFetchPredictions = vi.mocked(fetchPredictions);

describe("PredictionMarkets", () => {
  it("renders a question, probability, and volume for a reachable market", async () => {
    mockedFetchPredictions.mockResolvedValue([
      {
        question: "Will the Fed hold rates in September?",
        probability_pct: 74.5,
        volume_24h: 310862,
        end_date: "2026-09-16T00:00:00Z",
        url: "https://polymarket.com/event/fed-decision-in-september-762",
        source: "polymarket",
      },
    ]);

    render(await PredictionMarkets());

    expect(screen.getByText("Will the Fed hold rates in September?")).toBeInTheDocument();
    expect(screen.getByText("75%")).toBeInTheDocument();
    expect(screen.getByText(/vol/)).toBeInTheDocument();
  });

  it("shows an unavailable message rather than a fabricated market when the provider is down", async () => {
    mockedFetchPredictions.mockResolvedValue(null);

    render(await PredictionMarkets());

    expect(screen.getByText(/no prediction markets reachable/i)).toBeInTheDocument();
  });
});
