from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Side = Literal["buy", "sell"]


class TradingConfig(BaseModel):
    """Public, non-secret values the frontend needs to build a builder-fee
    approval / order through the Hyperliquid SDK (docs/DECISIONS.md
    ADR-0028). No key or signature ever passes through the backend — this
    is just an address and a fee rate, both public once approved on-chain
    anyway."""

    builder_address: str
    builder_fee_tenths_bp: int
    testnet_base_url: str
    configured: bool


class ApprovalIn(BaseModel):
    wallet_address: str
    max_fee_tenths_bp: int


class ApprovalOut(BaseModel):
    wallet_address: str
    max_fee_tenths_bp: int
    approved_at: datetime


class FillIn(BaseModel):
    wallet_address: str
    coin: str
    side: Side
    size: float
    price: float
    # Hyperliquid's own order id — used to verify the claimed fill actually
    # happened (via a live orderStatus check) before it's logged for
    # commission accounting. Never trusted at face value.
    order_id: int


class FillOut(BaseModel):
    id: int
    wallet_address: str
    coin: str
    side: Side
    size: float
    price: float
    builder_fee_tenths_bp: int
    created_at: datetime
