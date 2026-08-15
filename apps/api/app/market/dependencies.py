from dataclasses import dataclass

import httpx
from redis.asyncio import Redis

from app.config import Settings
from app.market.budget import BudgetManager
from app.market.cache import Cache
from app.market.config_loader import load_budgets, load_provider_chains
from app.market.providers.alpaca import AlpacaProvider
from app.market.providers.base import FundamentalsProvider, ProbabilityProvider, Provider
from app.market.providers.binance import BinanceProvider
from app.market.providers.federal_reserve import FederalReserveProvider
from app.market.providers.finnhub import FinnhubProvider
from app.market.providers.fred import FredProvider
from app.market.providers.hyperliquid import HyperliquidProvider
from app.market.providers.polymarket import PolymarketProvider
from app.market.providers.regional_feds import RegionalFedsProvider
from app.market.providers.rss_media import RssMediaProvider
from app.market.providers.sec_edgar import SecEdgarProvider
from app.market.providers.treasury import TreasuryProvider
from app.market.router import Router


@dataclass
class MarketGateway:
    router: Router
    http_client: httpx.AsyncClient
    redis: Redis
    # cache/budget/sec_edgar/polymarket are also reachable via router
    # internally for their Router-mediated capabilities, but fundamentals()/
    # probability() don't fit the quote/candles/news/calendar Provider
    # Protocol (docs/DECISIONS.md ADR-0021/0024) — exposed here so their
    # endpoints can call them directly while still going through the same
    # cache-then-budget discipline every other vendor call gets.
    cache: Cache
    budget: BudgetManager
    sec_edgar: FundamentalsProvider
    polymarket: ProbabilityProvider

    async def aclose(self) -> None:
        await self.http_client.aclose()
        await self.redis.aclose()


def build_market_gateway(settings: Settings) -> MarketGateway:
    http_client = httpx.AsyncClient(timeout=10.0)
    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=True)

    sec_edgar_provider = SecEdgarProvider(http_client)
    polymarket_provider = PolymarketProvider(http_client)
    providers: dict[str, Provider] = {
        "finnhub": FinnhubProvider(http_client, settings.finnhub_api_key),
        "fred": FredProvider(http_client, settings.fred_api_key),
        "alpaca": AlpacaProvider(http_client, settings.alpaca_api_key, settings.alpaca_api_secret),
        "binance": BinanceProvider(http_client),
        "hyperliquid": HyperliquidProvider(http_client),
        "federal_reserve": FederalReserveProvider(http_client),
        "treasury": TreasuryProvider(http_client),
        "regional_feds": RegionalFedsProvider(http_client),
        "sec_edgar": sec_edgar_provider,
        "rss_media": RssMediaProvider(http_client),
    }
    budget = BudgetManager(redis, load_budgets())
    cache = Cache(redis)
    router = Router(providers, load_provider_chains(), budget, cache)
    return MarketGateway(
        router=router,
        http_client=http_client,
        redis=redis,
        cache=cache,
        budget=budget,
        sec_edgar=sec_edgar_provider,
        polymarket=polymarket_provider,
    )
