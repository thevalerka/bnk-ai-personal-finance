from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.market.providers.base import ProviderError
from app.market.providers.polymarket import PolymarketProvider
from tests.market.conftest import load_fixture


@respx.mock
async def test_probability_matches_macro_markets_and_ignores_unrelated_ones(
    http_client: httpx.AsyncClient,
) -> None:
    fixture = load_fixture("polymarket_markets.json")
    respx.get(url__regex=r"^https://gamma-api\.polymarket\.com/markets.*offset=0.*$").mock(
        return_value=httpx.Response(200, json=fixture)
    )
    respx.get(url__regex=r"^https://gamma-api\.polymarket\.com/markets.*offset=100.*$").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(url__regex=r"^https://gamma-api\.polymarket\.com/markets.*offset=200.*$").mock(
        return_value=httpx.Response(200, json=[])
    )
    provider = PolymarketProvider(http_client)

    markets = await provider.probability()

    # The soccer over/under market is filtered out by the keyword match —
    # only the 2 real Fed markets survive.
    assert len(markets) == 2
    assert markets[0].source == "polymarket"
    top = markets[0]
    assert top.question == (
        "Will the Fed increase interest rates by 50+ bps after the September 2026 meeting?"
    )
    assert top.probability_pct == pytest.approx(0.45)
    assert top.volume_24h == pytest.approx(382746.58725)
    assert top.url == "https://polymarket.com/event/fed-decision-in-september-762"
    assert top.end_date == datetime(2026, 9, 16, tzinfo=UTC)
    # Sorted by 24h volume descending.
    assert markets[1].probability_pct == pytest.approx(75.5)


@respx.mock
async def test_probability_falls_back_to_market_slug_when_no_parent_event(
    http_client: httpx.AsyncClient,
) -> None:
    market = {
        "question": "Fed rate hike in 2026?",
        "slug": "fed-rate-hike-in-2026",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.05", "0.95"]',
        "volume24hr": 69596.0,
        "endDate": "2026-12-09T00:00:00Z",
        "active": True,
        "closed": False,
        "events": [],
    }
    respx.get(url__regex=r"^https://gamma-api\.polymarket\.com/markets.*offset=0.*$").mock(
        return_value=httpx.Response(200, json=[market])
    )
    respx.get(url__regex=r"^https://gamma-api\.polymarket\.com/markets.*offset=100.*$").mock(
        return_value=httpx.Response(200, json=[])
    )
    respx.get(url__regex=r"^https://gamma-api\.polymarket\.com/markets.*offset=200.*$").mock(
        return_value=httpx.Response(200, json=[])
    )
    provider = PolymarketProvider(http_client)

    markets = await provider.probability()

    assert len(markets) == 1
    assert markets[0].url == "https://polymarket.com/event/fed-rate-hike-in-2026"


@respx.mock
async def test_probability_raises_on_http_error(http_client: httpx.AsyncClient) -> None:
    respx.get(url__regex=r"^https://gamma-api\.polymarket\.com/markets.*$").mock(
        return_value=httpx.Response(500)
    )
    provider = PolymarketProvider(http_client)

    with pytest.raises(ProviderError):
        await provider.probability()
