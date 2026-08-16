"""Per-wallet rate limit on the logging endpoints (`/trading/fills`,
`/trading/approvals`) — the actual order signing/submission happens against
Hyperliquid directly from the browser and is rate-limited by Hyperliquid
itself, so this isn't guarding trading activity. It's guarding our own
Postgres from one wallet hammering the log endpoints. Same fixed-window
Redis INCR/EXPIRE idiom as `app.agent.budget.AgentBudget.try_consume_request`,
just keyed by wallet address instead of profile_id.
"""

from redis.asyncio import Redis


class TradingBudget:
    def __init__(self, redis: Redis, rate_limit_per_minute: int) -> None:
        self._redis = redis
        self._rate_limit_per_minute = rate_limit_per_minute

    async def try_consume_request(self, wallet_address: str) -> bool:
        key = f"trading:ratelimit:{wallet_address.lower()}"
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, 60)
        return count <= self._rate_limit_per_minute
