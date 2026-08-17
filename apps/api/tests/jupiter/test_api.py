from collections.abc import Generator

import asyncpg
import httpx
import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from app.config import get_settings
from app.jupiter.budget import JupiterBudget
from app.jupiter.gateway import JupiterGateway
from app.main import app
from app.market.budget import BudgetManager
from app.market.cache import Cache
from app.market.dependencies import MarketGateway
from app.market.router import Router
from tests.market.conftest import FakeProvider

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
TSLAX = "XsDoVfqeBukxuZHWhdvWHBhgEHjGNst4MLodqsJHzoB"


class FakeJupiterClient:
    def __init__(self, resolvable: dict[str, tuple[str, float, int]] | None = None) -> None:
        self._resolvable = resolvable or {}
        self.search_calls: list[str] = []

    async def search_token(self, query: str) -> dict[str, object] | None:
        self.search_calls.append(query)
        match = self._resolvable.get(query)
        if match is None:
            return None
        mint, price, decimals = match
        return {"id": mint, "usdPrice": price, "decimals": decimals, "isVerified": True}

    async def lend_tokens(self) -> list[dict[str, object]]:
        return [
            {
                "asset": {"symbol": "USDC", "address": USDC, "decimals": 6, "price": "1.0"},
                "supplyRate": "386",
                "totalAssets": "430236236731306",
            },
            {
                "asset": {
                    "symbol": "WSOL",
                    "address": "So11111111111111111111111111111111111111112",
                    "decimals": 9,
                    "price": "75.0",
                },
                "supplyRate": "120",
                "totalAssets": "1000000000",
            },
        ]

    async def swap_quote(
        self,
        input_mint: str,
        output_mint: str,
        amount: str,
        slippage_bps: int,
        platform_fee_bps: int,
    ) -> dict[str, object]:
        return {
            "inputMint": input_mint,
            "outputMint": output_mint,
            "inAmount": amount,
            "outAmount": "2936789",
            "priceImpactPct": "0.01",
        }

    async def build_swap_transaction(
        self, wallet_address: str, quote: dict[str, object], fee_account: str
    ) -> dict[str, object]:
        return {"swapTransaction": "dW5zaWduZWQtdHg=", "lastValidBlockHeight": 12345}

    async def build_lend_transaction(
        self, action: str, asset_mint: str, wallet_address: str, amount: str
    ) -> dict[str, object]:
        return {"transaction": "dW5zaWduZWQtdHg="}


class FakeVerifier:
    def __init__(self, succeeds: bool = True) -> None:
        self.succeeds = succeeds
        self.checked: list[str] = []

    async def transaction_succeeded(self, signature: str) -> bool:
        self.checked.append(signature)
        return self.succeeds


def _install_fake_market_gateway(redis: Redis) -> None:
    budget = BudgetManager(redis, {})
    cache = Cache(redis)
    router = Router(providers={}, chains={}, budget=budget, cache=cache)
    app.state.market_gateway = MarketGateway(
        router=router,
        http_client=httpx.AsyncClient(),
        redis=redis,
        cache=cache,
        budget=budget,
        sec_edgar=FakeProvider("sec_edgar"),
        polymarket=FakeProvider("polymarket"),
    )


def _install_fake_jupiter_gateway(
    redis: Redis,
    *,
    resolvable: dict[str, tuple[str, float, int]] | None = None,
    verifier_succeeds: bool = True,
    trading_enabled: bool = True,
    fee_account: str = "FeeAccount111",
    rate_limit: int = 20,
) -> tuple[FakeJupiterClient, FakeVerifier]:
    client = FakeJupiterClient(resolvable)
    verifier = FakeVerifier(verifier_succeeds)
    app.state.jupiter_gateway = JupiterGateway(
        client=client,  # type: ignore[arg-type]
        verifier=verifier,  # type: ignore[arg-type]
        rate_limit=JupiterBudget(redis, rate_limit),
        trading_enabled=trading_enabled,
        platform_fee_bps=25,
        fee_account=fee_account,
    )
    return client, verifier


