from dataclasses import dataclass

import httpx
from redis.asyncio import Redis

from app.config import Settings
from app.jupiter.budget import JupiterBudget
from app.jupiter.client import USDC_MINT, JupiterClient
from app.jupiter.solana_verify import SolanaVerifier

__all__ = ["JupiterGateway", "build_jupiter_gateway", "USDC_MINT"]


@dataclass
class JupiterGateway:
    """Sibling to `app.trading.gateway.TradingGateway` — order/deposit
    building doesn't fit the read-only Provider Protocol either
    (docs/DECISIONS.md ADR-0029)."""

    client: JupiterClient
    verifier: SolanaVerifier
    rate_limit: JupiterBudget
    trading_enabled: bool
    platform_fee_bps: int
    fee_account: str

    @property
    def configured(self) -> bool:
        """True once an operator has set up a real fee-receiving account —
        distinct from `trading_enabled` (the kill switch): signing can be
        live with zero commission configured, same as Hyperliquid's
        blank-builder-address state."""
        return bool(self.fee_account)


def build_jupiter_gateway(
    settings: Settings, http_client: httpx.AsyncClient, redis: Redis
) -> JupiterGateway:
    return JupiterGateway(
        client=JupiterClient(http_client, settings.jupiter_base_url, settings.jupiter_api_key),
        verifier=SolanaVerifier(http_client, settings.solana_rpc_url),
        rate_limit=JupiterBudget(redis, settings.jupiter_rate_limit_per_minute),
        trading_enabled=settings.jupiter_trading_enabled,
        platform_fee_bps=settings.jupiter_platform_fee_bps,
        fee_account=settings.jupiter_fee_account,
    )
