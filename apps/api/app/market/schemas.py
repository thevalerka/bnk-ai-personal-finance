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


class Event(BaseModel):
    ts: datetime
    kind: str
    importance: int
    title: str
    source: str
    tickers: list[str] = []
    topics: list[str] = []
