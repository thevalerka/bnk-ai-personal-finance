from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.market.providers.base import ProviderError
from app.market.providers.hyperliquid import HyperliquidProvider
from tests.market.conftest import load_fixture


@respx.mock
async def test_quote_reads_all_mids(http_client: httpx.AsyncClient) -> None:
    respx.post("https://api.hyperliquid.xyz/info").mock(
        return_value=httpx.Response(200, json=load_fixture("hyperliquid_all_mids.json"))
    )
    provider = HyperliquidProvider(http_client)

    quotes = await provider.quote(["BTC"])

    assert quotes[0].symbol == "BTC"
    assert quotes[0].price == 43250.5
    assert quotes[0].source == "hyperliquid"


@respx.mock
async def test_quote_raises_for_unknown_coin(http_client: httpx.AsyncClient) -> None:
    respx.post("https://api.hyperliquid.xyz/info").mock(
        return_value=httpx.Response(200, json=load_fixture("hyperliquid_all_mids.json"))
    )
    provider = HyperliquidProvider(http_client)

    with pytest.raises(ProviderError):
        await provider.quote(["DOGE"])


@respx.mock
async def test_candles_parses_snapshot(http_client: httpx.AsyncClient) -> None:
    respx.post("https://api.hyperliquid.xyz/info").mock(
        return_value=httpx.Response(200, json=load_fixture("hyperliquid_candles.json"))
    )
    provider = HyperliquidProvider(http_client)

    candles = await provider.candles("BTC", tf="1h", limit=1)

    assert candles[0].close == 43250.5


async def test_candles_rejects_unsupported_interval(http_client: httpx.AsyncClient) -> None:
    provider = HyperliquidProvider(http_client)

    with pytest.raises(ProviderError):
        await provider.candles("BTC", tf="7m", limit=1)


async def test_news_and_calendar_raise_not_implemented(http_client: httpx.AsyncClient) -> None:
    provider = HyperliquidProvider(http_client)

    with pytest.raises(NotImplementedError):
        await provider.news([], since=datetime.now(tz=UTC))
