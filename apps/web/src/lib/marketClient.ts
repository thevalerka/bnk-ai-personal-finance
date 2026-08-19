// Client-side (browser) fetch layer for /market/* candle data — used from
// Client Components that need to refetch after the initial server render
// (e.g. CandleChart.tsx switching timeframes). Same NEXT_PUBLIC_API_PUBLIC_URL
// split as lib/attention.ts: lib/market.ts's NEXT_PUBLIC_API_BASE_URL is a
// same-box loopback address in production, unreachable from a visitor's own
// browser. No credentials needed here — candle data isn't profile-scoped.

import type { Candle } from "./market";

const API_PUBLIC_URL = process.env.NEXT_PUBLIC_API_PUBLIC_URL ?? "http://localhost:8100";

export async function fetchCandlesPublic(
  capability: string,
  symbol: string,
  tf: string,
  limit: number,
): Promise<Candle[] | null> {
  const params = new URLSearchParams({ capability, symbol, tf, limit: String(limit) });
  try {
    const response = await fetch(`${API_PUBLIC_URL}/market/candles?${params}`);
    if (!response.ok) return null;
    return (await response.json()) as Candle[];
  } catch {
    return null;
  }
}
