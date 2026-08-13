// Server-side client for the Market Data Gateway (apps/api `/market/*`).
// Every function returns `null` on any failure (network error, non-2xx,
// unavailable capability) instead of throwing — callers render an explicit
// "data unavailable" state rather than a fabricated number. See CLAUDE.md
// non-negotiables: no market number without a real provider response behind it.

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8100";

export interface Quote {
  symbol: string;
  price: number;
  ts: string;
  change: number | null;
  change_percent: number | null;
  source: string;
}

export interface Candle {
  symbol: string;
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
  source: string;
}

export interface NewsItem {
  id: string;
  ts: string;
  headline: string;
  url: string;
  source: string;
  tickers: string[];
  topics: string[];
}

export interface MarketEvent {
  ts: string;
  kind: string;
  importance: number;
  title: string;
  source: string;
  tickers: string[];
  topics: string[];
}

async function getJSON<T>(path: string, revalidateSeconds: number): Promise<T | null> {
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      next: { revalidate: revalidateSeconds },
    });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export function fetchTape(): Promise<Quote[] | null> {
  return getJSON<Quote[]>("/market/tape", 15);
}

export function fetchQuote(capability: string, symbols: string[]): Promise<Quote[] | null> {
  const params = new URLSearchParams({ capability, symbols: symbols.join(",") });
  return getJSON<Quote[]>(`/market/quote?${params}`, 15);
}

export function fetchCandles(
  capability: string,
  symbol: string,
  tf = "1d",
  limit = 30,
): Promise<Candle[] | null> {
  const params = new URLSearchParams({ capability, symbol, tf, limit: String(limit) });
  return getJSON<Candle[]>(`/market/candles?${params}`, 60);
}

export function fetchNews(capability = "equity_news", sinceHours = 24): Promise<NewsItem[] | null> {
  const params = new URLSearchParams({ capability, since_hours: String(sinceHours) });
  return getJSON<NewsItem[]>(`/market/news?${params}`, 300);
}

export function fetchCalendar(days = 14): Promise<MarketEvent[] | null> {
  const params = new URLSearchParams({ days: String(days) });
  return getJSON<MarketEvent[]>(`/market/calendar?${params}`, 3600);
}
