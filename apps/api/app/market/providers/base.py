from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol

from app.market.schemas import Candle, Event, NewsItem, Quote

CallKind = Literal["quote", "candles", "news", "calendar"]


@dataclass(frozen=True, slots=True)
class DateRange:
    start: date
    end: date


@dataclass(frozen=True, slots=True)
class CallSpec:
    kind: CallKind
    symbols: tuple[str, ...] = ()


class ProviderError(Exception):
    """A provider call failed (network, vendor error, bad response shape).

    The Router catches this and falls back to the next provider in the
    capability's chain. It is never raised for "this provider doesn't offer
    that capability" — that's NotImplementedError instead, which the Router
    treats as a config error, not a transient failure to fall back from.
    """


class Provider(Protocol):
    name: str

    async def quote(self, symbols: list[str]) -> list[Quote]: ...

    async def candles(self, symbol: str, tf: str, limit: int) -> list[Candle]: ...

    async def news(self, topics: list[str], since: datetime) -> list[NewsItem]: ...

    async def calendar(self, window: DateRange) -> list[Event]: ...

    def cost(self, call: CallSpec) -> int: ...
