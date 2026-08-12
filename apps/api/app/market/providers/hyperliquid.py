from datetime import UTC, datetime

import httpx

from app.market.providers.base import CallSpec, DateRange, ProviderError
from app.market.schemas import Candle, Event, NewsItem, Quote

BASE_URL = "https://api.hyperliquid.xyz/info"

_INTERVAL_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


class HyperliquidProvider:
    """Crypto spot/perp mids and candles via Hyperliquid's public info API.

    No key required. Symbols are Hyperliquid coin names (e.g. "BTC"), not
    trading pairs like Binance's "BTCUSDT".
    """

    name = "hyperliquid"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def quote(self, symbols: list[str]) -> list[Quote]:
        response = await self._post({"type": "allMids"})
        mids: dict[str, str] = response.json()
        now = datetime.now(tz=UTC)
        quotes = []
        for symbol in symbols:
            price = mids.get(symbol)
            if price is None:
                raise ProviderError(f"hyperliquid: no mid price for {symbol}")
            quotes.append(Quote(symbol=symbol, price=float(price), ts=now, source=self.name))
        return quotes

    async def candles(self, symbol: str, tf: str, limit: int) -> list[Candle]:
        interval_ms = _INTERVAL_MS.get(tf)
        if interval_ms is None:
            raise ProviderError(f"hyperliquid: unsupported interval {tf!r}")
        end_ms = int(datetime.now(tz=UTC).timestamp() * 1000)
        start_ms = end_ms - interval_ms * limit
        response = await self._post(
            {
                "type": "candleSnapshot",
                "req": {"coin": symbol, "interval": tf, "startTime": start_ms, "endTime": end_ms},
            }
        )
        return [
            Candle(
                symbol=symbol,
                ts=datetime.fromtimestamp(row["t"] / 1000, tz=UTC),
                open=float(row["o"]),
                high=float(row["h"]),
                low=float(row["l"]),
                close=float(row["c"]),
                volume=float(row["v"]),
                source=self.name,
            )
            for row in response.json()
        ]

    async def news(self, topics: list[str], since: datetime) -> list[NewsItem]:
        raise NotImplementedError("hyperliquid has no news feed")

    async def calendar(self, window: DateRange) -> list[Event]:
        raise NotImplementedError("hyperliquid has no economic calendar")

    def cost(self, call: CallSpec) -> int:
        return 1

    async def _post(self, body: dict[str, object]) -> httpx.Response:
        try:
            response = await self._client.post(BASE_URL, json=body)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"hyperliquid request failed: {exc}") from exc
        return response