@pytest.fixture
def client(redis: Redis) -> Generator[TestClient]:
    with TestClient(app) as c:
        _install_fake_market_gateway(redis)
        _install_fake_jupiter_gateway(
            redis, resolvable={"AAPLx": ("AAPLmint", 306.7, 8), "TSLAx": (TSLAX, 340.4, 8)}
        )
        yield c

    async def _cleanup() -> None:
        conn = await asyncpg.connect(dsn=get_settings().database_url)
        try:
            await conn.execute("DELETE FROM dex_swaps WHERE wallet_address = $1", "so1abc")
            await conn.execute("DELETE FROM lend_positions WHERE wallet_address = $1", "so1abc")
        finally:
            await conn.close()

    import anyio

    anyio.run(_cleanup)


def test_config_reports_configured_when_fee_account_is_set(client: TestClient) -> None:
    response = client.get("/jupiter/config")

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert body["trading_enabled"] is True
    assert body["platform_fee_bps"] == 25


def test_config_reports_unconfigured_when_fee_account_is_blank(redis: Redis) -> None:
    with TestClient(app) as c:
        _install_fake_market_gateway(redis)
        _install_fake_jupiter_gateway(redis, fee_account="")
        response = c.get("/jupiter/config")

    assert response.json()["configured"] is False


def test_xstocks_only_returns_resolvable_symbols(client: TestClient) -> None:
    response = client.get("/jupiter/xstocks")

    assert response.status_code == 200
    body = response.json()
    symbols = {x["symbol"] for x in body}
    # Only AAPLx/TSLAx resolve via the fake client; every other catalog
    # entry is silently omitted, never shown with a guessed price.
    assert symbols == {"AAPLx", "TSLAx"}
    aaplx = next(x for x in body if x["symbol"] == "AAPLx")
    assert aaplx["category"] == "public_equity"
    vcxx_present = "VCXx" in symbols
    assert vcxx_present is False


def test_xstocks_flags_pre_ipo_category(redis: Redis) -> None:
    with TestClient(app) as c:
        _install_fake_market_gateway(redis)
        _install_fake_jupiter_gateway(
            redis, resolvable={"VCXx": ("VCXmint", 43.8, 8), "SPCXx": ("SPCXmint", 139.7, 8)}
        )
        response = c.get("/jupiter/xstocks")

    body = response.json()
    assert all(x["category"] == "pre_ipo" for x in body)


def test_xstocks_503_when_nothing_resolves(redis: Redis) -> None:
    with TestClient(app) as c:
        _install_fake_market_gateway(redis)
        _install_fake_jupiter_gateway(redis, resolvable={})
        response = c.get("/jupiter/xstocks")

    assert response.status_code == 503


def test_lend_tokens_filters_to_stablecoins_only(client: TestClient) -> None:
    response = client.get("/jupiter/lend-tokens")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["symbol"] == "USDC"
    assert body[0]["supply_apy_pct"] == pytest.approx(3.86)


def test_swap_quote_refuses_when_trading_disabled(redis: Redis) -> None:
    with TestClient(app) as c:
        _install_fake_market_gateway(redis)
        _install_fake_jupiter_gateway(redis, trading_enabled=False)
        response = c.post(
            "/jupiter/swap-quote",
            json={"input_mint": USDC, "output_mint": TSLAX, "amount": "10000000"},
        )

    assert response.status_code == 503


