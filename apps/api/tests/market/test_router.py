from datetime import UTC, date, datetime

import pytest
from redis.asyncio import Redis

from app.market.budget import BudgetManager, ProviderBudget
from app.market.cache import Cache
from app.market.providers.base import DateRange
from app.market.router import MarketDataUnavailable, Router
from tests.market.conftest import FakeProvider, ProviderError


async def test_falls_back_to_next_provider_when_primary_errors(redis: Redis) -> None:
    primary = FakeProvider("primary", error=ProviderError("primary is down"))
    secondary = FakeProvider("secondary")
    router = Router(
        providers={"primary": primary, "secondary": secondary},
        chains={"cap": ["primary", "secondary"]},
        budget=BudgetManager(redis, {}),
        cache=Cache(redis),
    )

    quotes = await router.quote("cap", ["AAPL"])

    assert quotes[0].source == "secondary"
    assert primary.calls == 1
    assert secondary.calls == 1


async def test_budget_breach_with_no_cache_never_calls_the_vendor(redis: Redis) -> None:
    provider = FakeProvider("primary")
    router = Router(
        providers={"primary": provider},
        chains={"cap": ["primary"]},
        budget=BudgetManager(redis, {"primary": ProviderBudget(capacity=0, window_seconds=60)}),
        cache=Cache(redis),
    )

    with pytest.raises(MarketDataUnavailable):
        await router.quote("cap", ["AAPL"])

    assert provider.calls == 0


async def test_budget_breach_serves_stale_cache_instead_of_calling_the_vendor(
    redis: Redis,
) -> None:
    provider = FakeProvider("primary")
    # capacity=1: the first call is allowed and populates the cache; every
    # call after that is a breach and must be served from that stale entry.
    router = Router(
        providers={"primary": provider},
        chains={"cap": ["primary"]},
        budget=BudgetManager(redis, {"primary": ProviderBudget(capacity=1, window_seconds=60)}),
        cache=Cache(redis),
        fresh_ttl_seconds=0,
    )

    first = await router.quote("cap", ["AAPL"])
    assert provider.calls == 1

    second = await router.quote("cap", ["AAPL"])

    assert provider.calls == 1  # no second vendor call once over budget
    assert second[0].price == first[0].price
    assert second[0].source == "primary"


async def test_fresh_cache_is_served_without_calling_the_vendor_again(redis: Redis) -> None:
    provider = FakeProvider("primary")
    router = Router(
        providers={"primary": provider},
        chains={"cap": ["primary"]},
        budget=BudgetManager(redis, {}),
        cache=Cache(redis),
        fresh_ttl_seconds=300,
    )

    await router.quote("cap", ["AAPL"])
    await router.quote("cap", ["AAPL"])

    assert provider.calls == 1


async def test_raises_when_capability_has_no_configured_chain(redis: Redis) -> None:
    router = Router(
        providers={},
        chains={},
        budget=BudgetManager(redis, {}),
        cache=Cache(redis),
    )

    with pytest.raises(MarketDataUnavailable):
        await router.quote("unknown-capability", ["AAPL"])


async def test_candles_falls_back_and_caches_like_quote(redis: Redis) -> None:
    primary = FakeProvider("primary", error=ProviderError("primary is down"))
    secondary = FakeProvider("secondary")
    router = Router(
        providers={"primary": primary, "secondary": secondary},
        chains={"cap": ["primary", "secondary"]},
        budget=BudgetManager(redis, {}),
        cache=Cache(redis),
        fresh_ttl_seconds=300,
    )

    first = await router.candles("cap", "AAPL", "1d", 10)
    await router.candles("cap", "AAPL", "1d", 10)

    assert first[0].source == "secondary"
    assert secondary.calls == 1  # second call served from cache


async def test_news_uses_its_own_ttl(redis: Redis) -> None:
    provider = FakeProvider("primary")
    router = Router(
        providers={"primary": provider},
        chains={"cap": ["primary"]},
        budget=BudgetManager(redis, {}),
        cache=Cache(redis),
        news_ttl_seconds=300,
    )

    await router.news("cap", ["ai"], datetime.now(tz=UTC))
    await router.news("cap", ["ai"], datetime.now(tz=UTC))

    assert provider.calls == 1


async def test_calendar_uses_its_own_ttl(redis: Redis) -> None:
    provider = FakeProvider("primary")
    router = Router(
        providers={"primary": provider},
        chains={"cap": ["primary"]},
        budget=BudgetManager(redis, {}),
        cache=Cache(redis),
        calendar_ttl_seconds=3600,
    )
    window = DateRange(start=date(2026, 1, 1), end=date(2026, 1, 31))

    await router.calendar("cap", window)
    await router.calendar("cap", window)

    assert provider.calls == 1


async def test_candles_raises_when_every_provider_is_unreachable(redis: Redis) -> None:
    provider = FakeProvider("primary", error=ProviderError("down"))
    router = Router(
        providers={"primary": provider},
        chains={"cap": ["primary"]},
        budget=BudgetManager(redis, {}),
        cache=Cache(redis),
    )

    with pytest.raises(MarketDataUnavailable):
        await router.candles("cap", "AAPL", "1d", 10)
