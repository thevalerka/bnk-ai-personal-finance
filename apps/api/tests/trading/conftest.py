from collections.abc import AsyncGenerator

import asyncpg
import httpx
import pytest
from fakeredis import FakeAsyncRedis
from redis.asyncio import Redis

from app.config import get_settings
from app.db import create_pool, init_schema


@pytest.fixture
async def db_pool() -> AsyncGenerator[asyncpg.Pool]:
    pool = await create_pool(get_settings())
    await init_schema(pool)
    yield pool
    await pool.close()


@pytest.fixture
async def db_conn(db_pool: asyncpg.Pool) -> AsyncGenerator[asyncpg.pool.PoolConnectionProxy]:
    async with db_pool.acquire() as conn:
        tr = conn.transaction()
        await tr.start()
        try:
            yield conn
        finally:
            await tr.rollback()


@pytest.fixture
async def redis() -> AsyncGenerator[Redis]:
    client = FakeAsyncRedis()
    yield client
    await client.aclose()


@pytest.fixture
async def http_client() -> AsyncGenerator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client
