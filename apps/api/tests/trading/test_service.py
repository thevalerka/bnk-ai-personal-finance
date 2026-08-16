import asyncpg

from app.trading import service


async def test_record_and_list_approval(db_conn: asyncpg.pool.PoolConnectionProxy) -> None:
    out = await service.record_approval(db_conn, "0xABC123", max_fee_tenths_bp=10)

    assert out.wallet_address == "0xabc123"
    assert out.max_fee_tenths_bp == 10


async def test_record_and_list_fills(db_conn: asyncpg.pool.PoolConnectionProxy) -> None:
    await service.record_fill(
        db_conn,
        wallet_address="0xABC123",
        coin="BTC",
        side="buy",
        size=0.01,
        price=65000.0,
        builder_fee_tenths_bp=10,
    )
    await service.record_fill(
        db_conn,
        wallet_address="0xABC123",
        coin="ETH",
        side="sell",
        size=1.0,
        price=3200.0,
        builder_fee_tenths_bp=10,
    )

    fills = await service.list_fills(db_conn, "0xabc123")

    assert len(fills) == 2
    assert fills[0].coin == "ETH"  # most recent first
    assert fills[1].coin == "BTC"


async def test_list_fills_scoped_to_wallet(db_conn: asyncpg.pool.PoolConnectionProxy) -> None:
    await service.record_fill(
        db_conn,
        wallet_address="0xAAA",
        coin="BTC",
        side="buy",
        size=0.01,
        price=65000.0,
        builder_fee_tenths_bp=10,
    )
    await service.record_fill(
        db_conn,
        wallet_address="0xBBB",
        coin="ETH",
        side="buy",
        size=1.0,
        price=3200.0,
        builder_fee_tenths_bp=10,
    )

    fills = await service.list_fills(db_conn, "0xaaa")

    assert len(fills) == 1
    assert fills[0].coin == "BTC"
