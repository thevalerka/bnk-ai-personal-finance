from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.market import router as market_router
from app.config import get_settings
from app.market.dependencies import build_market_gateway

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.market_gateway = build_market_gateway(settings)
    yield
    await app.state.market_gateway.aclose()


app = FastAPI(title="Adaptive Markets Terminal API", lifespan=lifespan)
app.include_router(market_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.env}
