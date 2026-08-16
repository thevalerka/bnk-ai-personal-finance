from collections.abc import Generator

import asyncpg
import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from app.config import get_settings
from app.main import app
from app.trading.budget import TradingBudget
from app.trading.gateway import TradingGateway


class FakeExchangeClient:
    def __init__(self, exists: bool = True) -> None:
        self.exists = exists
        self.calls: list[tuple[str, int]] = []

    async def order_exists(self, wallet_address: str, order_id: int) -> bool:
        self.calls.append((wallet_address, order_id))
        return self.exists


def _install_fake_gateway(
    redis: Redis, *, exists: bool = True, configured: bool = True, rate_limit: int = 20
) -> FakeExchangeClient:
    exchange = FakeExchangeClient(exists=exists)
    app.state.trading_gateway = TradingGateway(
        exchange=exchange,  # type: ignore[arg-type]
        budget=TradingBudget(redis, rate_limit),
        builder_address="0xBUILDER" if configured else "",
        builder_fee_tenths_bp=10,
        testnet_base_url="https://api.hyperliquid-testnet.xyz",
    )
    return exchange


@pytest.fixture
def client(redis: Redis) -> Generator[TestClient]:
    with TestClient(app) as c:
        _install_fake_gateway(redis)
        yield c

    async def _cleanup() -> None:
        conn = await asyncpg.connect(dsn=get_settings().database_url)
        try:
            await conn.execute("DELETE FROM builder_approvals WHERE wallet_address = $1", "0xabc")
            await conn.execute("DELETE FROM order_fills WHERE wallet_address = $1", "0xabc")
        finally:
            await conn.close()

    import anyio

    anyio.run(_cleanup)


def test_config_reports_configured_when_builder_address_is_set(client: TestClient) -> None:
    response = client.get("/trading/config")

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["builder_address"] == "0xBUILDER"


def test_config_reports_unconfigured_when_builder_address_is_blank(redis: Redis) -> None:
    with TestClient(app) as c:
        _install_fake_gateway(redis, configured=False)
        response = c.get("/trading/config")

    assert response.json()["configured"] is False


def test_post_approval_records_it(client: TestClient) -> None:
    response = client.post(
        "/trading/approvals", json={"wallet_address": "0xABC", "max_fee_tenths_bp": 10}
    )

    assert response.status_code == 200
    assert response.json()["wallet_address"] == "0xabc"


def test_post_fill_rejects_a_fill_hyperliquid_does_not_know_about(redis: Redis) -> None:
    with TestClient(app) as c:
        _install_fake_gateway(redis, exists=False)
        response = c.post(
            "/trading/fills",
            json={
                "wallet_address": "0xABC",
                "coin": "BTC",
                "side": "buy",
                "size": 0.01,
                "price": 65000.0,
                "order_id": 1,
            },
        )

    assert response.status_code == 422


def test_post_fill_records_a_verified_fill_and_lists_it(client: TestClient) -> None:
    post_response = client.post(
        "/trading/fills",
        json={
            "wallet_address": "0xABC",
            "coin": "BTC",
            "side": "buy",
            "size": 0.01,
            "price": 65000.0,
            "order_id": 1,
        },
    )
    assert post_response.status_code == 200

    list_response = client.get("/trading/orders", params={"wallet": "0xabc"})

    assert list_response.status_code == 200
    fills = list_response.json()
    assert len(fills) == 1
    assert fills[0]["coin"] == "BTC"
    assert fills[0]["builder_fee_tenths_bp"] == 10


def test_fill_rate_limit_returns_429(redis: Redis) -> None:
    with TestClient(app) as c:
        _install_fake_gateway(redis, rate_limit=1)
        first = c.post(
            "/trading/fills",
            json={
                "wallet_address": "0xABC",
                "coin": "BTC",
                "side": "buy",
                "size": 0.01,
                "price": 65000.0,
                "order_id": 1,
            },
        )
        second = c.post(
            "/trading/fills",
            json={
                "wallet_address": "0xABC",
                "coin": "BTC",
                "side": "buy",
                "size": 0.01,
                "price": 65000.0,
                "order_id": 2,
            },
        )

    assert first.status_code == 200
    assert second.status_code == 429

    async def _cleanup() -> None:
        conn = await asyncpg.connect(dsn=get_settings().database_url)
        try:
            await conn.execute("DELETE FROM order_fills WHERE wallet_address = $1", "0xabc")
        finally:
            await conn.close()

    import anyio

    anyio.run(_cleanup)
