from dataclasses import dataclass

import httpx
from redis.asyncio import Redis

from app.config import Settings
from app.market.budget import BudgetManager
from app.market.cache import Cache
from app.market.config_loader import load_budgets, load_provider_chains
from app.market.providers.alpaca import AlpacaProvider
from app.market.providers.base import Provider
from app.market.providers.binance import BinanceProvider
from app.market.providers.finnhub import FinnhubProvider
from app.market.providers.fred import FredProvider
from app.market.providers.hyperliquid import HyperliquidProvider
from app.market.router import Router


@dataclass
class MarketGateway:
    router: Router
    http_client: httpx.AsyncClient
    redis: Redis

    async def aclose(self) -> None:
        await self.http_client.aclose()
        await self.redis.aclose()


def build_market_gateway(settings: Settings) -> MarketGateway:
    http_client = httpx.AsyncClient(timeout=10.0)
    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=True)

    providers: dict[str, Provider] = {
        "finnhub": FinnhubProvider(http_client, settings.finnhub_api_key),
        "fred": FredProvider(http_client, settings.fred_api_key),
        "alpaca": AlpacaProvider(http_client, settings.alpaca_api_key, settings.alpaca_api_secret),
        "binance": BinanceProvider(http_client),
        "hyperliquid": HyperliquidProvider(http_client),
    }
    budget = BudgetManager(redis, load_budgets())
    cache = Cache(redis)
    router = Router(providers, load_provider_chains(), budget, cache)
    return MarketGateway(router=router, http_client=http_client, redis=redis)
