from datetime import UTC, date, datetime

import httpx
import pytest
import respx

from app.market.providers.base import DateRange
from app.market.providers.fred import FredProvider
from tests.market.conftest import load_fixture


@respx.mock
async def test_quote_returns_latest_observation(http_client: httpx.AsyncClient) -> None:
    respx.get("https://api.stlouisfed.org/fred/series/observations").mock(
        return_value=httpx.Response(200, json=load_fixture("fred_observations.json"))
    )
    provider = FredProvider(http_client, api_key="test-key")

    quotes = await provider.quote(["DGS10"])

    assert quotes[0].symbol == "DGS10"
    assert quotes[0].price == 4.18
    assert quotes[0].ts.date() == date(2024, 1, 25)


@respx.mock
async def test_candles_skip_missing_value_marker(http_client: httpx.AsyncClient) -> None:
    respx.get("https://api.stlouisfed.org/fred/series/observations").mock(
        return_value=httpx.Response(200, json=load_fixture("fred_observations.json"))
    )
    provider = FredProvider(http_client, api_key="test-key")

    candles = await provider.candles("DGS10", tf="1d", limit=3)

    # the fixture has 3 rows but one value is "." (missing) and must be dropped
    assert len(candles) == 2
    assert candles[0].open == candles[0].high == candles[0].low == candles[0].close
    assert [c.ts.date() for c in candles] == [date(2024, 1, 24), date(2024, 1, 25)]


@respx.mock
async def test_calendar_parses_release_dates(http_client: httpx.AsyncClient) -> None:
    respx.get("https://api.stlouisfed.org/fred/releases/dates").mock(
        return_value=httpx.Response(200, json=load_fixture("fred_releases.json"))
    )
    provider = FredProvider(http_client, api_key="test-key")

    events = await provider.calendar(DateRange(start=date(2024, 1, 1), end=date(2024, 3, 1)))

    assert events[0].kind == "macro_release"
    assert events[0].title == "Employment Situation"


async def test_news_raises_not_implemented(http_client: httpx.AsyncClient) -> None:
    provider = FredProvider(http_client, api_key="test-key")

    with pytest.raises(NotImplementedError):
        await provider.news([], since=datetime.now(tz=UTC))
