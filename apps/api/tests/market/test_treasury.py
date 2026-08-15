from datetime import UTC, date, datetime

import httpx
import pytest
import respx

from app.market.providers.base import DateRange, ProviderError
from app.market.providers.treasury import TreasuryProvider
from tests.market.conftest import load_fixture


@respx.mock
async def test_calendar_parses_auctions_into_events(http_client: httpx.AsyncClient) -> None:
    respx.get(
        "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query"
    ).mock(return_value=httpx.Response(200, json=load_fixture("treasury_auctions.json")))
    provider = TreasuryProvider(http_client)

    events = await provider.calendar(DateRange(start=date(2026, 8, 14), end=date(2026, 9, 14)))

    assert len(events) == 2
    assert events[0].kind == "auction"
    assert events[0].source == "treasury"
    assert events[0].title == "26-Week Bill auction"
    assert events[0].tickers == ["912797TV9"]


@respx.mock
async def test_calendar_raises_on_http_error(http_client: httpx.AsyncClient) -> None:
    respx.get(
        "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query"
    ).mock(return_value=httpx.Response(500))
    provider = TreasuryProvider(http_client)

    with pytest.raises(ProviderError):
        await provider.calendar(DateRange(start=date(2026, 8, 14), end=date(2026, 9, 14)))


async def test_quote_candles_news_raise_not_implemented(http_client: httpx.AsyncClient) -> None:
    provider = TreasuryProvider(http_client)

    with pytest.raises(NotImplementedError):
        await provider.quote(["AAPL"])
    with pytest.raises(NotImplementedError):
        await provider.candles("AAPL", tf="1d", limit=10)
    with pytest.raises(NotImplementedError):
        await provider.news([], since=datetime.now(tz=UTC))
