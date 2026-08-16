from dataclasses import dataclass

import httpx
from redis.asyncio import Redis

from app.config import Settings
from app.trading.budget import TradingBudget
from app.trading.hyperliquid_exchange import HyperliquidExchangeClient


@dataclass
class TradingGateway:
    """Sibling to `app.market.dependencies.MarketGateway`, not a Router
    capability itself (docs/DECISIONS.md ADR-0028) — order placement
    doesn't fit the read-only quote/candles/news/calendar Provider Protocol,
    same shape of exception `sec_edgar`/`polymarket` already are on
    `MarketGateway`."""

    exchange: HyperliquidExchangeClient
    budget: TradingBudget
    builder_address: str
    builder_fee_tenths_bp: int
    testnet_base_url: str

    @property
    def configured(self) -> bool:
        return bool(self.builder_address)


def build_trading_gateway(
    settings: Settings, http_client: httpx.AsyncClient, redis: Redis
) -> TradingGateway:
    return TradingGateway(
        exchange=HyperliquidExchangeClient(http_client),
        budget=TradingBudget(redis, settings.trading_rate_limit_per_minute),
        builder_address=settings.hyperliquid_builder_address,
        builder_fee_tenths_bp=settings.hyperliquid_builder_fee_tenths_bp,
        testnet_base_url=settings.hyperliquid_testnet_base_url,
    )
