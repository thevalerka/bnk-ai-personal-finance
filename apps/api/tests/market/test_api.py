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
        "equity_candles": ["alpaca"],
        "crypto_candles": ["binance", "hyperliquid"],
        "macro_candles": ["fred"],
        "equity_news": ["finnhub"],
        "macro_news": ["federal_reserve"],
        "earnings_calendar": ["finnhub"],
        "macro_calendar": ["fred"],
        "auction_calendar": ["treasury"],
        "sec_filings_news": ["sec_edgar"],
        "media_news": ["rss_media"],
    }
    budget = BudgetManager(redis, {})
    cache = Cache(redis)
    router = Router(
        providers=providers,  # type: ignore[arg-type]
        chains=chains,
        budget=budget,
        cache=cache,
    )
    app.state.market_gateway = MarketGateway(
        router=router,
        http_client=httpx.AsyncClient(),
        redis=redis,
        cache=cache,
        budget=budget,
        sec_edgar=providers.get("sec_edgar", FakeProvider("sec_edgar")),
        polymarket=providers.get("polymarket", FakeProvider("polymarket")),
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


def test_world_indices_returns_a_point_per_country_with_a_real_quote(redis: Redis) -> None:
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

        response = client.get("/market/world")

        assert response.status_code == 200
        points = response.json()
        assert len(points) > 20
        us = next(p for p in points if p["iso_numeric"] == "840")
        assert us["name"] == "United States"
        assert us["symbol"] == "SPY"
        assert us["quote"]["symbol"] == "SPY"
        assert us["quote"]["source"] == "finnhub"
        assert us["bond_yield_pct"] == 1.0  # DGS10 via FakeProvider("fred")
        assert us["fx_label"] is None  # no currency for the US entry itself

        japan = next(p for p in points if p["iso_numeric"] == "392")
        assert japan["currency"] == "JPY"
        assert japan["fx_label"] == "$1 = 1.00 JPY"  # units_per_usd direction
        germany = next(p for p in points if p["iso_numeric"] == "276")
        assert germany["fx_label"] == "1 EUR = $1.0000"  # usd_per_unit direction

        indonesia = next(p for p in points if p["iso_numeric"] == "360")
        assert indonesia["currency"] is None
        assert indonesia["fx_label"] is None
        assert indonesia["bond_yield_pct"] is None


def test_world_indices_degrades_fx_and_yield_without_losing_the_map_when_fred_is_down(
    redis: Redis,
) -> None:
    with TestClient(app) as client:
        _install_fake_gateway(
            redis,
            {
                "finnhub": FakeProvider("finnhub"),
                "alpaca": FakeProvider("alpaca"),
                "binance": FakeProvider("binance"),
                "hyperliquid": FakeProvider("hyperliquid"),
                "fred": FakeProvider("fred", error=ProviderError("fred is down")),
            },
        )

        response = client.get("/market/world")

        assert response.status_code == 200
        points = response.json()
        us = next(p for p in points if p["iso_numeric"] == "840")
        assert us["quote"]["symbol"] == "SPY"  # ETF/map fill unaffected
        assert us["bond_yield_pct"] is None
        japan = next(p for p in points if p["iso_numeric"] == "392")
        assert japan["fx_label"] is None


def test_world_indices_returns_503_when_equity_quote_is_unreachable(redis: Redis) -> None:
    with TestClient(app) as client:
        down = ProviderError("down")
        _install_fake_gateway(
            redis,
            {
                "finnhub": FakeProvider("finnhub", error=down),
                "alpaca": FakeProvider("alpaca", error=down),
                "binance": FakeProvider("binance"),
                "hyperliquid": FakeProvider("hyperliquid"),
                "fred": FakeProvider("fred"),
            },
        )

        response = client.get("/market/world")

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


def test_candles_endpoint_returns_bars(redis: Redis) -> None:
    with TestClient(app) as client:
        _install_fake_gateway(redis, {"alpaca": FakeProvider("alpaca")})

        response = client.get(
            "/market/candles",
            params={"capability": "equity_candles", "symbol": "AAPL", "tf": "1d", "limit": 10},
        )

        assert response.status_code == 200
        assert response.json()[0]["symbol"] == "AAPL"


def test_candles_endpoint_returns_503_on_total_provider_failure(redis: Redis) -> None:
    with TestClient(app) as client:
        _install_fake_gateway(
            redis, {"alpaca": FakeProvider("alpaca", error=ProviderError("down"))}
        )

        response = client.get(
            "/market/candles",
            params={"capability": "equity_candles", "symbol": "AAPL"},
        )

        assert response.status_code == 503


def test_news_endpoint_merges_equity_and_macro_news(redis: Redis) -> None:
    with TestClient(app) as client:
        _install_fake_gateway(
            redis,
            {
                "finnhub": FakeProvider("finnhub"),
                "federal_reserve": FakeProvider("federal_reserve"),
            },
        )

        response = client.get("/market/news")

        assert response.status_code == 200
        sources = {item["source"] for item in response.json()}
        assert sources == {"finnhub", "federal_reserve"}


def test_news_endpoint_degrades_gracefully_when_one_source_is_down(redis: Redis) -> None:
    with TestClient(app) as client:
        _install_fake_gateway(
            redis,
            {
                "finnhub": FakeProvider("finnhub", error=ProviderError("down")),
                "federal_reserve": FakeProvider("federal_reserve"),
            },
        )

        response = client.get("/market/news")

        assert response.status_code == 200
        sources = {item["source"] for item in response.json()}
        assert sources == {"federal_reserve"}


def test_news_endpoint_returns_503_when_every_source_is_unreachable(redis: Redis) -> None:
    with TestClient(app) as client:
        down = ProviderError("down")
        _install_fake_gateway(
            redis,
            {
                "finnhub": FakeProvider("finnhub", error=down),
                "federal_reserve": FakeProvider("federal_reserve", error=down),
            },
        )

        response = client.get("/market/news")

        assert response.status_code == 503


def test_stock_detail_bundles_quote_candles_filings_and_news(redis: Redis) -> None:
    with TestClient(app) as client:
        _install_fake_gateway(
            redis,
            {
                "finnhub": FakeProvider("finnhub"),
                "alpaca": FakeProvider("alpaca"),
                "sec_edgar": FakeProvider("sec_edgar"),
            },
        )

        response = client.get("/market/stock/aapl")

        assert response.status_code == 200
        body = response.json()
        assert body["symbol"] == "AAPL"  # uppercased
        assert body["quote"]["source"] == "finnhub"
        assert body["candles"][0]["source"] == "alpaca"
        assert body["filings"][0]["source"] == "sec_edgar"
        assert body["news"][0]["source"] == "finnhub"
        assert body["financials"][0]["revenue"] == 100.0


def test_stock_detail_degrades_partially_when_filings_are_unreachable(redis: Redis) -> None:
    with TestClient(app) as client:
        _install_fake_gateway(
            redis,
            {
                "finnhub": FakeProvider("finnhub"),
                "alpaca": FakeProvider("alpaca"),
                "sec_edgar": FakeProvider("sec_edgar", error=ProviderError("down")),
            },
        )

        response = client.get("/market/stock/aapl")

        assert response.status_code == 200
        body = response.json()
        assert body["quote"] is not None  # unaffected by sec_edgar being down
        assert body["filings"] == []
        assert body["financials"] == []


def test_stock_detail_returns_503_when_everything_is_unreachable(redis: Redis) -> None:
    with TestClient(app) as client:
        down = ProviderError("down")
        _install_fake_gateway(
            redis,
            {
                "finnhub": FakeProvider("finnhub", error=down),
                "alpaca": FakeProvider("alpaca", error=down),
                "sec_edgar": FakeProvider("sec_edgar", error=down),
            },
        )

        response = client.get("/market/stock/aapl")

        assert response.status_code == 503


def test_calendar_endpoint_merges_earnings_macro_and_auctions(redis: Redis) -> None:
    with TestClient(app) as client:
        _install_fake_gateway(
            redis,
            {
                "finnhub": FakeProvider("finnhub"),
                "fred": FakeProvider("fred"),
                "treasury": FakeProvider("treasury"),
            },
        )

        response = client.get("/market/calendar")

        assert response.status_code == 200
        sources = {item["source"] for item in response.json()}
        assert sources == {"finnhub", "fred", "treasury"}


def test_calendar_endpoint_degrades_gracefully_when_one_source_is_down(redis: Redis) -> None:
    with TestClient(app) as client:
        _install_fake_gateway(
            redis,
            {
                "finnhub": FakeProvider("finnhub", error=ProviderError("down")),
                "fred": FakeProvider("fred"),
                "treasury": FakeProvider("treasury"),
            },
        )

        response = client.get("/market/calendar")

        assert response.status_code == 200
        sources = {item["source"] for item in response.json()}
        assert sources == {"fred", "treasury"}


def test_predictions_endpoint_returns_market_implied_odds(redis: Redis) -> None:
    with TestClient(app) as client:
        _install_fake_gateway(redis, {"polymarket": FakeProvider("polymarket")})

        response = client.get("/market/predictions")

        assert response.status_code == 200
        body = response.json()
        assert body[0]["source"] == "polymarket"
        assert body[0]["probability_pct"] == 75.5


def test_predictions_endpoint_returns_503_when_unreachable(redis: Redis) -> None:
    with TestClient(app) as client:
        _install_fake_gateway(
            redis, {"polymarket": FakeProvider("polymarket", error=ProviderError("down"))}
        )

        response = client.get("/market/predictions")

        assert response.status_code == 503


def test_earnings_calendar_endpoint_returns_per_company_markets(redis: Redis) -> None:
    with TestClient(app) as client:
        _install_fake_gateway(redis, {"polymarket": FakeProvider("polymarket")})

        response = client.get("/market/earnings-calendar")

        assert response.status_code == 200
        body = response.json()
        assert body[0]["source"] == "polymarket"
        assert body[0]["ticker"] == "TEST"
        assert body[0]["eps_estimate"] == "$1.00"


def test_earnings_calendar_endpoint_returns_503_when_unreachable(redis: Redis) -> None:
    with TestClient(app) as client:
        _install_fake_gateway(
            redis, {"polymarket": FakeProvider("polymarket", error=ProviderError("down"))}
        )

        response = client.get("/market/earnings-calendar")

        assert response.status_code == 503


def test_market_graph_endpoint_returns_503_when_everything_is_unreachable(redis: Redis) -> None:
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
                "federal_reserve": FakeProvider("federal_reserve", error=down),
                "treasury": FakeProvider("treasury", error=down),
                "regional_feds": FakeProvider("regional_feds", error=down),
                "sec_edgar": FakeProvider("sec_edgar", error=down),
                "rss_media": FakeProvider("rss_media", error=down),
            },
        )

        response = client.get("/market/graph")

        # FakeProvider's candles() always returns exactly 1 bar, below
        # compute_market_graph's own 20-bar minimum — same "no real signal"
        # outcome as every provider being down, exercised via the real chain
        # wiring rather than graph.py's dedicated synthetic-data tests.
        assert response.status_code == 503
