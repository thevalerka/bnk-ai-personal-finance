from fastapi import APIRouter, HTTPException, Request

from app.market.dependencies import MarketGateway
from app.market.router import MarketDataUnavailable, Router
from app.market.schemas import Quote

router = APIRouter(prefix="/market", tags=["market"])

# Global tape composition for phase 1: whatever's reachable with the four
# providers this phase ships (Finnhub, FRED, Alpaca, Binance/Hyperliquid).
# DXY/gold need Twelve Data, which isn't a P1 adapter — see docs/STATE.md.
TAPE_SPEC: list[tuple[str, list[str]]] = [
    ("equity_quote", ["SPY", "QQQ"]),
    ("crypto_quote", ["BTC"]),
    ("macro_series", ["DGS2", "DGS10", "VIXCLS", "DCOILWTICO"]),
]


def _router(request: Request) -> Router:
    gateway: MarketGateway = request.app.state.market_gateway
    return gateway.router


@router.get("/tape")
async def get_tape(request: Request) -> list[Quote]:
    market_router = _router(request)
    quotes: list[Quote] = []
    for capability, symbols in TAPE_SPEC:
        try:
            quotes.extend(await market_router.quote(capability, symbols))
        except MarketDataUnavailable:
            continue
    if not quotes:
        raise HTTPException(status_code=503, detail="market data unavailable")
    return quotes


@router.get("/quote")
async def get_quote(request: Request, capability: str, symbols: str) -> list[Quote]:
    market_router = _router(request)
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    try:
        return await market_router.quote(capability, symbol_list)
    except MarketDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
