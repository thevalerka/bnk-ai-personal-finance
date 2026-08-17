import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LendTeaser } from "../LendTeaser";
import { fetchLendTokensTeaser } from "@/lib/market";

vi.mock("@/lib/market", () => ({
  fetchLendTokensTeaser: vi.fn(),
}));

const mockedFetch = vi.mocked(fetchLendTokensTeaser);

describe("LendTeaser", () => {
  it("renders a real supply APY for a reachable stablecoin vault", async () => {
    mockedFetch.mockResolvedValue([{ symbol: "USDC", supply_apy_pct: 3.86 }]);

    render(await LendTeaser());

    expect(screen.getByText("USDC lending APY")).toBeInTheDocument();
    expect(screen.getByText("3.86%")).toBeInTheDocument();
  });

  it("shows an unavailable message rather than a fabricated rate when unreachable", async () => {
    mockedFetch.mockResolvedValue(null);

    render(await LendTeaser());

    expect(screen.getByText(/no stablecoin lend vaults reachable/i)).toBeInTheDocument();
  });
});
