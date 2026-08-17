import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { XStocksTeaser } from "../XStocksTeaser";
import { fetchXStocksTeaser } from "@/lib/market";

vi.mock("@/lib/market", () => ({
  fetchXStocksTeaser: vi.fn(),
}));

const mockedFetch = vi.mocked(fetchXStocksTeaser);

describe("XStocksTeaser", () => {
  it("renders real prices for reachable xStocks", async () => {
    mockedFetch.mockResolvedValue([
      { symbol: "AAPLx", name: "Apple xStock", price_usd: 306.77, category: "public_equity" },
      { symbol: "VCXx", name: "Fundrise Innovation Fund xStock", price_usd: 43.82, category: "pre_ipo" },
    ]);

    render(await XStocksTeaser());

    expect(screen.getByText("$306.77")).toBeInTheDocument();
    expect(screen.getByText(/VCXx.*pre-IPO/)).toBeInTheDocument();
  });

  it("shows an unavailable message rather than a fabricated price when unreachable", async () => {
    mockedFetch.mockResolvedValue(null);

    render(await XStocksTeaser());

    expect(screen.getByText(/no xstocks reachable/i)).toBeInTheDocument();
  });
});
