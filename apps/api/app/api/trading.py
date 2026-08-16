from fastapi import APIRouter, HTTPException, Request

from app.trading import service
from app.trading.gateway import TradingGateway
from app.trading.schemas import ApprovalIn, ApprovalOut, FillIn, FillOut, TradingConfig

router = APIRouter(prefix="/trading", tags=["trading"])


def _gateway(request: Request) -> TradingGateway:
    return request.app.state.trading_gateway  # type: ignore[no-any-return]


@router.get("/config")
async def get_config(request: Request) -> TradingConfig:
    gateway = _gateway(request)
    return TradingConfig(
        builder_address=gateway.builder_address,
        builder_fee_tenths_bp=gateway.builder_fee_tenths_bp,
        testnet_base_url=gateway.testnet_base_url,
        configured=gateway.configured,
    )


@router.post("/approvals")
async def post_approval(request: Request, body: ApprovalIn) -> ApprovalOut:
    """Logged after the frontend already got a real builder-fee approval
    signed and accepted by Hyperliquid — this endpoint doesn't grant
    anything, it's our own record for commission accounting (docs/
    DECISIONS.md ADR-0028)."""
    gateway = _gateway(request)
    if not await gateway.budget.try_consume_request(body.wallet_address):
        raise HTTPException(status_code=429, detail="too many requests")
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        return await service.record_approval(conn, body.wallet_address, body.max_fee_tenths_bp)


@router.post("/fills")
async def post_fill(request: Request, body: FillIn) -> FillOut:
    """Logged after the frontend already signed and submitted an order
    directly to Hyperliquid — verified against Hyperliquid's own testnet
    orderStatus before being trusted, so this can't be fed a fabricated
    trade (CLAUDE.md: no number without a real provider response behind
    it, applied here to commission accounting rather than displayed market
    data)."""
    gateway = _gateway(request)
    if not await gateway.budget.try_consume_request(body.wallet_address):
        raise HTTPException(status_code=429, detail="too many requests")
    if not await gateway.exchange.order_exists(body.wallet_address, body.order_id):
        raise HTTPException(status_code=422, detail="order not found on hyperliquid testnet")
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        return await service.record_fill(
            conn,
            body.wallet_address,
            body.coin,
            body.side,
            body.size,
            body.price,
            gateway.builder_fee_tenths_bp,
        )


@router.get("/orders")
async def get_orders(request: Request, wallet: str) -> list[FillOut]:
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        return await service.list_fills(conn, wallet)
