from fastapi import APIRouter, HTTPException, Request

from app.jupiter import service
from app.jupiter.catalog import CATALOG, NOTES
from app.jupiter.client import USDC_MINT
from app.jupiter.gateway import JupiterGateway
from app.jupiter.schemas import (
    JupiterConfig,
    LendFillIn,
    LendFillOut,
    LendToken,
    LendTransactionIn,
    LendTransactionOut,
    SwapFillIn,
    SwapFillOut,
    SwapQuoteIn,
    SwapQuoteOut,
    SwapTransactionIn,
    SwapTransactionOut,
    XStock,
)
from app.market.dependencies import MarketGateway
from app.market.providers.base import ProviderError

router = APIRouter(prefix="/jupiter", tags=["jupiter"])

# Stablecoins only (docs/PLAN.md's "fixed income" area) — Jupiter Lend also
# lists volatile-asset vaults (WSOL, ...), out of scope here.
_STABLECOIN_SYMBOLS = {"USDC", "USDT", "DAI", "PYUSD", "USDS", "USDG"}

_XSTOCKS_CACHE_KEY = "jupiter:xstocks:v1"
_LEND_TOKENS_CACHE_KEY = "jupiter:lend_tokens:v1"


def _gateway(request: Request) -> JupiterGateway:
    return request.app.state.jupiter_gateway  # type: ignore[no-any-return]


def _market_gateway(request: Request) -> MarketGateway:
    return request.app.state.market_gateway  # type: ignore[no-any-return]


@router.get("/config")
async def get_config(request: Request) -> JupiterConfig:
    gateway = _gateway(request)
    return JupiterConfig(
        trading_enabled=gateway.trading_enabled,
        platform_fee_bps=gateway.platform_fee_bps,
        configured=gateway.configured,
    )


@router.get("/xstocks")
async def get_xstocks(request: Request) -> list[XStock]:
    market_gateway = _market_gateway(request)
    cached = await market_gateway.cache.get(_XSTOCKS_CACHE_KEY, fresh_ttl_seconds=60)
    if cached is not None and cached.is_fresh:
        return [XStock.model_validate(item) for item in cached.payload]

    if not await market_gateway.budget.try_consume("jupiter", units=len(CATALOG)):
        if cached is not None:
            return [XStock.model_validate(item) for item in cached.payload]
        raise HTTPException(status_code=503, detail="jupiter budget exhausted")

    gateway = _gateway(request)
    resolved: list[XStock] = []
    for symbol, name, category in CATALOG:
        try:
            token = await gateway.client.search_token(symbol)
        except ProviderError:
            continue
        if token is None:
            continue
        price = token.get("usdPrice")
        mint = token.get("id")
        decimals = token.get("decimals")
        if (
            not isinstance(price, int | float)
            or not isinstance(mint, str)
            or not isinstance(decimals, int)
        ):
            continue
        resolved.append(
            XStock(
                symbol=symbol,
                name=name,
                mint=mint,
                decimals=decimals,
                price_usd=float(price),
                category=category,
                note=NOTES[category],
            )
        )

    if not resolved:
        if cached is not None:
            return [XStock.model_validate(item) for item in cached.payload]
        raise HTTPException(status_code=503, detail="no xStocks reachable right now")

    await market_gateway.cache.set(
        _XSTOCKS_CACHE_KEY, [x.model_dump(mode="json") for x in resolved]
    )
    return resolved


@router.get("/lend-tokens")
async def get_lend_tokens(request: Request) -> list[LendToken]:
    market_gateway = _market_gateway(request)
    cached = await market_gateway.cache.get(_LEND_TOKENS_CACHE_KEY, fresh_ttl_seconds=60)
    if cached is not None and cached.is_fresh:
        return [LendToken.model_validate(item) for item in cached.payload]

    if not await market_gateway.budget.try_consume("jupiter", units=1):
        if cached is not None:
            return [LendToken.model_validate(item) for item in cached.payload]
        raise HTTPException(status_code=503, detail="jupiter budget exhausted")

    gateway = _gateway(request)
    try:
        vaults = await gateway.client.lend_tokens()
    except ProviderError:
        if cached is not None:
            return [LendToken.model_validate(item) for item in cached.payload]
        raise HTTPException(status_code=503, detail="jupiter lend tokens unreachable") from None

    tokens: list[LendToken] = []
    for vault in vaults:
        asset = vault.get("asset")
        if not isinstance(asset, dict):
            continue
        symbol = asset.get("symbol")
        if not isinstance(symbol, str) or symbol.upper() not in _STABLECOIN_SYMBOLS:
            continue
        mint = asset.get("address")
        decimals = asset.get("decimals")
        asset_price = asset.get("price")
        supply_rate = vault.get("supplyRate")
        total_assets = vault.get("totalAssets")
        if not (
            isinstance(mint, str)
            and isinstance(decimals, int)
            and isinstance(supply_rate, str)
            and isinstance(total_assets, str)
        ):
            continue
        try:
            apy_pct = float(supply_rate) / 100
            price = float(asset_price) if isinstance(asset_price, str) else 1.0
            supplied_usd = (int(total_assets) / (10**decimals)) * price
        except (ValueError, ZeroDivisionError):
            continue
        tokens.append(
            LendToken(
                asset_mint=mint,
                symbol=symbol.upper(),
                decimals=decimals,
                supply_apy_pct=apy_pct,
                total_supplied_usd=supplied_usd,
            )
        )

    if not tokens:
        if cached is not None:
            return [LendToken.model_validate(item) for item in cached.payload]
        raise HTTPException(status_code=503, detail="no stablecoin lend vaults reachable right now")

    await market_gateway.cache.set(
        _LEND_TOKENS_CACHE_KEY, [t.model_dump(mode="json") for t in tokens]
    )
    return tokens


