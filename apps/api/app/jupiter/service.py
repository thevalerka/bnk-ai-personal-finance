"""Business logic behind the /jupiter endpoints (app/api/jupiter.py) — kept
out of the router so it's independently testable against a real
transactional Postgres connection, same split as app.trading.service.
"""

import asyncpg

from app.jupiter.schemas import Action, LendFillOut, SwapFillOut

DbConn = asyncpg.pool.PoolConnectionProxy | asyncpg.Connection


async def record_swap_fill(
    conn: DbConn,
    wallet_address: str,
    input_mint: str,
    output_mint: str,
    in_amount: str,
    out_amount: str,
    signature: str,
    platform_fee_bps: int,
) -> SwapFillOut:
    row = await conn.fetchrow(
        "INSERT INTO dex_swaps "
        "(wallet_address, input_mint, output_mint, in_amount, out_amount, "
        "signature, platform_fee_bps) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7) "
        "RETURNING id, wallet_address, input_mint, output_mint, in_amount, out_amount, "
        "signature, platform_fee_bps, created_at",
        wallet_address.lower(),
        input_mint,
        output_mint,
        in_amount,
        out_amount,
        signature,
        platform_fee_bps,
    )
    assert row is not None
    return SwapFillOut(**dict(row))


async def list_swap_fills(conn: DbConn, wallet_address: str, limit: int = 50) -> list[SwapFillOut]:
    rows = await conn.fetch(
        "SELECT id, wallet_address, input_mint, output_mint, in_amount, out_amount, "
        "signature, platform_fee_bps, created_at FROM dex_swaps "
        "WHERE wallet_address = $1 ORDER BY created_at DESC, id DESC LIMIT $2",
        wallet_address.lower(),
        limit,
    )
    return [SwapFillOut(**dict(row)) for row in rows]


async def record_lend_fill(
    conn: DbConn,
    wallet_address: str,
    asset_mint: str,
    action: Action,
    amount: str,
    signature: str,
) -> LendFillOut:
    row = await conn.fetchrow(
        "INSERT INTO lend_positions (wallet_address, asset_mint, action, amount, signature) "
        "VALUES ($1, $2, $3, $4, $5) "
        "RETURNING id, wallet_address, asset_mint, action, amount, signature, created_at",
        wallet_address.lower(),
        asset_mint,
        action,
        amount,
        signature,
    )
    assert row is not None
    return LendFillOut(**dict(row))


async def list_lend_fills(conn: DbConn, wallet_address: str, limit: int = 50) -> list[LendFillOut]:
    rows = await conn.fetch(
        "SELECT id, wallet_address, asset_mint, action, amount, signature, created_at "
        "FROM lend_positions WHERE wallet_address = $1 ORDER BY created_at DESC, id DESC LIMIT $2",
        wallet_address.lower(),
        limit,
    )
    return [LendFillOut(**dict(row)) for row in rows]
