from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.market.providers.binance import BinanceProvider
from tests.market.conftest import load_fixture


@respx.mock
async def test_quote_maps_canonical_symbol_to_usdt_pair(http_client: httpx.AsyncClient) -> None:
    route = respx.get("https://api.binance.com/api/v3/ticker/price").mock(
        return_value=httpx.Response(200, json=load_fixture("binance_ticker_multi.json"))
    )
    provider = BinanceProvider(http_client)

    quotes = await provider.quote(["BTC", "ETH"])

    assert route.calls.last.request.url.params["symbols"] == '["BTCUSDT", "ETHUSDT"]'
    assert {q.symbol for q in quotes} == {"BTC", "ETH"}
    assert next(q for q in quotes if q.symbol == "BTC").price == 43250.12


@respx.mock
async def test_candles_parses_klines(http_client: httpx.AsyncClient) -> None:
    respx.get("https://api.binance.com/api/v3/klines").mock(
        return_value=httpx.Response(200, json=load_fixture("binance_klines.json"))
    )
    provider = BinanceProvider(http_client)

    candles = await provider.candles("BTC", tf="1h", limit=1)

    assert candles[0].symbol == "BTC"
    assert candles[0].close == 43250.12
    assert candles[0].volume == 1234.56


async def test_news_and_calendar_raise_not_implemented(http_client: httpx.AsyncClient) -> None:
    provider = BinanceProvider(http_client)

    with pytest.raises(NotImplementedError):
        await provider.news([], since=datetime.now(tz=UTC))
