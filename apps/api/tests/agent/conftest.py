"""Agent test fixtures. Reuses tests/attention's real-Postgres pattern (the
attention engine's mutation tools genuinely write rows) and tests/market's
FakeProvider double (no vendor is called for real here either) — same
disciplines the rest of this test suite already applies, just combined
since the agent sits on top of both subsystems.

The Anthropic SDK itself is never called: FakeAsyncAnthropic below is a
narrow test double matching only the surface app/agent/service.py actually
uses (`client.messages.stream(...)` as an async context manager, async
iteration over events, `await stream.get_final_message()`) — mocking HTTP
bytes for a real SSE parse would test Anthropic's own library, not this
app's tool-use loop.
"""

import uuid
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import asyncpg
import httpx
import pytest
from fakeredis import FakeAsyncRedis
from redis.asyncio import Redis

from app.attention import service as attention_service
from app.attention.taxonomy import Taxonomy, load_taxonomy
from app.config import get_settings
from app.db import create_pool, init_schema
from app.market.budget import BudgetManager
from app.market.cache import Cache
from app.market.dependencies import MarketGateway
from app.market.router import Router
from tests.market.conftest import FakeProvider

# ---------------------------------------------------------------------------
# Real Postgres (same fixtures as tests/attention/conftest.py)
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_pool() -> AsyncGenerator[asyncpg.Pool]:
    pool = await create_pool(get_settings())
    await init_schema(pool)
    yield pool
    await pool.close()


@pytest.fixture
async def db_conn(db_pool: asyncpg.Pool) -> AsyncGenerator[asyncpg.pool.PoolConnectionProxy]:
    async with db_pool.acquire() as conn:
        tr = conn.transaction()
        await tr.start()
        try:
            yield conn
        finally:
            await tr.rollback()


@pytest.fixture
def taxonomy() -> Taxonomy:
    return load_taxonomy()


@pytest.fixture
async def profile_id(db_pool: asyncpg.Pool) -> AsyncGenerator[uuid.UUID]:
    # Committed via a plain pool connection, not db_conn's rollback-only
    # transaction: tool executors acquire their own connection from
    # ctx.db_pool, which can't see an uncommitted insert held open on a
    # different connection. Cleaned up explicitly instead (ON DELETE
    # CASCADE takes events/interest_scores with it).
    pid = uuid.uuid4()
    async with db_pool.acquire() as conn:
        await attention_service.ensure_profile(conn, pid)
    yield pid
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM profiles WHERE id = $1", pid)


# ---------------------------------------------------------------------------
# Fake market gateway (same chains as app/main.py's real build, FakeRedis)
# ---------------------------------------------------------------------------


@pytest.fixture
async def redis() -> AsyncGenerator[Redis]:
    client = FakeAsyncRedis()
    yield client
    await client.aclose()


def build_gateway(redis: Redis, providers: dict[str, FakeProvider]) -> MarketGateway:
    chains = {
        "equity_quote": ["finnhub", "alpaca"],
        "crypto_quote": ["binance", "hyperliquid"],
        "macro_series": ["fred"],
        "equity_candles": ["alpaca"],
        "crypto_candles": ["binance", "hyperliquid"],
        "macro_candles": ["fred"],
        "equity_news": ["finnhub"],
        "macro_news": ["federal_reserve"],
        "earnings_calendar": ["finnhub"],
        "macro_calendar": ["fred"],
        "auction_calendar": ["treasury"],
        "regional_fed_news": ["regional_feds"],
        "sec_filings_news": ["sec_edgar"],
        "media_news": ["rss_media"],
    }
    budget = BudgetManager(redis, {})
    cache = Cache(redis)
    router = Router(providers=providers, chains=chains, budget=budget, cache=cache)  # type: ignore[arg-type]
    return MarketGateway(
        # Real (unused-by-any-agent-tool) client rather than None — needed
        # so app.main's lifespan shutdown can still call .aclose() on it
        # when a test installs this gateway onto the live app.
        router=router,
        http_client=httpx.AsyncClient(),
        redis=redis,
        cache=cache,
        budget=budget,
        sec_edgar=providers.get("sec_edgar", FakeProvider("sec_edgar")),
        polymarket=providers.get("polymarket", FakeProvider("polymarket")),
    )


# ---------------------------------------------------------------------------
# Fake Anthropic client — matches only the surface service.py uses
# ---------------------------------------------------------------------------


@dataclass
class FakeUsage:
    input_tokens: int = 10
    output_tokens: int = 5


@dataclass
class FakeTextDelta:
    text: str
    type: str = "text_delta"


@dataclass
class FakeContentBlockDeltaEvent:
    delta: FakeTextDelta
    type: str = "content_block_delta"


@dataclass
class FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class FakeToolUseBlock:
    name: str
    input: dict[str, Any]
    id: str = "toolu_1"
    type: str = "tool_use"


@dataclass
class FakeMessage:
    content: list[Any]
    stop_reason: str
    usage: FakeUsage = field(default_factory=FakeUsage)


class FakeStream:
    def __init__(self, events: list[Any], final_message: FakeMessage) -> None:
        self._events = events
        self._final_message = final_message

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._iter()

    async def _iter(self) -> AsyncIterator[Any]:
        for event in self._events:
            yield event

    async def get_final_message(self) -> FakeMessage:
        return self._final_message


class FakeStreamManager:
    def __init__(self, stream: FakeStream | None, error: BaseException | None = None) -> None:
        self._stream = stream
        self._error = error

    async def __aenter__(self) -> FakeStream:
        if self._error is not None:
            raise self._error
        assert self._stream is not None
        return self._stream

    async def __aexit__(self, *exc: object) -> bool:
        return False


FakeTurn = tuple[list[Any], FakeMessage] | BaseException


class FakeMessagesAPI:
    """`turns` is one entry per expected `client.messages.stream(...)` call,
    consumed in order — turn 1 is the first request, turn 2 the follow-up
    after a tool result, etc. An entry is either an (events, final_message)
    pair or an exception to raise on stream entry (simulating a request
    that fails before any content arrives)."""

    def __init__(self, turns: list[FakeTurn]) -> None:
        self._turns = list(turns)
        self.calls: list[dict[str, Any]] = []

    def stream(self, **kwargs: Any) -> FakeStreamManager:
        self.calls.append(kwargs)
        turn = self._turns.pop(0)
        if isinstance(turn, BaseException):
            return FakeStreamManager(None, error=turn)
        events, final_message = turn
        return FakeStreamManager(FakeStream(events, final_message))


class FakeAsyncAnthropic:
    def __init__(self, turns: list[FakeTurn]) -> None:
        self.messages = FakeMessagesAPI(turns)

    async def close(self) -> None:
        """No-op — matches anthropic.AsyncAnthropic's surface so
        app.main's lifespan shutdown (`await app.state.anthropic_client.
        close()`) works unmodified when a test installs this in its place.
        """
