import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakeredis import FakeAsyncRedis
from redis.asyncio import Redis

from app.market.providers.base import CallSpec, DateRange, ProviderError
from app.market.schemas import Candle, Event, NewsItem, Quote

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    with (FIXTURES_DIR / name).open() as f:
        return json.load(f)


@pytest.fixture
async def http_client() -> AsyncGenerator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture
async def redis() -> AsyncGenerator[Redis]:
    client = FakeAsyncRedis()
    yield client
    await client.aclose()


class FakeProvider:
    """A minimal Provider test double: controllable success/failure, call-counted."""

    def __init__(self, name: str, error: Exception | None = None, cost_value: int = 1) -> None:
        self.name = name
        self.calls = 0
        self._error = error
        self._cost_value = cost_value

    async def quote(self, symbols: list[str]) -> list[Quote]:
        self.calls += 1
        if self._error is not None:
            raise self._error
        now = datetime.now(tz=UTC)
        return [Quote(symbol=s, price=1.0, ts=now, source=self.name) for s in symbols]

    async def candles(self, symbol: str, tf: str, limit: int) -> list[Candle]:
        self.calls += 1
        if self._error is not None:
            raise self._error
        now = datetime.now(tz=UTC)
        return [
            Candle(symbol=symbol, ts=now, open=1.0, high=1.0, low=1.0, close=1.0, source=self.name)
        ]

    async def news(self, topics: list[str], since: datetime) -> list[NewsItem]:
        self.calls += 1
        if self._error is not None:
            raise self._error
        now = datetime.now(tz=UTC)
        return [
            NewsItem(
                id="1",
                ts=now,
                headline="headline",
                url="https://example.com",
                source=self.name,
            )
        ]

    async def calendar(self, window: DateRange) -> list[Event]:
        self.calls += 1
        if self._error is not None:
            raise self._error
        now = datetime.now(tz=UTC)
        return [Event(ts=now, kind="test", importance=1, title="event", source=self.name)]

    def cost(self, call: CallSpec) -> int:
        return self._cost_value


__all__ = ["FakeProvider", "ProviderError", "load_fixture"]
