import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Tape } from "../Tape";
import { fetchTape } from "@/lib/market";

vi.mock("@/lib/market", () => ({
  fetchTape: vi.fn(),
}));

const mockedFetchTape = vi.mocked(fetchTape);

describe("Tape", () => {
  it("renders quotes from a live tape", async () => {
    mockedFetchTape.mockResolvedValue([
      { symbol: "BTC", price: 61234, ts: "2026-01-01T00:00:00Z", change: null, change_percent: 1.4, source: "binance" },
    ]);

    render(await Tape());

    // The marquee track renders the quote list twice (duplicated for a
    // seamless CSS scroll loop — the second copy is aria-hidden) so each
    // value legitimately appears twice in the DOM.
    expect(screen.getAllByText("BTC").length).toBeGreaterThan(0);
    expect(screen.getAllByText("61,234").length).toBeGreaterThan(0);
  });

  it("shows an unavailable message rather than an empty or fabricated tape", async () => {
    mockedFetchTape.mockResolvedValue(null);

    render(await Tape());

    expect(screen.getByText(/global tape unavailable/i)).toBeInTheDocument();
  });
});
