from redis.asyncio import Redis

from app.trading.budget import TradingBudget


async def test_allows_up_to_the_limit(redis: Redis) -> None:
    budget = TradingBudget(redis, rate_limit_per_minute=3)

    results = [await budget.try_consume_request("0xABC") for _ in range(3)]

    assert results == [True, True, True]


async def test_blocks_past_the_limit(redis: Redis) -> None:
    budget = TradingBudget(redis, rate_limit_per_minute=2)

    results = [await budget.try_consume_request("0xABC") for _ in range(3)]

    assert results == [True, True, False]


async def test_keys_are_case_insensitive_per_wallet(redis: Redis) -> None:
    budget = TradingBudget(redis, rate_limit_per_minute=1)

    first = await budget.try_consume_request("0xAbC")
    second = await budget.try_consume_request("0xabc")

    assert first is True
    assert second is False
