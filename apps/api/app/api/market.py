from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request

from app.market.dependencies import MarketGateway
from app.market.providers.base import DateRange
from app.market.router import MarketDataUnavailable, Router
from app.market.schemas import Candle, Event, NewsItem, Quote

router = APIRouter(prefix="/market", tags=["market"])

# Global tape composition for phase 1: whatever's reachable with the four
# providers this phase ships (Finnhub, FRED, Alpaca, Binance/Hyperliquid).
# DXY/gold need Twelve Data, which isn't a P1 adapter — see docs/STATE.md.
TAPE_SPEC: list[tuple[str, list[str]]] = [
    ("equity_quote", ["SPY", "QQQ"]),
    ("crypto_quote", ["BTC"]),
    ("macro_series", ["DGS2", "DGS10", "VIXCLS", "DCOILWTICO"]),
]

# Earnings (finnhub) and macro releases (fred) are complementary, not
# fallback alternatives — both are always queried and merged, same as tape.
CALENDAR_CAPABILITIES = ["earnings_calendar", "macro_calendar"]


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


@router.get("/candles")
async def get_candles(
    request: Request, capability: str, symbol: str, tf: str = "1d", limit: int = 90
) -> list[Candle]:
    market_router = _router(request)
    try:
        return await market_router.candles(capability, symbol, tf, limit)
    except MarketDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/news")
async def get_news(
    request: Request,
    capability: str = "equity_news",
    topics: str = "",
    since_hours: int = 24,
) -> list[NewsItem]:
    market_router = _router(request)
    topic_list = [t.strip() for t in topics.split(",") if t.strip()]
    since = datetime.now(tz=UTC) - timedelta(hours=since_hours)
    try:
        return await market_router.news(capability, topic_list, since)
    except MarketDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/calendar")
async def get_calendar(request: Request, days: int = 14) -> list[Event]:
    market_router = _router(request)
    today = datetime.now(tz=UTC).date()
    window = DateRange(start=today, end=today + timedelta(days=days))
    events: list[Event] = []
    for capability in CALENDAR_CAPABILITIES:
        try:
            events.extend(await market_router.calendar(capability, window))
        except MarketDataUnavailable:
            continue
    events.sort(key=lambda event: event.ts)
    return events
