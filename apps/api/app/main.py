from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import anthropic
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.budget import AgentBudget
from app.api.agent import router as agent_router
from app.api.jupiter import router as jupiter_router
from app.api.market import router as market_router
from app.api.profile import router as profile_router
from app.api.trading import router as trading_router
from app.config import get_settings
from app.db import create_pool, init_schema
from app.jupiter.gateway import build_jupiter_gateway
from app.market.dependencies import build_market_gateway
from app.trading.gateway import build_trading_gateway

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.market_gateway = build_market_gateway(settings)
    app.state.db_pool = await create_pool(settings)
    await init_schema(app.state.db_pool)
    # Reuses the market gateway's httpx client + Redis, same rationale as
    # agent_budget below — this is another consumer of shared infra, not a
    # reason to open new connections.
    app.state.trading_gateway = build_trading_gateway(
        settings, app.state.market_gateway.http_client, app.state.market_gateway.redis
    )
    # Same reuse rationale as trading_gateway above (docs/DECISIONS.md ADR-0029).
    app.state.jupiter_gateway = build_jupiter_gateway(
        settings, app.state.market_gateway.http_client, app.state.market_gateway.redis
    )
    # Reuses the gateway's own Redis connection rather than opening a
    # second one — the agent's budget/rate-limit counters are just more
    # keys in the same store.
    app.state.agent_budget = AgentBudget(
        app.state.market_gateway.redis,
        settings.agent_monthly_token_budget,
        settings.agent_rate_limit_per_minute,
    )
    # Constructed even with an empty key (no network call at construction
    # time) — /agent/stream refuses up front with a 503 when the key is
    # blank, so this is never actually invoked in that state.
    app.state.anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    yield
    await app.state.market_gateway.aclose()
    await app.state.db_pool.close()
    await app.state.anthropic_client.close()


app = FastAPI(title="Adaptive Markets Terminal API", lifespan=lifespan)
# /profile/* is called directly from the browser with credentials (the
# amt_profile cookie) for live event tracking — /market/* never needs this,
# it's only ever fetched server-side by Next.js Server Components.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(market_router)
app.include_router(profile_router)
app.include_router(agent_router)
app.include_router(trading_router)
app.include_router(jupiter_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.env}
