from datetime import UTC, datetime

import httpx

from app.market.providers.base import CallSpec, DateRange, ProviderError
from app.market.schemas import Candle, Event, NewsItem, Quote

BASE_URL = "https://finnhub.io/api/v1"


class FinnhubProvider:
    """US equity quotes, news, and earnings calendar (free tier: ~60 req/min).

    No free candle data on this provider — see docs/PLAN.md section 3.2.
    """

    name = "finnhub"

    def __init__(self, client: httpx.AsyncClient, api_key: str) -> None:
        self._client = client
        self._api_key = api_key

    async def quote(self, symbols: list[str]) -> list[Quote]:
        quotes = []
        for symbol in symbols:
            response = await self._get("/quote", {"symbol": symbol})
            data = response.json()
            if data.get("t") in (None, 0):
                raise ProviderError(f"finnhub: no quote data for {symbol}")
            quotes.append(
                Quote(
                    symbol=symbol,
                    price=data["c"],
                    change=data.get("d"),
                    change_percent=data.get("dp"),
                    ts=datetime.fromtimestamp(data["t"], tz=UTC),
                    source=self.name,
                )
            )
        return quotes

    async def candles(self, symbol: str, tf: str, limit: int) -> list[Candle]:
        raise NotImplementedError("finnhub candles require a paid plan")

    async def news(self, topics: list[str], since: datetime) -> list[NewsItem]:
        from_date = since.date().isoformat()
        to_date = datetime.now(tz=UTC).date().isoformat()
        items: list[NewsItem] = []
        symbols = topics or [""]
        for symbol in symbols:
            if symbol:
                response = await self._get(
                    "/company-news", {"symbol": symbol, "from": from_date, "to": to_date}
                )
            else:
                response = await self._get("/news", {"category": "general"})
            for article in response.json():
                ts = datetime.fromtimestamp(article["datetime"], tz=UTC)
                if ts < since:
                    continue
                items.append(
                    NewsItem(
                        id=str(article["id"]),
                        ts=ts,
                        headline=article["headline"],
                        url=article["url"],
                        source=self.name,
                        tickers=[symbol] if symbol else list(article.get("related", "").split(",")),
                        topics=[article.get("category", "")],
                    )
                )
        return items

    async def calendar(self, window: DateRange) -> list[Event]:
        response = await self._get(
            "/calendar/earnings",
            {"from": window.start.isoformat(), "to": window.end.isoformat()},
        )
        events = []
        for row in response.json().get("earningsCalendar", []):
            events.append(
                Event(
                    ts=datetime.fromisoformat(row["date"]).replace(tzinfo=UTC),
                    kind="earnings",
                    importance=2,
                    title=f"{row['symbol']} earnings ({row.get('quarter')}Q{row.get('year')})",
                    source=self.name,
                    tickers=[row["symbol"]],
                )
            )
        return events

    def cost(self, call: CallSpec) -> int:
        return max(1, len(call.symbols))

    async def _get(self, path: str, params: dict[str, str]) -> httpx.Response:
        try:
            response = await self._client.get(
                f"{BASE_URL}{path}", params={**params, "token": self._api_key}
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"finnhub request failed: {exc}") from exc
        return response
