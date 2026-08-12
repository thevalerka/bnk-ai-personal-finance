from datetime import UTC, date, datetime

import httpx

from app.market.providers.base import CallSpec, DateRange, ProviderError
from app.market.schemas import Candle, Event, NewsItem, Quote

BASE_URL = "https://api.stlouisfed.org/fred"


class FredProvider:
    """Macro/rates series from FRED — the backbone of the fixed-income view.

    `symbol` throughout this provider means a FRED series id (e.g. "DGS10").
    Candles are a flat OHLC (open=high=low=close) over each series
    observation, since FRED reports one value per period, not a trading range.
    """

    name = "fred"

    def __init__(self, client: httpx.AsyncClient, api_key: str) -> None:
        self._client = client
        self._api_key = api_key

    async def quote(self, symbols: list[str]) -> list[Quote]:
        quotes = []
        for series_id in symbols:
            observations = await self._observations(series_id, limit=1)
            if not observations:
                raise ProviderError(f"fred: no observations for {series_id}")
            obs_date, value = observations[-1]
            quotes.append(
                Quote(
                    symbol=series_id,
                    price=value,
                    ts=datetime.combine(obs_date, datetime.min.time(), tzinfo=UTC),
                    source=self.name,
                )
            )
        return quotes

    async def candles(self, symbol: str, tf: str, limit: int) -> list[Candle]:
        observations = await self._observations(symbol, limit=limit)
        return [
            Candle(
                symbol=symbol,
                ts=datetime.combine(obs_date, datetime.min.time(), tzinfo=UTC),
                open=value,
                high=value,
                low=value,
                close=value,
                source=self.name,
            )
            for obs_date, value in observations
        ]

    async def news(self, topics: list[str], since: datetime) -> list[NewsItem]:
        raise NotImplementedError("fred has no news feed")

    async def calendar(self, window: DateRange) -> list[Event]:
        try:
            response = await self._client.get(
                f"{BASE_URL}/releases/dates",
                params={
                    "api_key": self._api_key,
                    "file_type": "json",
                    "realtime_start": window.start.isoformat(),
                    "realtime_end": window.end.isoformat(),
                    "include_release_dates_with_no_data": "false",
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"fred request failed: {exc}") from exc
        return [
            Event(
                ts=datetime.fromisoformat(row["date"]).replace(tzinfo=UTC),
                kind="macro_release",
                importance=2,
                title=row["release_name"],
                source=self.name,
            )
            for row in response.json().get("release_dates", [])
        ]

    def cost(self, call: CallSpec) -> int:
        return max(1, len(call.symbols))

    async def _observations(self, series_id: str, limit: int) -> list[tuple[date, float]]:
        try:
            response = await self._client.get(
                f"{BASE_URL}/series/observations",
                params={
                    "series_id": series_id,
                    "api_key": self._api_key,
                    "file_type": "json",
                    "sort_order": "desc",
                    "limit": limit,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"fred request failed: {exc}") from exc
        observations = []
        for row in response.json().get("observations", []):
            if row["value"] == ".":
                continue
            observations.append((date.fromisoformat(row["date"]), float(row["value"])))
        observations.reverse()
        return observations
