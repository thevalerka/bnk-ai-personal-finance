import { fetchQuote } from "@/lib/market";
import { Unavailable } from "./Block";
import { YieldCurveChart } from "./YieldCurveChart";

const TENORS: Array<{ series: string; label: string }> = [
  { series: "DGS1MO", label: "1M" },
  { series: "DGS3MO", label: "3M" },
  { series: "DGS6MO", label: "6M" },
  { series: "DGS1", label: "1Y" },
  { series: "DGS2", label: "2Y" },
  { series: "DGS3", label: "3Y" },
  { series: "DGS5", label: "5Y" },
  { series: "DGS7", label: "7Y" },
  { series: "DGS10", label: "10Y" },
  { series: "DGS20", label: "20Y" },
  { series: "DGS30", label: "30Y" },
];

export async function YieldCurve() {
  const quotes = await fetchQuote(
    "macro_series",
    TENORS.map((t) => t.series),
  );

  const bySeries = new Map((quotes ?? []).map((q) => [q.symbol, q.price]));
  const points = TENORS.map((t) => ({ label: t.label, value: bySeries.get(t.series) })).filter(
    (p): p is { label: string; value: number } => p.value !== undefined,
  );

  if (points.length < 2) {
    return <Unavailable reason="Yield curve unavailable — FRED not reachable." />;
  }

  return <YieldCurveChart points={points} />;
}