def _require_trading_enabled(gateway: JupiterGateway) -> None:
    if not gateway.trading_enabled:
        raise HTTPException(
            status_code=503,
            detail="live signing is disabled (JUPITER_TRADING_ENABLED is off)",
        )


@router.post("/swap-quote")
async def post_swap_quote(request: Request, body: SwapQuoteIn) -> SwapQuoteOut:
    gateway = _gateway(request)
    _require_trading_enabled(gateway)
    try:
        quote = await gateway.client.swap_quote(
            body.input_mint,
            body.output_mint,
            body.amount,
            body.slippage_bps,
            gateway.platform_fee_bps if gateway.fee_account else 0,
        )
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    price_impact_raw = quote.get("priceImpactPct", 0) or 0
    price_impact = (
        float(price_impact_raw) if isinstance(price_impact_raw, str | int | float) else 0.0
    )
    return SwapQuoteOut(
        input_mint=body.input_mint,
        output_mint=body.output_mint,
        in_amount=str(quote.get("inAmount", body.amount)),
        out_amount=str(quote.get("outAmount", "0")),
        price_impact_pct=price_impact,
        raw_quote=quote,
    )


@router.post("/swap-transaction")
async def post_swap_transaction(request: Request, body: SwapTransactionIn) -> SwapTransactionOut:
    gateway = _gateway(request)
    _require_trading_enabled(gateway)
    try:
        built = await gateway.client.build_swap_transaction(
            body.wallet_address, body.quote, gateway.fee_account
        )
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    tx = built.get("swapTransaction")
    last_valid = built.get("lastValidBlockHeight")
    if not isinstance(tx, str) or not isinstance(last_valid, int):
        raise HTTPException(
            status_code=502, detail="jupiter returned an unexpected transaction shape"
        )
    return SwapTransactionOut(transaction=tx, last_valid_block_height=last_valid)


@router.post("/lend-transaction")
async def post_lend_transaction(request: Request, body: LendTransactionIn) -> LendTransactionOut:
    gateway = _gateway(request)
    _require_trading_enabled(gateway)
    try:
        built = await gateway.client.build_lend_transaction(
            body.action, body.asset_mint, body.wallet_address, body.amount
        )
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    tx = built.get("transaction")
    if not isinstance(tx, str):
        raise HTTPException(
            status_code=502, detail="jupiter returned an unexpected transaction shape"
        )
    return LendTransactionOut(transaction=tx)


@router.post("/swap-fills")
async def post_swap_fill(request: Request, body: SwapFillIn) -> SwapFillOut:
    gateway = _gateway(request)
    if not await gateway.rate_limit.try_consume_request(body.wallet_address):
        raise HTTPException(status_code=429, detail="too many requests")
    if not await gateway.verifier.transaction_succeeded(body.signature):
        raise HTTPException(status_code=422, detail="signature not found or failed on-chain")
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        return await service.record_swap_fill(
            conn,
            body.wallet_address,
            body.input_mint,
            body.output_mint,
            body.in_amount,
            body.out_amount,
            body.signature,
            gateway.platform_fee_bps if gateway.fee_account else 0,
        )


@router.post("/lend-fills")
async def post_lend_fill(request: Request, body: LendFillIn) -> LendFillOut:
    gateway = _gateway(request)
    if not await gateway.rate_limit.try_consume_request(body.wallet_address):
        raise HTTPException(status_code=429, detail="too many requests")
    if not await gateway.verifier.transaction_succeeded(body.signature):
        raise HTTPException(status_code=422, detail="signature not found or failed on-chain")
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        return await service.record_lend_fill(
            conn, body.wallet_address, body.asset_mint, body.action, body.amount, body.signature
        )


@router.get("/swap-history")
async def get_swap_history(request: Request, wallet: str) -> list[SwapFillOut]:
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        return await service.list_swap_fills(conn, wallet)


@router.get("/lend-history")
async def get_lend_history(request: Request, wallet: str) -> list[LendFillOut]:
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        return await service.list_lend_fills(conn, wallet)


@router.get("/usdc-mint")
async def get_usdc_mint() -> dict[str, str]:
    # Small convenience so the frontend never hardcodes a mint address of
    # its own — this backend's declared constant is the single source.
    return {"mint": USDC_MINT}
