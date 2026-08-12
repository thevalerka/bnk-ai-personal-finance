import httpx
from fastapi.testclient import TestClient
from redis.asyncio import Redis

from app.main import app
from app.market.budget import BudgetManager
from app.market.cache import Cache
from app.market.dependencies import MarketGateway
from app.market.router import Router
from tests.market.conftest import FakeProvider, ProviderError


def _install_fake_gateway(redis: Redis, providers: dict[str, FakeProvider]) -> None:
    chains = {
        "equity_quote": ["finnhub", "alpaca"],
        "crypto_quote": ["binance", "hyperliquid"],
        "macro_series": ["fred"],
    }
    router = Router(
        providers=providers,  # type: ignore[arg-type]
        chains=chains,
        budget=BudgetManager(redis, {}),
        cache=Cache(redis),
    )
    app.state.market_gateway = MarketGateway(
        router=router, http_client=httpx.AsyncClient(), redis=redis
    )


def test_tape_returns_normalized_quotes_from_every_reachable_capability(redis: Redis) -> None:
    with TestClient(app) as client:
        _install_fake_gateway(
            redis,
            {
                "finnhub": FakeProvider("finnhub"),
                "alpaca": FakeProvider("alpaca"),
                "binance": FakeProvider("binance"),
                "hyperliquid": FakeProvider("hyperliquid"),
                "fred": FakeProvider("fred"),
            },
        )

        response = client.get("/market/tape")

        assert response.status_code == 200
        symbols = {item["symbol"] for item in response.json()}
        assert {"SPY", "QQQ", "BTC", "DGS2", "DGS10", "VIXCLS", "DCOILWTICO"} <= symbols


def test_tape_falls_back_transparently_when_the_primary_provider_is_down(redis: Redis) -> None:
    with TestClient(app) as client:
        _install_fake_gateway(
            redis,
            {
                "finnhub": FakeProvider("finnhub", error=ProviderError("finnhub is down")),
                "alpaca": FakeProvider("alpaca"),
                "binance": FakeProvider("binance", error=ProviderError("binance is down")),
                "hyperliquid": FakeProvider("hyperliquid"),
                "fred": FakeProvider("fred"),
            },
        )

        response = client.get("/market/tape")

        assert response.status_code == 200
        sources = {item["source"] for item in response.json()}
        assert sources == {"alpaca", "hyperliquid", "fred"}


def test_tape_returns_503_when_every_provider_is_unreachable(redis: Redis) -> None:
    with TestClient(app) as client:
        down = ProviderError("down")
        _install_fake_gateway(
            redis,
            {
                "finnhub": FakeProvider("finnhub", error=down),
                "alpaca": FakeProvider("alpaca", error=down),
                "binance": FakeProvider("binance", error=down),
                "hyperliquid": FakeProvider("hyperliquid", error=down),
                "fred": FakeProvider("fred", error=down),
            },
        )

        response = client.get("/market/tape")

        assert response.status_code == 503


def test_quote_endpoint_returns_503_on_total_provider_failure(redis: Redis) -> None:
    with TestClient(app) as client:
        _install_fake_gateway(
            redis, {"finnhub": FakeProvider("finnhub", error=ProviderError("down"))}
        )

        response = client.get(
            "/market/quote", params={"capability": "equity_quote", "symbols": "AAPL"}
        )

        assert response.status_code == 503
