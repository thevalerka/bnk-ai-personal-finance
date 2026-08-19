from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

AssetClass = Literal["equity", "crypto", "macro", "fx", "commodity"]


class Instrument(BaseModel):
    symbol: str
    asset_class: AssetClass
    name: str | None = None
    exchange: str | None = None
    currency: str = "USD"


class Quote(BaseModel):
    symbol: str
    price: float
    ts: datetime
    change: float | None = None
    change_percent: float | None = None
    source: str


class Candle(BaseModel):
    symbol: str
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    source: str


class CurvePoint(BaseModel):
    series_id: str
    ts: date
    value: float
    source: str


class NewsItem(BaseModel):
    id: str
    ts: datetime
    headline: str
    url: str
    source: str
    tickers: list[str] = []
    topics: list[str] = []


class WorldIndexPoint(BaseModel):
    iso_numeric: str
    name: str
    symbol: str
    quote: Quote | None = None
    currency: str | None = None
    fx_label: str | None = None
    bond_yield_pct: float | None = None


class FinancialPeriod(BaseModel):
    period_end: date
    fiscal_period: str  # "FY", "Q1", "Q2", "Q3"
    form: str  # "10-K" or "10-Q"
    # Income statement
    revenue: float | None = None
    cost_of_revenue: float | None = None
    gross_profit: float | None = None
    gross_margin_pct: float | None = None
    research_development: float | None = None
    sga_expense: float | None = None
    operating_expenses: float | None = None
    operating_income: float | None = None
    operating_margin_pct: float | None = None
    interest_expense: float | None = None
    income_tax_expense: float | None = None
    net_income: float | None = None
    net_margin_pct: float | None = None
    # Per share
    eps_diluted: float | None = None
    eps_basic: float | None = None
    # Cash flow
    operating_cash_flow: float | None = None
    capex: float | None = None
    free_cash_flow: float | None = None
    # Balance sheet (point-in-time as of period_end, not a duration)
    total_assets: float | None = None
    total_liabilities: float | None = None
    stockholders_equity: float | None = None
    cash_and_equivalents: float | None = None
    long_term_debt: float | None = None


class StockDetail(BaseModel):
    symbol: str
    quote: Quote | None = None
    candles: list[Candle] = []
    filings: list[NewsItem] = []
    news: list[NewsItem] = []
    financials: list[FinancialPeriod] = []


class PredictionMarket(BaseModel):
    question: str
    probability_pct: float
    volume_24h: float
    end_date: datetime | None = None
    url: str
    source: str = "polymarket"


class EarningsMarket(BaseModel):
    ticker: str
    company: str
    eps_estimate: str | None = None
    probability_pct: float
    volume: float
    report_date: datetime | None = None
    url: str
    source: str = "polymarket"


class Event(BaseModel):
    ts: datetime
    kind: str
    importance: int
    title: str
    source: str
    tickers: list[str] = []
    topics: list[str] = []


MarketGraphAssetClass = Literal["equity", "rates", "macro", "commodity", "crypto", "fx", "news"]
MarketGraphEdgeKind = Literal["correlation", "lead_lag", "markov", "news"]
# "daily_fallback": this node has no real intraday data anywhere in this
# app's provider set (FRED is daily-only) — at an intraday timeframe it's
# still showing its real latest daily bar/quote, not fabricated intraday
# data (docs/DECISIONS.md ADR-0032).
MarketGraphDataGranularity = Literal["native", "daily_fallback"]


class MarketGraphNode(BaseModel):
    id: str
    label: str
    asset_class: MarketGraphAssetClass
    symbol: str
    last_price: float | None = None
    change_pct: float | None = None
    dominance_score: float
    rank: int
    data_granularity: MarketGraphDataGranularity = "native"
    # Current realized volatility (annualized) / trailing-1-year historical
    # volatility (annualized) — None when either side couldn't be computed
    # from real data. ~1.0 means "trading about as volatile as its own
    # 1-year norm"; None must not be presented as 1.0 (that would silently
    # claim "normal" for a number that was never actually reachable).
    volatility_ratio: float | None = None


class MarketGraphEdge(BaseModel):
    source: str
    target: str
    weight: float
    kind: MarketGraphEdgeKind


class MarketGraphCorrelation(BaseModel):
    a: str
    b: str
    corr: float


class MarketGraphSnapshot(BaseModel):
    computed_at: datetime
    nodes: list[MarketGraphNode] = []
    edges: list[MarketGraphEdge] = []
    correlations: list[MarketGraphCorrelation] = []
