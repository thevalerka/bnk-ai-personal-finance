from datetime import UTC, datetime, timedelta

import httpx

from app.market.providers.base import CallSpec, DateRange, ProviderError
from app.market.schemas import Candle, Event, NewsItem, Quote

BASE_URL = "https://data.alpaca.markets/v2"

_TIMEFRAME_MAP = {
    "1m": "1Min",
    "5m": "5Min",
    "15m": "15Min",
    "1h": "1Hour",
    "4h": "4Hour",
    "1d": "1Day",
}
_MINUTES_PER_TF = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240}
_TRADING_MINUTES_PER_DAY = 390  # NYSE 9:30-16:00 ET


def _calendar_days_needed(tf: str, limit: int) -> int:
    """Calendar-day span covering `limit` trading periods, padded for
    weekends/holidays. Alpaca's /bars requires an explicit `start` — omit it
    and this account gets back `"bars": null` rather than recent data."""
    if tf == "1d":
        trading_periods = limit
    else:
        minutes_per_bar = _MINUTES_PER_TF.get(tf, 1)
        periods_per_day = max(1, _TRADING_MINUTES_PER_DAY // minutes_per_bar)
        trading_periods = -(-limit // periods_per_day)  # ceil
    return trading_periods * 2 + 10


class AlpacaProvider:
    """Real-time (IEX feed) equity quotes and bars. Free with a paper account."""

    name = "alpaca"

    def __init__(self, client: httpx.AsyncClient, api_key: str, api_secret: str) -> None:
        self._client = client
        self._headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": api_secret}

    async def quote(self, symbols: list[str]) -> list[Quote]:
        response = await self._get("/stocks/trades/latest", {"symbols": ",".join(symbols)})
        trades = response.json().get("trades", {})
        quotes = []
        for symbol in symbols:
            trade = trades.get(symbol)
            if trade is None:
                raise ProviderError(f"alpaca: no trade data for {symbol}")
            quotes.append(
                Quote(
                    symbol=symbol,
                    price=trade["p"],
                    ts=datetime.fromisoformat(trade["t"].replace("Z", "+00:00")),
                    source=self.name,
                )
            )
        return quotes

    async def candles(self, symbol: str, tf: str, limit: int) -> list[Candle]:
        timeframe = _TIMEFRAME_MAP.get(tf, tf)
        end = datetime.now(tz=UTC)
        start = end - timedelta(days=_calendar_days_needed(tf, limit))
        response = await self._get(
            f"/stocks/{symbol}/bars",
            {
                "timeframe": timeframe,
                "start": start.date().isoformat(),
                "end": end.date().isoformat(),
                "limit": limit + 30,
                # Free-tier accounts get a 403 ("subscription does not permit
                # querying recent SIP data") on the default feed for anything
                # in roughly the last month; IEX is free-tier-accessible.
                "feed": "iex",
            },
        )
        bars = (response.json().get("bars") or [])[-limit:]
        return [
            Candle(
                symbol=symbol,
                ts=datetime.fromisoformat(bar["t"].replace("Z", "+00:00")),
                open=bar["o"],
                high=bar["h"],
                low=bar["l"],
                close=bar["c"],
                volume=bar.get("v"),
                source=self.name,
            )
            for bar in bars
        ]

    async def news(self, topics: list[str], since: datetime) -> list[NewsItem]:
        raise NotImplementedError("news is sourced from finnhub, not alpaca")

    async def calendar(self, window: DateRange) -> list[Event]:
        raise NotImplementedError("calendar is sourced from finnhub/fred, not alpaca")

    def cost(self, call: CallSpec) -> int:
        return max(1, len(call.symbols))

    async def _get(self, path: str, params: dict[str, str | int | float]) -> httpx.Response:
        try:
            response = await self._client.get(
                f"{BASE_URL}{path}", params=params, headers=self._headers
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError(f"alpaca request failed: {exc}") from exc
        return response
