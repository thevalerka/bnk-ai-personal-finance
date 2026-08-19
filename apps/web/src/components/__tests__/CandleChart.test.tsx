import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { CandleChart } from "../CandleChart";
import { fetchCandlesPublic } from "@/lib/marketClient";

// lightweight-charts renders to a <canvas> via a real browser rendering
// context jsdom doesn't implement — mocked entirely here, same reasoning
// as the ResizeObserver stub in vitest.setup.ts. This test asserts the
// component drives the library's API correctly (series data, fitContent,
// timeframe refetch), not pixel output.
const mockSeries = { setData: vi.fn(), applyOptions: vi.fn() };
const mockTimeScale = { fitContent: vi.fn() };
const mockChart = {
  addSeries: vi.fn(() => mockSeries),
  timeScale: vi.fn(() => mockTimeScale),
  resize: vi.fn(),
  applyOptions: vi.fn(),
  remove: vi.fn(),
};

vi.mock("lightweight-charts", () => ({
  createChart: vi.fn(() => mockChart),
  CandlestickSeries: "CandlestickSeries",
}));

vi.mock("@/lib/marketClient", () => ({
  fetchCandlesPublic: vi.fn(),
}));

const mockedFetchCandlesPublic = vi.mocked(fetchCandlesPublic);

function candle(ts: string, close: number) {
  return { symbol: "SPY", ts, open: close, high: close, low: close, close, volume: 1, source: "alpaca" };
}

const initialCandles = [candle("2026-08-01", 555), candle("2026-08-18", 560.5)];

describe("CandleChart", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("mounts a candlestick series with the initial candles and fits content", () => {
    render(<CandleChart symbol="SPY" capability="equity_candles" initialCandles={initialCandles} />);

    expect(mockChart.addSeries).toHaveBeenCalled();
    expect(mockSeries.setData).toHaveBeenCalledWith(
      expect.arrayContaining([expect.objectContaining({ close: 560.5 })]),
    );
    expect(mockTimeScale.fitContent).toHaveBeenCalled();
  });

  it("switching timeframe refetches candles for that timeframe and updates the series", async () => {
    mockedFetchCandlesPublic.mockResolvedValue([candle("2026-08-18T09:00:00Z", 561), candle("2026-08-18T10:00:00Z", 562)]);
    render(<CandleChart symbol="SPY" capability="equity_candles" initialCandles={initialCandles} />);

    fireEvent.click(screen.getByRole("button", { name: "1H" }));

    await waitFor(() => {
      expect(mockedFetchCandlesPublic).toHaveBeenCalledWith("equity_candles", "SPY", "1h", 168);
    });
    await waitFor(() => {
      expect(mockSeries.setData).toHaveBeenCalledTimes(2);
    });
  });

  it("shows an error note when a timeframe refetch fails, without crashing", async () => {
    mockedFetchCandlesPublic.mockResolvedValue(null);
    render(<CandleChart symbol="SPY" capability="equity_candles" initialCandles={initialCandles} />);

    fireEvent.click(screen.getByRole("button", { name: "4H" }));

    expect(await screen.findByText(/couldn't load 4h candles/i)).toBeInTheDocument();
  });

  it("reset zoom calls fitContent again", () => {
    render(<CandleChart symbol="SPY" capability="equity_candles" initialCandles={initialCandles} />);
    mockTimeScale.fitContent.mockClear();

    fireEvent.click(screen.getByRole("button", { name: /reset zoom/i }));

    expect(mockTimeScale.fitContent).toHaveBeenCalledTimes(1);
  });
});
