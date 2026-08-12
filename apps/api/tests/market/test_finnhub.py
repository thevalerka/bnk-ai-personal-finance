from datetime import UTC, date, datetime

import httpx
import pytest
import respx

from app.market.providers.base import DateRange, ProviderError
from app.market.providers.finnhub import FinnhubProvider
from tests.market.conftest import load_fixture


@respx.mock
async def test_quote_parses_finnhub_response(http_client: httpx.AsyncClient) -> None:
    respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(200, json=load_fixture("finnhub_quote.json"))
    )
    provider = FinnhubProvider(http_client, api_key="test-key")

    quotes = await provider.quote(["AAPL"])

    assert len(quotes) == 1
    assert quotes[0].symbol == "AAPL"
    assert quotes[0].price == 195.5
    assert quotes[0].change == 1.2
    assert quotes[0].source == "finnhub"


@respx.mock
async def test_quote_raises_provider_error_when_symbol_unknown(
    http_client: httpx.AsyncClient,
) -> None:
    respx.get("https://finnhub.io/api/v1/quote").mock(
        return_value=httpx.Response(
            200, json={"c": 0, "d": None, "dp": None, "h": 0, "l": 0, "o": 0, "pc": 0, "t": 0}
        )
    )
    provider = FinnhubProvider(http_client, api_key="test-key")

    with pytest.raises(ProviderError):
        await provider.quote(["NOTASYMBOL"])


@respx.mock
async def test_quote_raises_provider_error_on_http_failure(http_client: httpx.AsyncClient) -> None:
    respx.get("https://finnhub.io/api/v1/quote").mock(return_value=httpx.Response(500))
    provider = FinnhubProvider(http_client, api_key="test-key")

    with pytest.raises(ProviderError):
        await provider.quote(["AAPL"])


@respx.mock
async def test_news_filters_out_items_older_than_since(http_client: httpx.AsyncClient) -> None:
    respx.get("https://finnhub.io/api/v1/company-news").mock(
        return_value=httpx.Response(200, json=load_fixture("finnhub_news.json"))
    )
    provider = FinnhubProvider(http_client, api_key="test-key")

    items = await provider.news(["AAPL"], since=datetime(2024, 1, 1, tzinfo=UTC))

    assert len(items) == 1
    assert items[0].headline == "Apple beats quarterly estimates"
    assert items[0].tickers == ["AAPL"]


@respx.mock
async def test_calendar_parses_earnings(http_client: httpx.AsyncClient) -> None:
    respx.get("https://finnhub.io/api/v1/calendar/earnings").mock(
        return_value=httpx.Response(200, json=load_fixture("finnhub_calendar.json"))
    )
    provider = FinnhubProvider(http_client, api_key="test-key")

    events = await provider.calendar(DateRange(start=date(2024, 1, 1), end=date(2024, 2, 1)))

    assert events[0].kind == "earnings"
    assert events[0].tickers == ["AAPL"]


async def test_candles_raise_not_implemented(http_client: httpx.AsyncClient) -> None:
    provider = FinnhubProvider(http_client, api_key="test-key")

    with pytest.raises(NotImplementedError):
        await provider.candles("AAPL", "1d", 10)
