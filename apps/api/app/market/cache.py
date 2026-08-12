import json
from dataclasses import dataclass
from datetime import UTC, datetime

from redis.asyncio import Redis

STALE_MAX_SECONDS = 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class CacheEntry:
    payload: list[dict[str, object]]
    is_fresh: bool


class Cache:
    """Redis-backed cache that remembers *how* stale an entry is.

    Entries live in Redis for up to `STALE_MAX_SECONDS` regardless of the
    caller's freshness window, so the Router can still serve a stale-but-
    present entry when a provider is out of budget or failing, instead of
    losing the data the moment its normal TTL expires.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get(self, key: str, fresh_ttl_seconds: int) -> CacheEntry | None:
        raw = await self._redis.get(key)
        if raw is None:
            return None
        record = json.loads(raw)
        cached_at = datetime.fromisoformat(record["cached_at"])
        age_seconds = (datetime.now(tz=UTC) - cached_at).total_seconds()
        return CacheEntry(payload=record["payload"], is_fresh=age_seconds <= fresh_ttl_seconds)

    async def set(self, key: str, payload: list[dict[str, object]]) -> None:
        record = {"cached_at": datetime.now(tz=UTC).isoformat(), "payload": payload}
        await self._redis.set(key, json.dumps(record), ex=STALE_MAX_SECONDS)
