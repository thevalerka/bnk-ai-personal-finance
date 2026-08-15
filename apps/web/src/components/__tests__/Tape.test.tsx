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

  it("shows friendly labels for raw FRED series IDs instead of the vendor code", async () => {
    mockedFetchTape.mockResolvedValue([
      { symbol: "VIXCLS", price: 16.5, ts: "2026-01-01T00:00:00Z", change: null, change_percent: null, source: "fred" },
      { symbol: "DCOILWTICO", price: 71.2, ts: "2026-01-01T00:00:00Z", change: null, change_percent: null, source: "fred" },
      { symbol: "DGS2", price: 4.05, ts: "2026-01-01T00:00:00Z", change: null, change_percent: null, source: "fred" },
    ]);

    render(await Tape());

    expect(screen.getAllByText("VIX").length).toBeGreaterThan(0);
    expect(screen.getAllByText("WTI").length).toBeGreaterThan(0);
    expect(screen.getAllByText("2Y").length).toBeGreaterThan(0);
    expect(screen.queryByText("VIXCLS")).not.toBeInTheDocument();
    expect(screen.queryByText("DCOILWTICO")).not.toBeInTheDocument();
  });

  it("links equity items to their stock detail page, but not crypto/macro items", async () => {
    mockedFetchTape.mockResolvedValue([
      { symbol: "AAPL", price: 305.09, ts: "2026-01-01T00:00:00Z", change: null, change_percent: 1.4, source: "finnhub" },
      { symbol: "BTC", price: 61234, ts: "2026-01-01T00:00:00Z", change: null, change_percent: 1.4, source: "binance" },
    ]);

    render(await Tape());

    const aaplLinks = screen.getAllByRole("link", { name: /AAPL/ });
    expect(aaplLinks.length).toBeGreaterThan(0);
    expect(aaplLinks[0]).toHaveAttribute("href", "/stock/AAPL");
    expect(screen.queryByRole("link", { name: /BTC/ })).not.toBeInTheDocument();

    // The marquee's second, aria-hidden copy (excluded from the accessible
    // role query above, correctly) shouldn't be a keyboard tab stop either.
    const allAaplLinks = screen.getAllByRole("link", { name: /AAPL/, hidden: true });
    expect(allAaplLinks.length).toBe(2);
    const hiddenLink = allAaplLinks.find((link) => link.getAttribute("tabindex") === "-1");
    expect(hiddenLink).toBeDefined();
  });

  it("shows an unavailable message rather than an empty or fabricated tape", async () => {
    mockedFetchTape.mockResolvedValue(null);

    render(await Tape());

    expect(screen.getByText(/global tape unavailable/i)).toBeInTheDocument();
  });
});
