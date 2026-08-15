from collections.abc import AsyncGenerator

import asyncpg
import pytest

from app.config import get_settings
from app.db import create_pool, init_schema


@pytest.fixture
async def db_pool() -> AsyncGenerator[asyncpg.Pool]:
    # Function-scoped rather than session-scoped: pytest-asyncio gives each
    # test its own event loop by default, and an asyncpg pool can't cross
    # loops. Recreating it per test is cheap enough at this test count.
    pool = await create_pool(get_settings())
    await init_schema(pool)
    yield pool
    await pool.close()


@pytest.fixture
async def db_conn(db_pool: asyncpg.Pool) -> AsyncGenerator[asyncpg.pool.PoolConnectionProxy]:
    """A connection wrapped in a transaction that's always rolled back, so
    attention tests never leave rows behind in the shared dev database."""
    async with db_pool.acquire() as conn:
        tr = conn.transaction()
        await tr.start()
        try:
            yield conn
        finally:
            await tr.rollback()
