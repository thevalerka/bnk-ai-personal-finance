"""Postgres access — the attention engine's only stateful store (docs/PLAN.md
section 4). Raw asyncpg rather than an ORM: this codebase doesn't use one
anywhere else (the Provider Protocol classes are the equivalent "boring,
inspectable" choice for the market gateway — see CLAUDE.md), and the schema
is three tables (db/schema.sql).
"""

from pathlib import Path

import asyncpg

from app.config import Settings

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "db" / "schema.sql"


async def create_pool(settings: Settings) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(dsn=settings.database_url)
    if pool is None:  # pragma: no cover - asyncpg only returns None when closing
        raise RuntimeError("failed to create asyncpg pool")
    return pool


async def init_schema(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA_PATH.read_text())
