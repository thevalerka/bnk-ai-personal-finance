from redis.asyncio import Redis

from app.market.budget import BudgetManager, ProviderBudget


async def test_allows_calls_under_capacity(redis: Redis) -> None:
    budget = BudgetManager(redis, {"finnhub": ProviderBudget(capacity=2, window_seconds=60)})

    assert await budget.try_consume("finnhub") is True
    assert await budget.try_consume("finnhub") is True


async def test_denies_calls_once_capacity_is_exhausted(redis: Redis) -> None:
    budget = BudgetManager(redis, {"finnhub": ProviderBudget(capacity=2, window_seconds=60)})

    assert await budget.try_consume("finnhub") is True
    assert await budget.try_consume("finnhub") is True
    assert await budget.try_consume("finnhub") is False


async def test_unconfigured_provider_is_unrestricted(redis: Redis) -> None:
    budget = BudgetManager(redis, {})

    for _ in range(50):
        assert await budget.try_consume("some-new-provider") is True


async def test_multi_unit_calls_consume_proportionally(redis: Redis) -> None:
    budget = BudgetManager(redis, {"finnhub": ProviderBudget(capacity=5, window_seconds=60)})

    assert await budget.try_consume("finnhub", units=3) is True
    assert await budget.try_consume("finnhub", units=3) is False
