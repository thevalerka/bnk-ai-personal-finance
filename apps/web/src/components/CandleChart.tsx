"use client";

import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import type { Candle } from "@/lib/market";
import { fetchCandlesPublic } from "@/lib/marketClient";
import styles from "./CandleChart.module.css";

const TIMEFRAMES: { label: string; tf: string; limit: number }[] = [
  { label: "1M", tf: "1m", limit: 180 },
  { label: "5M", tf: "5m", limit: 180 },
  { label: "15M", tf: "15m", limit: 180 },
  { label: "1H", tf: "1h", limit: 168 },
  { label: "4H", tf: "4h", limit: 180 },
  { label: "24H", tf: "1d", limit: 90 },
];

function toSeriesData(candles: Candle[]) {
  return candles
    .map((c) => ({
      time: Math.floor(new Date(c.ts).getTime() / 1000) as UTCTimestamp,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }))
    .sort((a, b) => (a.time as number) - (b.time as number));
}

function readThemeColors() {
  const styleDecl = getComputedStyle(document.documentElement);
  const read = (name: string, fallback: string) => styleDecl.getPropertyValue(name).trim() || fallback;
  return {
    up: read("--positive", "#22d66b"),
    down: read("--negative", "#ff4d6a"),
    text: read("--text-muted", "#8a93a6"),
    border: read("--border", "rgba(130,160,220,0.16)"),
  };
}

// Real candlestick chart with native zoom (wheel)/pan (drag)/reset —
// lightweight-charts (TradingView's MIT renderer) rather than hand-rolled
// SVG, since this repo's usual pattern (PriceHistoryChart.tsx) doesn't
// cover zoom/pan and getting that right by hand is a lot of fragile pointer
// math (docs/DECISIONS.md ADR-0030). The chart instance itself mounts once;
// timeframe switches update the existing series in place rather than
// tearing the chart down, so switching feels instant, not a flash-of-empty.
export function CandleChart({
  symbol,
  capability,
  initialCandles,
}: {
  symbol: string;
  capability: string;
  initialCandles: Candle[];
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const initialCandlesRef = useRef(initialCandles);
  const [activeTf, setActiveTf] = useState("1d");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const colors = readThemeColors();

    const chart = createChart(container, {
      layout: { background: { color: "transparent" }, textColor: colors.text, attributionLogo: false },
      grid: {
        vertLines: { color: colors.border },
        horzLines: { color: colors.border },
      },
      rightPriceScale: { borderColor: colors.border },
      timeScale: { borderColor: colors.border, timeVisible: true, secondsVisible: false },
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: colors.up,
      downColor: colors.down,
      borderVisible: false,
      wickUpColor: colors.up,
      wickDownColor: colors.down,
    });
    series.setData(toSeriesData(initialCandlesRef.current));
    chart.timeScale().fitContent();
    chart.resize(container.clientWidth, container.clientHeight);

    chartRef.current = chart;
    seriesRef.current = series;

    const resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      chart.resize(entry.contentRect.width, entry.contentRect.height);
    });
    resizeObserver.observe(container);

    const themeObserver = new MutationObserver(() => {
      const updated = readThemeColors();
      chart.applyOptions({
        layout: { textColor: updated.text },
        grid: { vertLines: { color: updated.border }, horzLines: { color: updated.border } },
        rightPriceScale: { borderColor: updated.border },
        timeScale: { borderColor: updated.border },
      });
      series.applyOptions({
        upColor: updated.up,
        downColor: updated.down,
        wickUpColor: updated.up,
        wickDownColor: updated.down,
      });
    });
    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });

    return () => {
      resizeObserver.disconnect();
      themeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  async function handleTimeframeClick(tf: string, limit: number) {
    if (tf === activeTf || loading) return;
    setActiveTf(tf);
    setLoading(true);
    setError(false);
    const candles = await fetchCandlesPublic(capability, symbol, tf, limit);
    setLoading(false);
    if (!candles || candles.length < 2) {
      setError(true);
      return;
    }
    seriesRef.current?.setData(toSeriesData(candles));
    chartRef.current?.timeScale().fitContent();
  }

  function handleReset() {
    chartRef.current?.timeScale().fitContent();
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.controls}>
        <div className={styles.timeframes} role="group" aria-label="Timeframe">
          {TIMEFRAMES.map((t) => (
            <button
              key={t.tf}
              type="button"
              className={t.tf === activeTf ? `${styles.tfButton} ${styles.tfButtonActive}` : styles.tfButton}
              onClick={() => void handleTimeframeClick(t.tf, t.limit)}
              disabled={loading}
              aria-pressed={t.tf === activeTf}
            >
              {t.label}
            </button>
          ))}
        </div>
        <button type="button" className={styles.resetButton} onClick={handleReset} title="Reset chart zoom/pan">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path
              d="M20 12a8 8 0 1 1-2.34-5.66M20 4v5h-5"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          Reset zoom
        </button>
      </div>
      {error ? (
        <div className={styles.errorNote}>Couldn&apos;t load {activeTf} candles — showing last available data.</div>
      ) : null}
      <div ref={containerRef} className={styles.chartContainer} />
    </div>
  );
}
