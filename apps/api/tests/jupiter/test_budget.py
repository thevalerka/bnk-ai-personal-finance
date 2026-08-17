from redis.asyncio import Redis

from app.jupiter.budget import JupiterBudget


async def test_allows_up_to_the_limit(redis: Redis) -> None:
    budget = JupiterBudget(redis, rate_limit_per_minute=3)

    results = [await budget.try_consume_request("So1ABC") for _ in range(3)]

    assert results == [True, True, True]


async def test_blocks_past_the_limit(redis: Redis) -> None:
    budget = JupiterBudget(redis, rate_limit_per_minute=2)

    results = [await budget.try_consume_request("So1ABC") for _ in range(3)]

    assert results == [True, True, False]


async def test_keys_are_case_insensitive_per_wallet(redis: Redis) -> None:
    budget = JupiterBudget(redis, rate_limit_per_minute=1)

    first = await budget.try_consume_request("So1AbC")
    second = await budget.try_consume_request("so1abc")

    assert first is True
    assert second is False
