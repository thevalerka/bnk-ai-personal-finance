from datetime import UTC, date, datetime

import httpx
import pytest
import respx

from app.market.providers.alpaca import AlpacaProvider
from app.market.providers.base import DateRange, ProviderError
from tests.market.conftest import load_fixture


@respx.mock
async def test_quote_parses_latest_trade(http_client: httpx.AsyncClient) -> None:
    respx.get("https://data.alpaca.markets/v2/stocks/trades/latest").mock(
        return_value=httpx.Response(200, json=load_fixture("alpaca_trades_latest.json"))
    )
    provider = AlpacaProvider(http_client, api_key="key", api_secret="secret")

    quotes = await provider.quote(["AAPL"])

    assert quotes[0].symbol == "AAPL"
    assert quotes[0].price == 195.5
    assert quotes[0].source == "alpaca"


@respx.mock
async def test_quote_raises_when_symbol_missing_from_response(
    http_client: httpx.AsyncClient,
) -> None:
    respx.get("https://data.alpaca.markets/v2/stocks/trades/latest").mock(
        return_value=httpx.Response(200, json={"trades": {}})
    )
    provider = AlpacaProvider(http_client, api_key="key", api_secret="secret")

    with pytest.raises(ProviderError):
        await provider.quote(["AAPL"])


@respx.mock
async def test_candles_parses_bars(http_client: httpx.AsyncClient) -> None:
    respx.get("https://data.alpaca.markets/v2/stocks/AAPL/bars").mock(
        return_value=httpx.Response(200, json=load_fixture("alpaca_bars.json"))
    )
    provider = AlpacaProvider(http_client, api_key="key", api_secret="secret")

    candles = await provider.candles("AAPL", tf="1d", limit=1)

    assert candles[0].close == 195.5
    assert candles[0].volume == 123456


async def test_news_and_calendar_raise_not_implemented(http_client: httpx.AsyncClient) -> None:
    provider = AlpacaProvider(http_client, api_key="key", api_secret="secret")

    with pytest.raises(NotImplementedError):
        await provider.news([], since=datetime.now(tz=UTC))
    with pytest.raises(NotImplementedError):
        await provider.calendar(DateRange(start=date(2024, 1, 1), end=date(2024, 2, 1)))
