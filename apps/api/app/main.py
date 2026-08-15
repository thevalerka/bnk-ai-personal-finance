from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.market import router as market_router
from app.api.profile import router as profile_router
from app.config import get_settings
from app.db import create_pool, init_schema
from app.market.dependencies import build_market_gateway

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.market_gateway = build_market_gateway(settings)
    app.state.db_pool = await create_pool(settings)
    await init_schema(app.state.db_pool)
    yield
    await app.state.market_gateway.aclose()
    await app.state.db_pool.close()


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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.env}
