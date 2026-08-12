import json
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis

from app.market.cache import Cache


async def test_get_returns_none_when_missing(redis: Redis) -> None:
    cache = Cache(redis)

    assert await cache.get("missing-key", fresh_ttl_seconds=30) is None


async def test_set_then_get_is_fresh_within_ttl(redis: Redis) -> None:
    cache = Cache(redis)

    await cache.set("k", [{"symbol": "AAPL"}])
    entry = await cache.get("k", fresh_ttl_seconds=30)

    assert entry is not None
    assert entry.is_fresh
    assert entry.payload == [{"symbol": "AAPL"}]


async def test_entry_older_than_ttl_is_reported_stale_but_still_returned(redis: Redis) -> None:
    cache = Cache(redis)
    old_record = {
        "cached_at": (datetime.now(tz=UTC) - timedelta(seconds=120)).isoformat(),
        "payload": [{"symbol": "AAPL"}],
    }
    await redis.set("k", json.dumps(old_record))

    entry = await cache.get("k", fresh_ttl_seconds=30)

    assert entry is not None
    assert not entry.is_fresh
    assert entry.payload == [{"symbol": "AAPL"}]
