import json
from datetime import UTC, datetime

import httpx

from app.market.providers.base import CallSpec, DateRange, ProviderError
from app.market.schemas import Candle, Event, NewsItem, Quote

BASE_URL = "https://api.binance.com/api/v3"


class BinanceProvider:
    """Crypto spot prices/candles via Binance's public REST API. No key required.

    Callers use canonical coin symbols ("BTC"), not Binance trading pairs
    ("BTCUSDT") — this provider maps canonical <-> vendor symbols internally
    (assuming a USDT quote currency), the same way HyperliquidProvider takes
    "BTC" natively, so the crypto_quote fallback chain in
    config/providers.yaml can swap providers without the caller knowing.
    """

    name = "binance"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def quote(self, symbols: list[str]) -> list[Quote]:
        pairs = [self._to_pair(symbol) for symbol in symbols]
        if len(pairs) == 1:
            response = await self._get("/ticker/price", {"symbol": pairs[0]})
            rows = [response.json()]
        else:
            response = await self._get("/ticker/price", {"symbols": json.dumps(pairs)})
            rows = response.json()
        by_pair = {row["symbol"]: row for row in rows}
        now = datetime.now(tz=UTC)
        quotes = []
        for symbol, pair in zip(symbols, pairs, strict=True):
            row = by_pair.get(pair)
            if row is None:
                raise ProviderError(f"binance: no ticker for {pair}")
            quotes.append(Quote(symbol=symbol, price=float(row["price"]), ts=now, source=self.name))
        return quotes

    async def candles(self, symbol: str, tf: str, limit: int) -> list[Candle]:
        pair = self._to_pair(symbol)
        response = await self._get("/klines", {"symbol": pair, "interval": tf, "limit": limit})
        candles = []
        for row in response.json():
            open_time_ms, open_, high, low, close, volume = row[:6]
            candles.append(
                Candle(
                    symbol=symbol,
                    ts=datetime.fromtimestamp(open_time_ms / 1000, tz=UTC),
                    open=float(open_),
                    high=float(high),
                    low=float(low),
                    close=float(close),
                    volume=float(volume),
                    source=self.name,
                )
            )
        return candles

    async def news(self, topics: list[str], since: datetime) -> list[NewsItem]:
        raise NotImplementedError("binance has no news feed")

    async def calendar(self, window: DateRange) -> list[Event]:
        raise NotImplementedError("binance has no economic calendar")

    def cost(self, call: CallSpec) -> int:
        return 1

    @staticmethod
    def _to_pair(symbol: str) -> str:
        return symbol if symbol.endswith("USDT") else f"{symbol}USDT"

    async def _get(self, path: str, params: dict[str, str | int | float]) -> httpx.Response:
        try:
            response = await self._client.get(f"{BASE_URL}{path}", params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"binance request failed: {exc}") from exc
        return response
