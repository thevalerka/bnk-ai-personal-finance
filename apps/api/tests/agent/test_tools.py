import uuid
from datetime import UTC, datetime

import asyncpg
import pytest
from redis.asyncio import Redis

from app.agent.tools import TOOL_EXECUTORS, TOOLS, ToolContext, execute_tool
from app.attention import service as attention_service
from app.attention.taxonomy import Taxonomy
from app.market.providers.base import ProviderError
from app.market.schemas import Quote
from tests.agent.conftest import build_gateway
from tests.market.conftest import FakeProvider


def make_ctx(
    redis: Redis,
    db_pool: asyncpg.Pool,
    taxonomy: Taxonomy,
    profile_id: uuid.UUID,
    providers: dict[str, FakeProvider] | None = None,
) -> ToolContext:
    gateway = build_gateway(redis, providers or {})
    return ToolContext(gateway=gateway, db_pool=db_pool, taxonomy=taxonomy, profile_id=profile_id)


def test_every_tool_name_has_an_executor() -> None:
    tool_names = {t["name"] for t in TOOLS}
    assert tool_names == set(TOOL_EXECUTORS)


async def test_get_quotes_returns_real_quote_shape(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id, {"finnhub": FakeProvider("finnhub")})
    outcome = await execute_tool(
        "get_quotes", {"capability": "equity_quote", "symbols": ["AAPL"]}, ctx
    )
    assert not outcome.is_error
    assert outcome.result[0]["symbol"] == "AAPL"
    assert outcome.result[0]["source"] == "finnhub"