def test_swap_quote_returns_a_real_quote_when_enabled(client: TestClient) -> None:
    response = client.post(
        "/jupiter/swap-quote",
        json={"input_mint": USDC, "output_mint": TSLAX, "amount": "10000000"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["out_amount"] == "2936789"
    assert body["price_impact_pct"] == pytest.approx(0.01)


def test_swap_transaction_returns_an_unsigned_transaction(client: TestClient) -> None:
    quote = client.post(
        "/jupiter/swap-quote",
        json={"input_mint": USDC, "output_mint": TSLAX, "amount": "10000000"},
    ).json()

    response = client.post(
        "/jupiter/swap-transaction",
        json={"wallet_address": "So1ABC", "quote": quote["raw_quote"]},
    )

    assert response.status_code == 200
    assert response.json()["transaction"] == "dW5zaWduZWQtdHg="


def test_lend_transaction_returns_an_unsigned_transaction(client: TestClient) -> None:
    response = client.post(
        "/jupiter/lend-transaction",
        json={
            "wallet_address": "So1ABC",
            "asset_mint": USDC,
            "action": "deposit",
            "amount": "1000000",
        },
    )

    assert response.status_code == 200
    assert response.json()["transaction"] == "dW5zaWduZWQtdHg="


def test_swap_fill_rejects_an_unverified_signature(redis: Redis) -> None:
    with TestClient(app) as c:
        _install_fake_market_gateway(redis)
        _install_fake_jupiter_gateway(redis, verifier_succeeds=False)
        response = c.post(
            "/jupiter/swap-fills",
            json={
                "wallet_address": "So1ABC",
                "input_mint": USDC,
                "output_mint": TSLAX,
                "in_amount": "10000000",
                "out_amount": "2936789",
                "signature": "bad-sig",
            },
        )

    assert response.status_code == 422


def test_swap_fill_records_a_verified_fill_and_lists_it(client: TestClient) -> None:
    post_response = client.post(
        "/jupiter/swap-fills",
        json={
            "wallet_address": "So1ABC",
            "input_mint": USDC,
            "output_mint": TSLAX,
            "in_amount": "10000000",
            "out_amount": "2936789",
            "signature": "good-sig",
        },
    )
    assert post_response.status_code == 200

    list_response = client.get("/jupiter/swap-history", params={"wallet": "so1abc"})

    assert list_response.status_code == 200
    fills = list_response.json()
    assert len(fills) == 1
    assert fills[0]["signature"] == "good-sig"
    assert fills[0]["platform_fee_bps"] == 25


def test_lend_fill_records_a_verified_fill_and_lists_it(client: TestClient) -> None:
    post_response = client.post(
        "/jupiter/lend-fills",
        json={
            "wallet_address": "So1ABC",
            "asset_mint": USDC,
            "action": "deposit",
            "amount": "1000000",
            "signature": "good-lend-sig",
        },
    )
    assert post_response.status_code == 200

    list_response = client.get("/jupiter/lend-history", params={"wallet": "so1abc"})

    assert list_response.status_code == 200
    fills = list_response.json()
    assert len(fills) == 1
    assert fills[0]["action"] == "deposit"


def test_fill_rate_limit_returns_429(redis: Redis) -> None:
    with TestClient(app) as c:
        _install_fake_market_gateway(redis)
        _install_fake_jupiter_gateway(redis, rate_limit=1)
        first = c.post(
            "/jupiter/swap-fills",
            json={
                "wallet_address": "So1ABC",
                "input_mint": USDC,
                "output_mint": TSLAX,
                "in_amount": "1",
                "out_amount": "1",
                "signature": "sig-1",
            },
        )
        second = c.post(
            "/jupiter/swap-fills",
            json={
                "wallet_address": "So1ABC",
                "input_mint": USDC,
                "output_mint": TSLAX,
                "in_amount": "1",
                "out_amount": "1",
                "signature": "sig-2",
            },
        )

    assert first.status_code == 200
    assert second.status_code == 429

    async def _cleanup() -> None:
        conn = await asyncpg.connect(dsn=get_settings().database_url)
        try:
            await conn.execute("DELETE FROM dex_swaps WHERE wallet_address = $1", "so1abc")
        finally:
            await conn.close()

    import anyio

    anyio.run(_cleanup)


def test_usdc_mint_endpoint(client: TestClient) -> None:
    response = client.get("/jupiter/usdc-mint")

    assert response.status_code == 200
    assert response.json()["mint"] == USDC
