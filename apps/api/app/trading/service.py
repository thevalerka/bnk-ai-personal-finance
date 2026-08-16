"""Business logic behind the /trading endpoints (app/api/trading.py) — kept
out of the router so it's independently testable against a real
transactional Postgres connection, same split as app.attention.service.
"""

import asyncpg

from app.trading.schemas import ApprovalOut, FillOut, Side

DbConn = asyncpg.pool.PoolConnectionProxy | asyncpg.Connection


async def record_approval(conn: DbConn, wallet_address: str, max_fee_tenths_bp: int) -> ApprovalOut:
    row = await conn.fetchrow(
        "INSERT INTO builder_approvals (wallet_address, max_fee_tenths_bp) "
        "VALUES ($1, $2) RETURNING wallet_address, max_fee_tenths_bp, approved_at",
        wallet_address.lower(),
        max_fee_tenths_bp,
    )
    assert row is not None
    return ApprovalOut(**dict(row))


async def record_fill(
    conn: DbConn,
    wallet_address: str,
    coin: str,
    side: Side,
    size: float,
    price: float,
    builder_fee_tenths_bp: int,
) -> FillOut:
    row = await conn.fetchrow(
        "INSERT INTO order_fills "
        "(wallet_address, coin, side, size, price, builder_fee_tenths_bp) "
        "VALUES ($1, $2, $3, $4, $5, $6) "
        "RETURNING id, wallet_address, coin, side, size, price, builder_fee_tenths_bp, created_at",
        wallet_address.lower(),
        coin,
        side,
        size,
        price,
        builder_fee_tenths_bp,
    )
    assert row is not None
    return FillOut(**dict(row))


async def list_fills(conn: DbConn, wallet_address: str, limit: int = 50) -> list[FillOut]:
    rows = await conn.fetch(
        "SELECT id, wallet_address, coin, side, size, price, builder_fee_tenths_bp, created_at "
        "FROM order_fills WHERE wallet_address = $1 ORDER BY created_at DESC, id DESC LIMIT $2",
        wallet_address.lower(),
        limit,
    )
    return [FillOut(**dict(row)) for row in rows]
