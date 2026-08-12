from dataclasses import dataclass

from redis.asyncio import Redis


@dataclass(frozen=True, slots=True)
class ProviderBudget:
    capacity: int
    window_seconds: int


class BudgetManager:
    """Fixed-window per-provider call budget backed by Redis.

    Simpler than a true token bucket (bursty right at window boundaries) but
    enforces the same "never exceed N calls per window" contract with one
    INCR + one conditional EXPIRE per call. A provider with no configured
    budget is treated as unrestricted, which keeps ad-hoc/dev providers
    usable without forcing every entry to appear in config/budgets.yaml.
    """

    def __init__(self, redis: Redis, limits: dict[str, ProviderBudget]) -> None:
        self._redis = redis
        self._limits = limits

    async def try_consume(self, provider: str, units: int = 1) -> bool:
        limit = self._limits.get(provider)
        if limit is None:
            return True
        key = f"budget:{provider}"
        new_value = await self._redis.incrby(key, units)
        if new_value == units:
            await self._redis.expire(key, limit.window_seconds)
        return new_value <= limit.capacity
