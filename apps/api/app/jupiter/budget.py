"""Per-wallet rate limit on the `/jupiter/*-fills` logging endpoints — same
role and idiom as `app.trading.budget.TradingBudget`, kept as its own class
(distinct Redis key prefix) rather than reused so a wallet hammering the
Jupiter log endpoints doesn't also burn its Hyperliquid budget or vice
versa. The actual swap/deposit signing happens client-side against Solana
directly, which this doesn't gate at all — it only protects our own
Postgres from log-endpoint spam.
"""

from redis.asyncio import Redis


class JupiterBudget:
    def __init__(self, redis: Redis, rate_limit_per_minute: int) -> None:
        self._redis = redis
        self._rate_limit_per_minute = rate_limit_per_minute

    async def try_consume_request(self, wallet_address: str) -> bool:
        key = f"jupiter:ratelimit:{wallet_address.lower()}"
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, 60)
        return count <= self._rate_limit_per_minute
