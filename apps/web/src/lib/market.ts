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

export interface WorldIndexPoint {
  iso_numeric: string;
  name: string;
  symbol: string;
  quote: Quote | null;
  currency: string | null;
  fx_label: string | null;
  bond_yield_pct: number | null;
}

export interface FinancialPeriod {
  period_end: string;
  fiscal_period: string;
  form: string;
  revenue: number | null;
  cost_of_revenue: number | null;
  gross_profit: number | null;
  gross_margin_pct: number | null;
  research_development: number | null;
  sga_expense: number | null;
  operating_expenses: number | null;
  operating_income: number | null;
  operating_margin_pct: number | null;
  interest_expense: number | null;
  income_tax_expense: number | null;
  net_income: number | null;
  net_margin_pct: number | null;
  eps_diluted: number | null;
  eps_basic: number | null;
  operating_cash_flow: number | null;
  capex: number | null;
  free_cash_flow: number | null;
  total_assets: number | null;
  total_liabilities: number | null;
  stockholders_equity: number | null;
  cash_and_equivalents: number | null;
  long_term_debt: number | null;
}

export interface StockDetail {
  symbol: string;
  quote: Quote | null;
  candles: Candle[];
  filings: NewsItem[];
  news: NewsItem[];
  financials: FinancialPeriod[];
}

export interface PredictionMarket {
  question: string;
  probability_pct: number;
  volume_24h: number;
  end_date: string | null;
  url: string;
  source: string;
}

export interface EarningsMarket {
  ticker: string;
  company: string;
  eps_estimate: string | null;
  probability_pct: number;
  volume: number;
  report_date: string | null;
  url: string;
  source: string;
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

export function fetchNews(sinceHours = 24): Promise<NewsItem[] | null> {
  const params = new URLSearchParams({ since_hours: String(sinceHours) });
  return getJSON<NewsItem[]>(`/market/news?${params}`, 300);
}

export function fetchCalendar(days = 14): Promise<MarketEvent[] | null> {
  const params = new URLSearchParams({ days: String(days) });
  return getJSON<MarketEvent[]>(`/market/calendar?${params}`, 3600);
}

export function fetchWorldIndices(): Promise<WorldIndexPoint[] | null> {
  return getJSON<WorldIndexPoint[]>("/market/world", 60);
}

export function fetchStockDetail(symbol: string, days = 180): Promise<StockDetail | null> {
  const params = new URLSearchParams({ days: String(days) });
  return getJSON<StockDetail>(`/market/stock/${encodeURIComponent(symbol)}?${params}`, 60);
}

export function fetchPredictions(): Promise<PredictionMarket[] | null> {
  return getJSON<PredictionMarket[]>("/market/predictions", 60);
}

export function fetchEarningsCalendar(): Promise<EarningsMarket[] | null> {
  return getJSON<EarningsMarket[]>("/market/earnings-calendar", 300);
}

// Read-only dashboard teasers for the /jupiter/* surface (docs/DECISIONS.md
// ADR-0029) — full detail/swap/deposit UI lives on /xstocks and /lend,
// this just needs the same server-side, no-credentials GET every other
// homepage block already uses.
export interface XStockTeaser {
  symbol: string;
  name: string;
  price_usd: number;
  category: "public_equity" | "pre_ipo";
}

export interface LendTokenTeaser {
  symbol: string;
  supply_apy_pct: number;
}

export function fetchXStocksTeaser(): Promise<XStockTeaser[] | null> {
  return getJSON<XStockTeaser[]>("/jupiter/xstocks", 60);
}

export function fetchLendTokensTeaser(): Promise<LendTokenTeaser[] | null> {
  return getJSON<LendTokenTeaser[]>("/jupiter/lend-tokens", 60);
}

// "Market drivers" graph (docs/DECISIONS.md ADR-0031/0032) — correlation/
// lead-lag/Markov-dominance + real breaking news across a 20-node
// cross-asset universe, recomputed and cached server-side per timeframe
// (15 minutes each).
export type MarketGraphAssetClass = "equity" | "rates" | "macro" | "commodity" | "crypto" | "fx" | "news";
export type MarketGraphEdgeKind = "correlation" | "lead_lag" | "markov" | "news";
// "daily_fallback": this node (rates/VIX/WTI/FX — FRED is daily-only) has
// no real intraday series anywhere in this app's provider set, so at an
// intraday timeframe it's still showing its real latest daily bar/quote,
// not fabricated intraday data.
export type MarketGraphDataGranularity = "native" | "daily_fallback";
export type MarketGraphTimeframe = "1d" | "4h" | "1h" | "15m" | "5m";

export interface MarketGraphNode {
  id: string;
  label: string;
  asset_class: MarketGraphAssetClass;
  symbol: string;
  last_price: number | null;
  change_pct: number | null;
  dominance_score: number;
  rank: number;
  data_granularity: MarketGraphDataGranularity;
  // Current realized volatility / trailing-1-year historical volatility,
  // both annualized. null when either side couldn't be computed from real
  // data — must render as "no data", never default to 1.0 ("normal").
  volatility_ratio: number | null;
}

export interface MarketGraphEdge {
  source: string;
  target: string;
  weight: number;
  kind: MarketGraphEdgeKind;
}

export interface MarketGraphCorrelation {
  a: string;
  b: string;
  corr: number;
}

export interface MarketGraphSnapshot {
  computed_at: string;
  nodes: MarketGraphNode[];
  edges: MarketGraphEdge[];
  correlations: MarketGraphCorrelation[];
}

export function fetchMarketGraph(): Promise<MarketGraphSnapshot | null> {
  return getJSON<MarketGraphSnapshot>("/market/graph", 900);
}
