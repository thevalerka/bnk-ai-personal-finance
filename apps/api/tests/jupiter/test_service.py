import asyncpg

from app.jupiter import service


async def test_record_and_list_swap_fills(db_conn: asyncpg.pool.PoolConnectionProxy) -> None:
    await service.record_swap_fill(
        db_conn,
        wallet_address="So1ABC123",
        input_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        output_mint="XsDoVfqeBukxuZHWhdvWHBhgEHjGNst4MLodqsJHzoB",
        in_amount="10000000",
        out_amount="2936789",
        signature="sig-1",
        platform_fee_bps=25,
    )
    await service.record_swap_fill(
        db_conn,
        wallet_address="So1ABC123",
        input_mint="XsDoVfqeBukxuZHWhdvWHBhgEHjGNst4MLodqsJHzoB",
        output_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        in_amount="100000",
        out_amount="34000",
        signature="sig-2",
        platform_fee_bps=25,
    )

    fills = await service.list_swap_fills(db_conn, "so1abc123")

    assert len(fills) == 2
    assert fills[0].signature == "sig-2"  # most recent first
    assert fills[1].signature == "sig-1"


async def test_swap_fills_scoped_to_wallet(db_conn: asyncpg.pool.PoolConnectionProxy) -> None:
    await service.record_swap_fill(
        db_conn,
        wallet_address="So1AAA",
        input_mint="mintA",
        output_mint="mintB",
        in_amount="1",
        out_amount="1",
        signature="sig-aaa",
        platform_fee_bps=0,
    )
    await service.record_swap_fill(
        db_conn,
        wallet_address="So1BBB",
        input_mint="mintA",
        output_mint="mintB",
        in_amount="1",
        out_amount="1",
        signature="sig-bbb",
        platform_fee_bps=0,
    )

    fills = await service.list_swap_fills(db_conn, "so1aaa")

    assert len(fills) == 1
    assert fills[0].signature == "sig-aaa"


async def test_record_and_list_lend_fills(db_conn: asyncpg.pool.PoolConnectionProxy) -> None:
    await service.record_lend_fill(
        db_conn,
        wallet_address="So1ABC123",
        asset_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        action="deposit",
        amount="1000000",
        signature="sig-lend-1",
    )
    await service.record_lend_fill(
        db_conn,
        wallet_address="So1ABC123",
        asset_mint="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        action="withdraw",
        amount="500000",
        signature="sig-lend-2",
    )

    fills = await service.list_lend_fills(db_conn, "so1abc123")

    assert len(fills) == 2
    assert fills[0].action == "withdraw"  # most recent first
    assert fills[1].action == "deposit"
