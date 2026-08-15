import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { WorldMap } from "../WorldMap";
import { fetchWorldIndices, type WorldIndexPoint } from "@/lib/market";

vi.mock("@/lib/market", () => ({
  fetchWorldIndices: vi.fn(),
}));

const mockedFetchWorldIndices = vi.mocked(fetchWorldIndices);

function usPoint(overrides: Partial<WorldIndexPoint> = {}): WorldIndexPoint {
  return {
    iso_numeric: "840",
    name: "United States",
    symbol: "SPY",
    quote: {
      symbol: "SPY",
      price: 777.88,
      ts: "2026-08-13T20:00:00Z",
      change: 5.39,
      change_percent: 0.7,
      source: "finnhub",
    },
    currency: null,
    fx_label: null,
    bond_yield_pct: 4.68,
    ...overrides,
  };
}

describe("WorldMap", () => {
  it("renders a titled path for a tracked country with a real quote", async () => {
    mockedFetchWorldIndices.mockResolvedValue([usPoint()]);

    // Testing Library's getByTitle only matches a <title> that's a direct
    // child of <svg> — ours is nested one level deeper, inside each
    // country's <path> (the correct place for a per-shape native tooltip,
    // still fully functional in a real browser) — so assert on the DOM
    // directly instead.
    const { container } = render(await WorldMap());
    const titles = Array.from(container.querySelectorAll("title")).map((t) => t.textContent);

    expect(titles).toContain("United States (SPY): +0.7% — 777.88");
  });

  it("shows the % change as an always-visible label, not only on hover", async () => {
    mockedFetchWorldIndices.mockResolvedValue([usPoint()]);

    render(await WorldMap());

    // A real <text> node in the DOM, not something gated behind a hover
    // state — visible without any pointer interaction.
    expect(screen.getByText("+0.7%")).toBeInTheDocument();
  });

  it("opens a popup with the ETF, currency, and yield on click, and closes it again", async () => {
    mockedFetchWorldIndices.mockResolvedValue([
      usPoint({
        iso_numeric: "392",
        name: "Japan",
        symbol: "EWJ",
        quote: {
          symbol: "EWJ",
          price: 98.47,
          ts: "2026-08-13T20:00:00Z",
          change: 0.68,
          change_percent: 0.7,
          source: "finnhub",
        },
        currency: "JPY",
        fx_label: "$1 = 157.54 JPY",
        bond_yield_pct: 2.67,
      }),
    ]);
    const { container } = render(await WorldMap());

    const path = container.querySelector('path[aria-label^="Japan"]');
    expect(path).toBeTruthy();
    fireEvent.click(path as Element);

    expect(screen.getByRole("dialog", { name: /japan details/i })).toBeInTheDocument();
    expect(screen.getByText("EWJ")).toBeInTheDocument();
    expect(screen.getByText("$1 = 157.54 JPY")).toBeInTheDocument();
    expect(screen.getByText("2.67%")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /view full details/i })).toHaveAttribute(
      "href",
      "/country/392",
    );

    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows 'Not available' in the popup for currency/yield the provider doesn't cover, without fabricating a number", async () => {
    mockedFetchWorldIndices.mockResolvedValue([usPoint({ bond_yield_pct: null })]);
    const { container } = render(await WorldMap());

    const path = container.querySelector('path[aria-label^="United States"]');
    fireEvent.click(path as Element);

    expect(screen.getAllByText("Not available").length).toBe(2); // currency (US has none) + yield
  });

  it("does not open a popup for an untracked country", async () => {
    mockedFetchWorldIndices.mockResolvedValue([]);
    const { container } = render(await WorldMap());

    const anyCountryPath = container.querySelector("path");
    fireEvent.click(anyCountryPath as Element);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("merges a territory that shares its parent country's code, without a key collision on codeless disputed regions", async () => {
    mockedFetchWorldIndices.mockResolvedValue([
      usPoint({
        iso_numeric: "036",
        name: "Australia",
        symbol: "EWA",
        quote: {
          symbol: "EWA",
          price: 24.1,
          ts: "2026-08-13T20:00:00Z",
          change: -0.2,
          change_percent: -0.4,
          source: "finnhub",
        },
        currency: "AUD",
        fx_label: "1 AUD = $0.7064",
      }),
    ]);
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

    const { container } = render(await WorldMap());

    expect(container.querySelectorAll("path").length).toBeGreaterThan(0);
    expect(consoleError.mock.calls.some((call) => String(call[0]).includes("same key"))).toBe(
      false,
    );
    consoleError.mockRestore();
  });

  it("shows an unavailable message when no world quotes are reachable", async () => {
    mockedFetchWorldIndices.mockResolvedValue(null);

    render(await WorldMap());

    expect(screen.getByText(/world map unavailable/i)).toBeInTheDocument();
  });
});
