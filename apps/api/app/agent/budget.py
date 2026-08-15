"""Cost control for the agent endpoint (docs/PLAN.md section 5.3): a hard
monthly token budget so a public prompt bar can't run up an unbounded bill,
plus a per-profile rate limit so one visitor can't hammer it. Same
fixed-window Redis counter pattern as app.market.budget.BudgetManager, just
keyed differently (calendar month instead of a rolling window, and
input+output token count instead of call count).
"""

from datetime import UTC, datetime

from redis.asyncio import Redis


def _month_key(now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return f"agent:tokens:{now.year:04d}-{now.month:02d}"


class AgentBudget:
    def __init__(self, redis: Redis, monthly_token_budget: int, rate_limit_per_minute: int) -> None:
        self._redis = redis
        self._monthly_token_budget = monthly_token_budget
        self._rate_limit_per_minute = rate_limit_per_minute

    async def has_budget(self) -> bool:
        """Read-only check before starting a turn — spending tokens on a
        request we're about to refuse mid-stream would be worse than
        refusing it up front."""
        spent = await self._redis.get(_month_key())
        return int(spent or 0) < self._monthly_token_budget

    async def record_spend(self, input_tokens: int, output_tokens: int) -> None:
        key = _month_key()
        new_total = await self._redis.incrby(key, input_tokens + output_tokens)
        if new_total == input_tokens + output_tokens:
            # First write of the month — expire in ~35 days so the key
            # self-cleans instead of accumulating one Redis key forever.
            await self._redis.expire(key, 35 * 24 * 3600)

    async def try_consume_request(self, profile_id: str) -> bool:
        """Per-profile requests/minute — the public-site abuse surface this
        is actually guarding against (plan 5.3): one visitor's browser
        looping the prompt bar, not overall traffic (that's the monthly
        token budget's job)."""
        key = f"agent:ratelimit:{profile_id}"
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, 60)
        return count <= self._rate_limit_per_minute
