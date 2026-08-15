from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ValidationError

from app.market.dependencies import MarketGateway
from app.market.providers.base import DateRange, ProviderError
from app.market.router import MarketDataUnavailable, Router
from app.market.schemas import (
    Candle,
    EarningsMarket,
    Event,
    FinancialPeriod,
    NewsItem,
    PredictionMarket,
    Quote,
    StockDetail,
    WorldIndexPoint,
)

router = APIRouter(prefix="/market", tags=["market"])

# Global tape composition for phase 1: whatever's reachable with the four
# providers this phase ships (Finnhub, FRED, Alpaca, Binance/Hyperliquid).
# DXY/gold need Twelve Data, which isn't a P1 adapter — see docs/STATE.md.
TAPE_SPEC: list[tuple[str, list[str]]] = [
    (
        "equity_quote",
        ["SPY", "QQQ", "DIA", "IWM", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"],
    ),
    ("crypto_quote", ["BTC", "ETH"]),
    ("macro_series", ["DGS2", "DGS10", "VIXCLS", "DCOILWTICO"]),
]

# Earnings (finnhub), macro releases (fred), and Treasury auctions are
# complementary, not fallback alternatives — all three are always queried
# and merged, same as tape. See SOURCES.md: the calendar comes from primary
# sources (fred, treasury) wherever one exists; finnhub's own economic
# calendar is paid-only, which is exactly why macro_calendar stays on fred.
CALENDAR_CAPABILITIES = ["earnings_calendar", "macro_calendar", "auction_calendar"]

# Aggregated equity news (finnhub), primary-source Fed news (FOMC
# statements, official speeches), regional Fed president speeches,
# curated-ticker SEC 8-K filings, and keyless breadth media RSS — merged,
# not a fallback chain, same reasoning as CALENDAR_CAPABILITIES above.
NEWS_CAPABILITIES = [
    "equity_news",
    "macro_news",
    "regional_fed_news",
    "sec_filings_news",
    "media_news",
]


@dataclass(frozen=True)
class WorldCountrySpec:
    iso_numeric: str
    name: str
    etf_symbol: str
    # FRED's daily H.10 FX series (docs/DECISIONS.md ADR-0016) aren't
    # consistently quoted in one direction — some are USD per 1 unit of the
    # foreign currency, others are units of the foreign currency per 1 USD.
    # fx_direction records which, so the endpoint can build one coherent
    # display string either way rather than pushing that vendor quirk onto
    # the frontend. None/None/None (Indonesia, Saudi Arabia) means FRED has
    # no H.10 series for that currency — degrades to "not available".
    currency: str | None = None
    fx_series: str | None = None
    fx_direction: Literal["usd_per_unit", "units_per_usd"] | None = None
    # OECD long-term (~10Y benchmark) government bond yield, monthly, also
    # via FRED — not published for every country (China/India/Brazil/
    # Taiwan/Singapore/Hong Kong have no series here either).
    yield_series: str | None = None


# World map (docs/STATE.md): no provider here offers per-country index
# levels, FX, or bond yields directly. Index is proxied by each country's
# most liquid US-listed single-country iShares MSCI ETF (equity_quote,
# real quotes). Currency and yield both come from FRED (macro_series) —
# every series id below was verified live against the real FRED API before
# being hardcoded here, not assumed from documentation (CLAUDE.md
# non-negotiable: no number without a real provider response behind it).
# iso_numeric is ISO 3166-1 numeric (matches world-atlas's topojson feature
# ids on the frontend).
WORLD_COUNTRIES: list[WorldCountrySpec] = [
    WorldCountrySpec("840", "United States", "SPY", yield_series="DGS10"),
    WorldCountrySpec("392", "Japan", "EWJ", "JPY", "DEXJPUS", "units_per_usd", "IRLTLT01JPM156N"),
    WorldCountrySpec("276", "Germany", "EWG", "EUR", "DEXUSEU", "usd_per_unit", "IRLTLT01DEM156N"),
    WorldCountrySpec(
        "826", "United Kingdom", "EWU", "GBP", "DEXUSUK", "usd_per_unit", "IRLTLT01GBM156N"
    ),
    WorldCountrySpec("250", "France", "EWQ", "EUR", "DEXUSEU", "usd_per_unit", "IRLTLT01FRM156N"),
    WorldCountrySpec("156", "China", "MCHI", "CNY", "DEXCHUS", "units_per_usd"),
    WorldCountrySpec("356", "India", "INDA", "INR", "DEXINUS", "units_per_usd"),
    WorldCountrySpec("076", "Brazil", "EWZ", "BRL", "DEXBZUS", "units_per_usd"),
    WorldCountrySpec("124", "Canada", "EWC", "CAD", "DEXCAUS", "units_per_usd", "IRLTLT01CAM156N"),
    WorldCountrySpec(
        "036", "Australia", "EWA", "AUD", "DEXUSAL", "usd_per_unit", "IRLTLT01AUM156N"
    ),
    WorldCountrySpec(
        "410", "South Korea", "EWY", "KRW", "DEXKOUS", "units_per_usd", "IRLTLT01KRM156N"
    ),
    WorldCountrySpec("484", "Mexico", "EWW", "MXN", "DEXMXUS", "units_per_usd", "IRLTLT01MXM156N"),
    WorldCountrySpec(
        "710", "South Africa", "EZA", "ZAR", "DEXSFUS", "units_per_usd", "IRLTLT01ZAM156N"
    ),
    WorldCountrySpec("380", "Italy", "EWI", "EUR", "DEXUSEU", "usd_per_unit", "IRLTLT01ITM156N"),
    WorldCountrySpec("724", "Spain", "EWP", "EUR", "DEXUSEU", "usd_per_unit", "IRLTLT01ESM156N"),
    WorldCountrySpec(
        "528", "Netherlands", "EWN", "EUR", "DEXUSEU", "usd_per_unit", "IRLTLT01NLM156N"
    ),
    WorldCountrySpec(
        "756", "Switzerland", "EWL", "CHF", "DEXSZUS", "units_per_usd", "IRLTLT01CHM156N"
    ),
    WorldCountrySpec("752", "Sweden", "EWD", "SEK", "DEXSDUS", "units_per_usd", "IRLTLT01SEM156N"),
    WorldCountrySpec("158", "Taiwan", "EWT", "TWD", "DEXTAUS", "units_per_usd"),
    WorldCountrySpec("702", "Singapore", "EWS", "SGD", "DEXSIUS", "units_per_usd"),
    WorldCountrySpec("344", "Hong Kong", "EWH", "HKD", "DEXHKUS", "units_per_usd"),
    WorldCountrySpec("360", "Indonesia", "EIDO"),
    WorldCountrySpec("682", "Saudi Arabia", "KSA"),
]


def _router(request: Request) -> Router:
    gateway: MarketGateway = request.app.state.market_gateway
    return gateway.router


def _gateway(request: Request) -> MarketGateway:
    gateway: MarketGateway = request.app.state.market_gateway
    return gateway


def _validated[ModelT: BaseModel](
    model: type[ModelT], payload: list[dict[str, object]]
) -> list[ModelT] | None:
    # A cache entry written under an older schema (e.g. ADR-0022 adding
    # required FinancialPeriod fields) would otherwise crash the whole
    # endpoint instead of just missing the cache — found live while shipping
    # ADR-0022, treated the same as a cache miss for any bypass-cached model.
    try:
        return [model.model_validate(item) for item in payload]
    except ValidationError:
        return None


async def _cached_bypass_call[ModelT: BaseModel](
    gateway: MarketGateway,
    *,
    cache_key: str,
    fresh_ttl_seconds: int,
    budget_provider: str,
    budget_units: int,
    model: type[ModelT],
    fetch: Callable[[], Awaitable[list[ModelT]]],
) -> list[ModelT]:
    # Shared by every capability that bypasses Router (fundamentals/
    # probability, docs/DECISIONS.md ADR-0021/0024 — neither fits quote/
    # candles/news/calendar) but still needs the same cache-then-budget
    # discipline every Router-mediated vendor call gets, just applied by
    # hand instead of by Router._call.
    cached = await gateway.cache.get(cache_key, fresh_ttl_seconds)
    if cached is not None and cached.is_fresh:
        validated = _validated(model, cached.payload)
        if validated is not None:
            return validated
    if not await gateway.budget.try_consume(budget_provider, budget_units):
        if cached is not None:
            return _validated(model, cached.payload) or []
        return []
    try:
        items = await fetch()
    except ProviderError:
        if cached is not None:
            return _validated(model, cached.payload) or []
        return []
    await gateway.cache.set(cache_key, [item.model_dump(mode="json") for item in items])
    return items


async def _fundamentals(gateway: MarketGateway, symbol: str) -> list[FinancialPeriod]:
    # "v2" scopes the cache key to the current FinancialPeriod shape
    # (ADR-0022 added many new fields) so a stale pre-v2 entry expires on
    # its own rather than ever being read.
    return await _cached_bypass_call(
        gateway,
        cache_key=f"sec_edgar:fundamentals:v2:{symbol}",
        fresh_ttl_seconds=86400,
        budget_provider="sec_edgar",
        budget_units=1,
        model=FinancialPeriod,
        fetch=lambda: gateway.sec_edgar.fundamentals(symbol),
    )


async def _predictions(gateway: MarketGateway) -> list[PredictionMarket]:
    return await _cached_bypass_call(
        gateway,
        cache_key="polymarket:probability",
        fresh_ttl_seconds=60,  # matches sources.yaml's declared probability_ttl
        budget_provider="polymarket",
        budget_units=3,  # probability() paginates 3 requests per call
        model=PredictionMarket,
        fetch=gateway.polymarket.probability,
    )


async def _earnings_calendar(gateway: MarketGateway) -> list[EarningsMarket]:
    return await _cached_bypass_call(
        gateway,
        cache_key="polymarket:earnings_calendar",
        fresh_ttl_seconds=300,  # dates/EPS estimates barely move intraday
        budget_provider="polymarket",  # shares polymarket's token bucket with probability()
        budget_units=1,  # single-page request
        model=EarningsMarket,
        fetch=gateway.polymarket.earnings_calendar,
    )


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


def _fx_label(country: WorldCountrySpec, fx_quotes: dict[str, Quote]) -> str | None:
    if not country.fx_series or not country.currency:
        return None
    quote = fx_quotes.get(country.fx_series)
    if quote is None:
        return None
    if country.fx_direction == "usd_per_unit":
        return f"1 {country.currency} = ${quote.price:,.4f}"
    return f"$1 = {quote.price:,.2f} {country.currency}"


@router.get("/world")
async def get_world_indices(request: Request) -> list[WorldIndexPoint]:
    market_router = _router(request)

    etf_symbols = [c.etf_symbol for c in WORLD_COUNTRIES]
    try:
        etf_quotes = await market_router.quote("equity_quote", etf_symbols)
    except MarketDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    by_etf = {quote.symbol: quote for quote in etf_quotes}

    # Deduped: several countries share a currency (EUR) or, in principle,
    # could share a yield series — no reason to ask FRED for the same
    # series twice in one request. Each list is its own try/except so a
    # FRED hiccup degrades only that panel, not the ETF-driven map fill.
    fx_series = sorted({c.fx_series for c in WORLD_COUNTRIES if c.fx_series})
    fx_quotes: dict[str, Quote] = {}
    if fx_series:
        try:
            fx_quotes = {q.symbol: q for q in await market_router.quote("macro_series", fx_series)}
        except MarketDataUnavailable:
            pass

    yield_series = sorted({c.yield_series for c in WORLD_COUNTRIES if c.yield_series})
    yield_quotes: dict[str, Quote] = {}
    if yield_series:
        try:
            yield_quotes = {
                q.symbol: q for q in await market_router.quote("macro_series", yield_series)
            }
        except MarketDataUnavailable:
            pass

    return [
        WorldIndexPoint(
            iso_numeric=c.iso_numeric,
            name=c.name,
            symbol=c.etf_symbol,
            quote=by_etf.get(c.etf_symbol),
            currency=c.currency,
            fx_label=_fx_label(c, fx_quotes),
            bond_yield_pct=(
                yield_quotes[c.yield_series].price
                if c.yield_series and c.yield_series in yield_quotes
                else None
            ),
        )
        for c in WORLD_COUNTRIES
    ]


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
async def get_news(request: Request, topics: str = "", since_hours: int = 24) -> list[NewsItem]:
    market_router = _router(request)
    topic_list = [t.strip() for t in topics.split(",") if t.strip()]
    since = datetime.now(tz=UTC) - timedelta(hours=since_hours)
    items: list[NewsItem] = []
    for capability in NEWS_CAPABILITIES:
        try:
            items.extend(await market_router.news(capability, topic_list, since))
        except MarketDataUnavailable:
            continue
    if not items:
        raise HTTPException(status_code=503, detail="market data unavailable")
    items.sort(key=lambda item: item.ts, reverse=True)
    return items


@router.get("/stock/{symbol}")
async def get_stock_detail(request: Request, symbol: str, days: int = 180) -> StockDetail:
    # Bundles the four calls a detail page needs into one round trip, same
    # page-specific-aggregate pattern as /tape and /world. Each piece is its
    # own try/except (like /world's fx/yield split) so one dead capability
    # only blanks its own section — filings legitimately come back empty for
    # any ticker outside sec_edgar's curated 10, which is honest, not a bug.
    market_router = _router(request)
    symbol = symbol.upper()

    quote: Quote | None = None
    try:
        quotes = await market_router.quote("equity_quote", [symbol])
        quote = quotes[0] if quotes else None
    except MarketDataUnavailable:
        pass

    candles: list[Candle] = []
    try:
        candles = await market_router.candles("equity_candles", symbol, "1d", days)
    except MarketDataUnavailable:
        pass

    filings: list[NewsItem] = []
    try:
        since_filings = datetime.now(tz=UTC) - timedelta(days=730)
        filings = await market_router.news("sec_filings_news", [symbol], since_filings)
    except MarketDataUnavailable:
        pass

    news: list[NewsItem] = []
    try:
        since_news = datetime.now(tz=UTC) - timedelta(days=30)
        news = await market_router.news("equity_news", [symbol], since_news)
    except MarketDataUnavailable:
        pass

    financials = await _fundamentals(_gateway(request), symbol)

    if quote is None and not candles and not filings and not news and not financials:
        raise HTTPException(status_code=503, detail="market data unavailable")

    return StockDetail(
        symbol=symbol,
        quote=quote,
        candles=candles,
        filings=filings,
        news=news,
        financials=financials,
    )


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


@router.get("/predictions")
async def get_predictions(request: Request) -> list[PredictionMarket]:
    predictions = await _predictions(_gateway(request))
    if not predictions:
        raise HTTPException(status_code=503, detail="market data unavailable")
    return predictions


@router.get("/earnings-calendar")
async def get_earnings_calendar(request: Request) -> list[EarningsMarket]:
    calendar = await _earnings_calendar(_gateway(request))
    if not calendar:
        raise HTTPException(status_code=503, detail="market data unavailable")
    return calendar
