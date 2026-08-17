from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Action = Literal["deposit", "withdraw"]


class JupiterConfig(BaseModel):
    """Public, non-secret values the frontend needs to build a swap/lend
    transaction request and know whether signing is actually live
    (docs/DECISIONS.md ADR-0029). No key ever passes through to the
    browser — the backend proxies every Jupiter call server-side because
    Jupiter's API needs a secret x-api-key the browser can't safely hold."""

    trading_enabled: bool
    platform_fee_bps: int
    configured: bool


class XStock(BaseModel):
    """One tokenized-equity entry from the curated catalog
    (app/jupiter/catalog.py), resolved to a real mint + live price via
    Jupiter's token search — never rendered if that resolution fails
    (CLAUDE.md: no number without a real provider response behind it)."""

    symbol: str
    name: str
    mint: str
    decimals: int
    price_usd: float
    # "public_equity" for already-listed companies (AAPLx, TSLAx, ...);
    # "pre_ipo" for the two genuine private/pre-IPO exposure products
    # (VCXx, SPCXx) — these are synthetic trackers/fund wrappers with no
    # shareholder rights, flagged distinctly so the UI can disclose that.
    category: Literal["public_equity", "pre_ipo"]
    note: str


class LendToken(BaseModel):
    """One Jupiter Lend vault (GET /lend/v1/earn/tokens) — real current
    supply APY for a stablecoin, not a static/aggregated number."""

    asset_mint: str
    symbol: str
    decimals: int
    supply_apy_pct: float
    total_supplied_usd: float


class SwapQuoteIn(BaseModel):
    input_mint: str
    output_mint: str
    # Smallest-unit integer amount (matches Jupiter's own convention) as a
    # string to avoid float precision loss on large token amounts.
    amount: str
    slippage_bps: int = 50


class SwapQuoteOut(BaseModel):
    input_mint: str
    output_mint: str
    in_amount: str
    out_amount: str
    price_impact_pct: float
    # Opaque, passed back verbatim to /swap-transaction — Jupiter's own
    # quoteResponse payload, not something we parse or trust fields out of
    # beyond what's already surfaced above.
    raw_quote: dict[str, object]


class SwapTransactionIn(BaseModel):
    wallet_address: str
    quote: dict[str, object]


class SwapTransactionOut(BaseModel):
    # Base64-encoded unsigned Solana transaction — the browser deserializes,
    # signs with the user's own wallet, and submits it. The backend never
    # sees a signature or a private key.
    transaction: str
    last_valid_block_height: int


class LendTransactionIn(BaseModel):
    wallet_address: str
    asset_mint: str
    action: Action
    # Smallest-unit integer amount, as a string (same rationale as
    # SwapQuoteIn.amount).
    amount: str


class LendTransactionOut(BaseModel):
    transaction: str


class SwapFillIn(BaseModel):
    wallet_address: str
    input_mint: str
    output_mint: str
    in_amount: str
    out_amount: str
    # The on-chain signature of the transaction the wallet already signed
    # and submitted directly to Solana — re-verified against a live RPC
    # call before this is trusted (see app/jupiter/solana_verify.py).
    signature: str


class SwapFillOut(BaseModel):
    id: int
    wallet_address: str
    input_mint: str
    output_mint: str
    in_amount: str
    out_amount: str
    signature: str
    platform_fee_bps: int
    created_at: datetime


class LendFillIn(BaseModel):
    wallet_address: str
    asset_mint: str
    action: Action
    amount: str
    signature: str


class LendFillOut(BaseModel):
    id: int
    wallet_address: str
    asset_mint: str
    action: Action
    amount: str
    signature: str
    created_at: datetime
