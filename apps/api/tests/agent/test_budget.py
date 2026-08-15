from redis.asyncio import Redis

from app.agent.budget import AgentBudget


async def test_has_budget_true_when_nothing_spent_yet(redis: Redis) -> None:
    budget = AgentBudget(redis, monthly_token_budget=1000, rate_limit_per_minute=10)
    assert await budget.has_budget() is True


async def test_record_spend_accumulates_and_trips_the_budget(redis: Redis) -> None:
    budget = AgentBudget(redis, monthly_token_budget=100, rate_limit_per_minute=10)
    await budget.record_spend(input_tokens=40, output_tokens=40)
    assert await budget.has_budget() is True
    await budget.record_spend(input_tokens=15, output_tokens=15)
    assert await budget.has_budget() is False


async def test_rate_limit_allows_up_to_the_configured_count(redis: Redis) -> None:
    budget = AgentBudget(redis, monthly_token_budget=1000, rate_limit_per_minute=3)
    results = [await budget.try_consume_request("profile-a") for _ in range(4)]
    assert results == [True, True, True, False]


async def test_rate_limit_is_scoped_per_profile(redis: Redis) -> None:
    budget = AgentBudget(redis, monthly_token_budget=1000, rate_limit_per_minute=1)
    assert await budget.try_consume_request("profile-a") is True
    # A second profile isn't blocked by the first one's limit.
    assert await budget.try_consume_request("profile-b") is True
    assert await budget.try_consume_request("profile-a") is False
