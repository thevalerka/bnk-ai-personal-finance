import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Sparkline } from "../Sparkline";
import type { Candle } from "@/lib/market";

function candle(close: number): Candle {
  return { symbol: "AAPL", ts: "2026-01-01T00:00:00Z", open: close, high: close, low: close, close, volume: null, source: "test" };
}

describe("Sparkline", () => {
  it("renders a path when given two or more candles", () => {
    const { container } = render(<Sparkline candles={[candle(1), candle(2), candle(1.5)]} />);
    expect(container.querySelector("path")).toBeInTheDocument();
    expect(container.querySelector("svg")).toHaveAttribute("role", "img");
  });

  it("renders nothing for fewer than two candles", () => {
    const { container } = render(<Sparkline candles={[candle(1)]} />);
    expect(container.querySelector("svg")).not.toBeInTheDocument();
  });
});