async def test_get_quotes_reports_unreachable_provider_honestly(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(
        redis,
        db_pool,
        taxonomy,
        profile_id,
        {"finnhub": FakeProvider("finnhub", error=ProviderError("down"))},
    )
    outcome = await execute_tool(
        "get_quotes", {"capability": "equity_quote", "symbols": ["AAPL"]}, ctx
    )
    assert outcome.is_error
    assert "error" in outcome.result


async def test_get_quotes_records_agent_mention_for_matched_taxonomy_node(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id, {"finnhub": FakeProvider("finnhub")})
    # SPY is a real instrument on equities.us_large_cap.broad_market (config/taxonomy.yaml).
    await execute_tool("get_quotes", {"capability": "equity_quote", "symbols": ["SPY"]}, ctx)
    async with db_pool.acquire() as conn:
        scores = await attention_service.get_scores(
            conn, profile_id, ["equities.us_large_cap.broad_market"]
        )
    assert scores.get("equities.us_large_cap.broad_market", 0) > 0


async def test_get_candles_summarizes_rather_than_dumping_the_series(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id, {"alpaca": FakeProvider("alpaca")})
    outcome = await execute_tool(
        "get_candles", {"capability": "equity_candles", "symbol": "AAPL", "limit": 5}, ctx
    )
    assert not outcome.is_error
    assert outcome.result["symbol"] == "AAPL"
    assert "change_pct_over_window" in outcome.result


async def test_get_curve_returns_all_reachable_tenors(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id, {"fred": FakeProvider("fred")})
    outcome = await execute_tool("get_curve", {}, ctx)
    assert not outcome.is_error
    assert outcome.result["country"] == "US"
    assert len(outcome.result["curve"]) == 11
    assert outcome.result["curve"][0]["tenor"] == "1M"


async def test_get_news_merges_every_capability(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(
        redis,
        db_pool,
        taxonomy,
        profile_id,
        {"finnhub": FakeProvider("finnhub"), "federal_reserve": FakeProvider("federal_reserve")},
    )
    outcome = await execute_tool("get_news", {}, ctx)
    assert not outcome.is_error
    sources = {item["source"] for item in outcome.result}
    assert sources == {"finnhub", "federal_reserve"}


async def test_get_calendar_merges_and_sorts(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(
        redis,
        db_pool,
        taxonomy,
        profile_id,
        {"finnhub": FakeProvider("finnhub"), "fred": FakeProvider("fred")},
    )
    outcome = await execute_tool("get_calendar", {"days": 7}, ctx)
    assert not outcome.is_error
    assert len(outcome.result) >= 1


async def test_get_predictions_uses_polymarket_provider(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id, {"polymarket": FakeProvider("polymarket")})
    outcome = await execute_tool("get_predictions", {}, ctx)
    assert not outcome.is_error
    assert outcome.result[0]["source"] == "polymarket"


async def test_get_earnings_calendar_uses_polymarket_provider(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id, {"polymarket": FakeProvider("polymarket")})
    outcome = await execute_tool("get_earnings_calendar", {}, ctx)
    assert not outcome.is_error
    assert outcome.result[0]["ticker"] == "TEST"


async def test_get_world_indices_returns_real_reachable_points(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id, {"finnhub": FakeProvider("finnhub")})
    outcome = await execute_tool("get_world_indices", {}, ctx)
    assert not outcome.is_error
    assert len(outcome.result) > 0


class _FixedQuoteProvider(FakeProvider):
    """Screen needs controllable change_percent, unlike FakeProvider's
    always-flat quote() — a small override rather than teaching the shared
    double a feature only this one test needs."""

    def __init__(self, quotes: list[Quote]) -> None:
        super().__init__("finnhub")
        self._quotes = {q.symbol: q for q in quotes}

    async def quote(self, symbols: list[str]) -> list[Quote]:
        return [self._quotes[s] for s in symbols if s in self._quotes]


async def test_screen_filters_by_direction_and_threshold(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    now = datetime.now(UTC)
    quotes = [
        Quote(symbol="NVDA", price=100, ts=now, change_percent=6.5, source="finnhub"),
        Quote(symbol="AAPL", price=200, ts=now, change_percent=-1.0, source="finnhub"),
        Quote(symbol="MSFT", price=300, ts=now, change_percent=0.1, source="finnhub"),
    ]
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id, {"finnhub": _FixedQuoteProvider(quotes)})
    outcome = await execute_tool("screen", {"direction": "up", "min_abs_change_percent": 5.0}, ctx)
    symbols = [m["symbol"] for m in outcome.result["matches"]]
    assert symbols == ["NVDA"]


async def test_render_chart_returns_summary_and_full_chart_spec(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id, {"alpaca": FakeProvider("alpaca")})
    outcome = await execute_tool(
        "render_chart", {"capability": "equity_candles", "symbol": "AAPL"}, ctx
    )
    assert not outcome.is_error
    assert outcome.result["rendered"] is True
    assert outcome.chart is not None
    assert outcome.chart["symbol"] == "AAPL"
    assert len(outcome.chart["candles"]) >= 1


async def test_set_focus_records_a_pin_event_and_reports_mutation(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id)
    outcome = await execute_tool("set_focus", {"node_id": "crypto.majors.btc", "weight": 1.0}, ctx)
    assert outcome.mutated is True
    async with db_pool.acquire() as conn:
        scores = await attention_service.get_scores(conn, profile_id, ["crypto.majors.btc"])
    assert scores["crypto.majors.btc"] == pytest.approx(8.0)  # EventKind.PIN weight


async def test_set_focus_rejects_unknown_node(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id)
    outcome = await execute_tool("set_focus", {"node_id": "not.a.real_node"}, ctx)
    assert outcome.is_error


async def test_add_block_reports_visible_effect_for_a_dynamic_block_node(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id)
    outcome = await execute_tool("add_block", {"node_id": "fixed_income.rates_ust.long_end"}, ctx)
    assert outcome.mutated is True
    assert outcome.result["visible_effect"] is True


async def test_add_block_is_honest_when_no_dashboard_block_exists_yet(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id)
    # commodities.energy.crude_oil is a real taxonomy node with no
    # dashboard block wired to it (only quotes/yield_curve/heatmap are).
    outcome = await execute_tool("add_block", {"node_id": "commodities.energy.crude_oil"}, ctx)
    assert outcome.mutated is True
    assert outcome.result["visible_effect"] is False


async def test_explain_layout_with_no_node_returns_the_current_layout_plan(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id)
    outcome = await execute_tool("explain_layout", {}, ctx)
    assert not outcome.is_error
    assert "blocks" in outcome.result


async def test_explain_layout_with_a_node_reconciles_with_set_focus(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id)
    await execute_tool("set_focus", {"node_id": "crypto.majors.btc"}, ctx)
    outcome = await execute_tool("explain_layout", {"node_id": "crypto.majors.btc"}, ctx)
    assert not outcome.is_error
    assert outcome.result["node_id"] == "crypto.majors.btc"
    assert outcome.result["score"] == pytest.approx(8.0)
    assert len(outcome.result["source_events"]) == 1


async def test_explain_layout_rejects_unknown_node(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id)
    outcome = await execute_tool("explain_layout", {"node_id": "not.a.real_node"}, ctx)
    assert outcome.is_error


async def test_execute_tool_unknown_name_is_a_clean_error(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id)
    outcome = await execute_tool("not_a_real_tool", {}, ctx)
    assert outcome.is_error
