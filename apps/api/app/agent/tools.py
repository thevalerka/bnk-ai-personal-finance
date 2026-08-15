"""Tool definitions + executors for the Phase 4 agent (docs/PLAN.md section
5.1). Every tool is a thin wrapper over the same Gateway/Router/attention-
engine calls the rest of the app already uses for real data — no tool here
talks to a vendor directly, and none returns a number that didn't come back
from a real provider response (CLAUDE.md non-negotiable).

Tool executors take a `ToolContext` (constructed once per agent turn in
service.py) and the tool's raw JSON input, and return a `ToolOutcome`: JSON
content to hand back to Claude as the tool_result, plus optional side
effects (a chart spec for the frontend to render inline, or a flag that the
call actually mutated the user's interest profile) that service.py turns
into their own SSE event types.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

from app.api.market import (
    CALENDAR_CAPABILITIES,
    NEWS_CAPABILITIES,
    TAPE_SPEC,
    WORLD_COUNTRIES,
    _earnings_calendar,
    _predictions,
    _world_indices,
)
from app.attention import service as attention_service
from app.attention.decay import EventKind
from app.attention.layout import BLOCK_NODES
from app.attention.taxonomy import Taxonomy
from app.market.dependencies import MarketGateway
from app.market.providers.base import DateRange
from app.market.router import MarketDataUnavailable

# US Treasury only — the one full yield curve this stack can reach (FRED's
# daily tenor series are US-only), same tenor list YieldCurve.tsx already
# renders. Mirrored here rather than shared because the frontend list lives
# in TS and there's no cross-language constant to import.
_CURVE_TENORS: list[tuple[str, str]] = [
    ("DGS1MO", "1M"),
    ("DGS3MO", "3M"),
    ("DGS6MO", "6M"),
    ("DGS1", "1Y"),
    ("DGS2", "2Y"),
    ("DGS3", "3Y"),
    ("DGS5", "5Y"),
    ("DGS7", "7Y"),
    ("DGS10", "10Y"),
    ("DGS20", "20Y"),
    ("DGS30", "30Y"),
]

# Screen operates only over symbols this app already quotes for real
# elsewhere (Tape + Most Traded + World Map ETFs) — never a live screener
# API (none of this stack's free-tier providers offer one), so "screen" is
# honestly a filter over a curated universe, not real-time market breadth.
_MOST_TRADED = ["NVDA", "AAPL", "TSLA", "AMD", "AMZN", "MSFT", "META", "GOOGL", "PLTR", "SOFI"]
_SCREEN_EQUITY_UNIVERSE = sorted(
    {*TAPE_SPEC[0][1], *_MOST_TRADED, *(c.etf_symbol for c in WORLD_COUNTRIES)}
)

_BLOCK_NODE_IDS = {node_id for nodes in BLOCK_NODES.values() for node_id in nodes}


@dataclass
class ToolContext:
    gateway: MarketGateway
    db_pool: asyncpg.Pool
    taxonomy: Taxonomy
    profile_id: uuid.UUID


@dataclass
class ToolOutcome:
    result: Any
    is_error: bool = False
    # Full candle series for the frontend to render inline (render_chart) —
    # kept separate from `result` (a compact summary) so Claude's context
    # isn't spent on OHLC arrays it doesn't need to reason about.
    chart: dict[str, Any] | None = None
    # set_focus/add_block only — tells service.py to emit a "mutation" SSE
    # event so the frontend can poll /profile/layout immediately instead of
    # waiting out DynamicGrid's normal 30s interval.
    mutated: bool = False


async def _record_mentions(ctx: ToolContext, symbols: list[str]) -> None:
    """Best-effort AGENT_MENTION event (docs/PLAN.md section 4.3, weight 4.0)
    for every taxonomy node this symbol maps to — closes the loop from "the
    agent looked this up for you" back into the same interest vector that
    drives layout. Never allowed to fail the tool call itself."""
    node_ids = {nid for symbol in symbols for nid in ctx.taxonomy.nodes_for_instrument(symbol)}
    if not node_ids:
        return
    try:
        async with ctx.db_pool.acquire() as conn:
            for node_id in node_ids:
                await attention_service.record_event(
                    conn, ctx.taxonomy, ctx.profile_id, node_id, EventKind.AGENT_MENTION
                )
    except Exception:  # noqa: BLE001 - never let telemetry break the answer
        pass


def _quote_dump(quotes: list[Any]) -> list[dict[str, Any]]:
    return [q.model_dump(mode="json") for q in quotes]


async def _tool_get_quotes(ctx: ToolContext, tool_input: dict[str, Any]) -> ToolOutcome:
    capability = tool_input["capability"]
    symbols = tool_input["symbols"]
    try:
        quotes = await ctx.gateway.router.quote(capability, symbols)
    except MarketDataUnavailable as exc:
        return ToolOutcome(result={"error": str(exc)}, is_error=True)
    await _record_mentions(ctx, symbols)
    return ToolOutcome(result=_quote_dump(quotes))


async def _tool_get_candles(ctx: ToolContext, tool_input: dict[str, Any]) -> ToolOutcome:
    capability = tool_input["capability"]
    symbol = tool_input["symbol"]
    tf = tool_input.get("tf", "1d")
    limit = int(tool_input.get("limit", 30))
    try:
        candles = await ctx.gateway.router.candles(capability, symbol, tf, limit)
    except MarketDataUnavailable as exc:
        return ToolOutcome(result={"error": str(exc)}, is_error=True)
    await _record_mentions(ctx, [symbol])
    dumped = [c.model_dump(mode="json") for c in candles]
    if not dumped:
        return ToolOutcome(result={"error": "no candles reachable"}, is_error=True)
    first, last = dumped[0], dumped[-1]
    summary = {
        "symbol": symbol,
        "periods": len(dumped),
        "first": {"ts": first["ts"], "close": first["close"]},
        "last": {"ts": last["ts"], "close": last["close"]},
        "change_pct_over_window": round((last["close"] - first["close"]) / first["close"] * 100, 2)
        if first["close"]
        else None,
        "source": last["source"],
    }
    return ToolOutcome(result=summary)


async def _tool_get_curve(ctx: ToolContext, _tool_input: dict[str, Any]) -> ToolOutcome:
    series = [s for s, _ in _CURVE_TENORS]
    try:
        quotes = await ctx.gateway.router.quote("macro_series", series)
    except MarketDataUnavailable as exc:
        return ToolOutcome(result={"error": str(exc)}, is_error=True)
    by_series = {q.symbol: q for q in quotes}
    labels = dict(_CURVE_TENORS)
    points = [
        {
            "tenor": labels[s],
            "yield_pct": by_series[s].price,
            "ts": by_series[s].ts.isoformat(),
            "source": by_series[s].source,
        }
        for s in series
        if s in by_series
    ]
    if not points:
        return ToolOutcome(result={"error": "no yield curve data reachable"}, is_error=True)
    await _record_mentions(ctx, series)
    return ToolOutcome(result={"country": "US", "curve": points})


async def _tool_get_news(ctx: ToolContext, tool_input: dict[str, Any]) -> ToolOutcome:
    topics = tool_input.get("topics", [])
    since_hours = int(tool_input.get("since_hours", 24))
    since = datetime.now(UTC) - timedelta(hours=since_hours)
    items = []
    for capability in NEWS_CAPABILITIES:
        try:
            items.extend(await ctx.gateway.router.news(capability, topics, since))
        except MarketDataUnavailable:
            continue
    items.sort(key=lambda i: i.ts, reverse=True)
    if not items:
        return ToolOutcome(result={"error": "no news reachable"}, is_error=True)
    return ToolOutcome(result=[i.model_dump(mode="json") for i in items[:20]])


async def _tool_get_calendar(ctx: ToolContext, tool_input: dict[str, Any]) -> ToolOutcome:
    days = int(tool_input.get("days", 14))
    today = datetime.now(UTC).date()
    window = DateRange(start=today, end=today + timedelta(days=days))
    events = []
    for capability in CALENDAR_CAPABILITIES:
        try:
            events.extend(await ctx.gateway.router.calendar(capability, window))
        except MarketDataUnavailable:
            continue
    events.sort(key=lambda e: e.ts)
    if not events:
        return ToolOutcome(result={"error": "no calendar events reachable"}, is_error=True)
    return ToolOutcome(result=[e.model_dump(mode="json") for e in events[:30]])


async def _tool_get_predictions(ctx: ToolContext, _tool_input: dict[str, Any]) -> ToolOutcome:
    predictions = await _predictions(ctx.gateway)
    if not predictions:
        return ToolOutcome(result={"error": "no prediction markets reachable"}, is_error=True)
    return ToolOutcome(result=[p.model_dump(mode="json") for p in predictions])


async def _tool_get_earnings_calendar(ctx: ToolContext, _tool_input: dict[str, Any]) -> ToolOutcome:
    calendar = await _earnings_calendar(ctx.gateway)
    if not calendar:
        return ToolOutcome(result={"error": "no earnings calendar reachable"}, is_error=True)
    return ToolOutcome(result=[m.model_dump(mode="json") for m in calendar])


async def _tool_get_world_indices(ctx: ToolContext, _tool_input: dict[str, Any]) -> ToolOutcome:
    points = await _world_indices(ctx.gateway.router)
    reachable = [p for p in points if p.quote is not None]
    if not reachable:
        return ToolOutcome(result={"error": "no world indices reachable"}, is_error=True)
    return ToolOutcome(result=[p.model_dump(mode="json") for p in reachable])


async def _tool_screen(ctx: ToolContext, tool_input: dict[str, Any]) -> ToolOutcome:
    direction = tool_input.get("direction", "up")
    min_abs_change_pct = float(tool_input.get("min_abs_change_percent", 0.0))
    try:
        quotes = await ctx.gateway.router.quote("equity_quote", _SCREEN_EQUITY_UNIVERSE)
    except MarketDataUnavailable as exc:
        return ToolOutcome(result={"error": str(exc)}, is_error=True)
    matches = [
        q
        for q in quotes
        if q.change_percent is not None
        and abs(q.change_percent) >= min_abs_change_pct
        and ((direction == "up") == (q.change_percent >= 0))
    ]
    matches.sort(key=lambda q: abs(q.change_percent or 0), reverse=True)
    return ToolOutcome(
        result={
            "universe_size": len(_SCREEN_EQUITY_UNIVERSE),
            "universe_note": (
                "curated equity list this dashboard already tracks (Tape, Most Traded, "
                "World Map index ETFs) — not a full-market screener, no free-tier provider "
                "here offers one"
            ),
            "matches": _quote_dump(matches[:15]),
        }
    )


async def _tool_render_chart(ctx: ToolContext, tool_input: dict[str, Any]) -> ToolOutcome:
    capability = tool_input["capability"]
    symbol = tool_input["symbol"]
    tf = tool_input.get("tf", "1d")
    limit = int(tool_input.get("limit", 60))
    title = tool_input.get("title") or symbol
    try:
        candles = await ctx.gateway.router.candles(capability, symbol, tf, limit)
    except MarketDataUnavailable as exc:
        return ToolOutcome(result={"error": str(exc)}, is_error=True)
    if not candles:
        return ToolOutcome(result={"error": "no candles reachable to chart"}, is_error=True)
    await _record_mentions(ctx, [symbol])
    dumped = [c.model_dump(mode="json") for c in candles]
    return ToolOutcome(
        result={
            "rendered": True,
            "symbol": symbol,
            "periods": len(dumped),
            "source": dumped[-1]["source"],
        },
        chart={"symbol": symbol, "title": title, "candles": dumped},
    )


async def _tool_set_focus(ctx: ToolContext, tool_input: dict[str, Any]) -> ToolOutcome:
    node_id = tool_input["node_id"]
    weight = float(tool_input.get("weight", 1.0))
    try:
        async with ctx.db_pool.acquire() as conn:
            await attention_service.record_event(
                conn, ctx.taxonomy, ctx.profile_id, node_id, EventKind.PIN, magnitude=weight
            )
    except ValueError as exc:
        return ToolOutcome(result={"error": str(exc)}, is_error=True)
    return ToolOutcome(
        result={"boosted": node_id, "weight": weight},
        mutated=True,
    )


async def _tool_add_block(ctx: ToolContext, tool_input: dict[str, Any]) -> ToolOutcome:
    node_id = tool_input["node_id"]
    try:
        async with ctx.db_pool.acquire() as conn:
            await attention_service.record_event(
                conn, ctx.taxonomy, ctx.profile_id, node_id, EventKind.PIN, magnitude=1.0
            )
    except ValueError as exc:
        return ToolOutcome(result={"error": str(exc)}, is_error=True)
    # Honest about current scope (docs/DECISIONS.md ADR-0012): only 3 fixed
    # blocks (Quotes/Yield Curve/Heatmap) actually resize from this signal
    # today. A pin outside that set is still recorded for real (it will
    # show up in explain_layout and in future block types) but won't move
    # anything visible on the page yet.
    visible = node_id in _BLOCK_NODE_IDS
    return ToolOutcome(
        result={
            "pinned": node_id,
            "visible_effect": visible,
            "note": (
                "This will grow the matching dashboard block within a few seconds."
                if visible
                else (
                    "Recorded — no dedicated dashboard block exists for this asset class yet "
                    "(only Quotes/Yield Curve/Sector Heatmap dynamically resize today), but "
                    "the interest is real and will show up in explain_layout."
                )
            ),
        },
        mutated=True,
    )


async def _tool_explain_layout(ctx: ToolContext, tool_input: dict[str, Any]) -> ToolOutcome:
    node_id = tool_input.get("node_id")
    async with ctx.db_pool.acquire() as conn:
        if node_id:
            if ctx.taxonomy.node(node_id) is None and node_id not in (
                set(ctx.taxonomy.asset_class_ids()) | set(ctx.taxonomy.bucket_ids())
            ):
                return ToolOutcome(
                    result={"error": f"unknown taxonomy node: {node_id}"}, is_error=True
                )
            explanation = await attention_service.explain(conn, ctx.profile_id, node_id)
            return ToolOutcome(result=explanation.model_dump(mode="json"))
        layout = await attention_service.get_layout(conn, ctx.profile_id)
    return ToolOutcome(result=layout.model_dump(mode="json"))


TOOL_EXECUTORS: dict[str, Callable[[ToolContext, dict[str, Any]], Awaitable[ToolOutcome]]] = {
    "get_quotes": _tool_get_quotes,
    "get_candles": _tool_get_candles,
    "get_curve": _tool_get_curve,
    "get_news": _tool_get_news,
    "get_calendar": _tool_get_calendar,
    "get_predictions": _tool_get_predictions,
    "get_earnings_calendar": _tool_get_earnings_calendar,
    "get_world_indices": _tool_get_world_indices,
    "screen": _tool_screen,
    "render_chart": _tool_render_chart,
    "set_focus": _tool_set_focus,
    "add_block": _tool_add_block,
    "explain_layout": _tool_explain_layout,
}


async def execute_tool(name: str, tool_input: dict[str, Any], ctx: ToolContext) -> ToolOutcome:
    executor = TOOL_EXECUTORS.get(name)
    if executor is None:
        return ToolOutcome(result={"error": f"unknown tool: {name}"}, is_error=True)
    return await executor(ctx, tool_input)


_QUOTE_CAPABILITIES = ["equity_quote", "crypto_quote", "macro_series"]
_CANDLE_CAPABILITIES = ["equity_candles", "crypto_candles", "macro_series"]

TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_quotes",
        "description": (
            "Get real-time-ish quotes (price, change, change_percent, source, timestamp) for one "
            "or more symbols. Use capability='equity_quote' for stock/ETF tickers (e.g. AAPL, "
            "SPY), 'crypto_quote' for BTC/ETH, 'macro_series' for FRED series codes (e.g. DGS10 "
            "for the 10-year Treasury yield, VIXCLS for VIX, DCOILWTICO for WTI crude)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "capability": {"type": "string", "enum": _QUOTE_CAPABILITIES},
                "symbols": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            },
            "required": ["capability", "symbols"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_candles",
        "description": (
            "Get historical OHLC candles for one symbol and summarize the change over the "
            "window (does not return the full series as text — use render_chart if the user "
            "wants to see it plotted). Same capability rules as get_quotes, plus "
            "'equity_candles'/'crypto_candles' for candle-specific chains."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "capability": {"type": "string", "enum": _CANDLE_CAPABILITIES},
                "symbol": {"type": "string"},
                "tf": {"type": "string", "default": "1d"},
                "limit": {"type": "integer", "default": 30, "minimum": 1, "maximum": 500},
            },
            "required": ["capability", "symbol"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_curve",
        "description": (
            "Get the current US Treasury yield curve (1M through 30Y), each tenor with its real "
            "yield, source, and timestamp. US-only — this stack has no other country's full "
            "yield curve wired."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_news",
        "description": (
            "Get recent headlines merged from every wired news source (equity news, Fed "
            "statements/speeches, regional Fed speeches, SEC 8-K filings, CNBC/MarketWatch RSS), "
            "newest first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional ticker/topic filter, e.g. ['AAPL']. Empty = none.",
                },
                "since_hours": {"type": "integer", "default": 24, "minimum": 1, "maximum": 720},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_calendar",
        "description": (
            "Get upcoming calendar events — earnings dates, macro data releases (FRED), and "
            "Treasury auctions — within the given window, soonest first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"days": {"type": "integer", "default": 14, "minimum": 1, "maximum": 90}},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_predictions",
        "description": (
            "Get real, live Polymarket prediction-market odds for Fed rate decisions and "
            "S&P-direction markets — market-implied probabilities, not the agent's own forecast. "
            "Always call this rather than guessing what the market is pricing in for a Fed "
            "decision."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_earnings_calendar",
        "description": (
            "Get real per-company 'will they beat consensus EPS' prediction-market odds from "
            "Polymarket (polymarket.com/earnings) — ticker, analyst EPS estimate, beat "
            "probability, and report date. This is market-implied sentiment, not a confirmed "
            "earnings-date calendar (use get_calendar for that)."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_world_indices",
        "description": (
            "Get every tracked country's index level (proxied by its largest US-listed "
            "single-country ETF), FX rate vs USD, and government bond yield where available."
        ),
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "screen",
        "description": (
            "Filter for the biggest movers today, up or down, by percent change. Scoped to this "
            "dashboard's own curated equity universe (the Tape, Most Traded, and World Map index "
            "ETFs already tracked) — not a full market screener, since no free-tier provider "
            "here offers one. Say so if the user asks for something outside that universe."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["up", "down"], "default": "up"},
                "min_abs_change_percent": {"type": "number", "default": 0, "minimum": 0},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "render_chart",
        "description": (
            "Fetch real candle data and render it as an inline price chart on the page for the "
            "user to see, in addition to summarizing it in your answer. Use this whenever the "
            "user asks to see, plot, or chart a price history."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "capability": {"type": "string", "enum": _CANDLE_CAPABILITIES},
                "symbol": {"type": "string"},
                "tf": {"type": "string", "default": "1d"},
                "limit": {"type": "integer", "default": 60, "minimum": 2, "maximum": 500},
                "title": {"type": "string", "description": "Optional chart title override."},
            },
            "required": ["capability", "symbol"],
            "additionalProperties": False,
        },
    },
    {
        "name": "set_focus",
        "description": (
            "Explicitly boost the user's interest score for one taxonomy node (e.g. "
            "'fixed_income.rates_ust.long_end', 'equities.us_large_cap.technology', "
            "'crypto.majors.btc') — a quieter, single-node nudge to their real interest "
            "vector. Use call explain_layout first if unsure which node ids exist."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string"},
                "weight": {
                    "type": "number",
                    "default": 1.0,
                    "minimum": 0,
                    "maximum": 1,
                    "description": "0-1 multiplier on the boost strength.",
                },
            },
            "required": ["node_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "add_block",
        "description": (
            "The strong version of set_focus: pin a taxonomy node to the user's dashboard with "
            "full weight (e.g. after 'I care about European credit' — use the closest real node, "
            "there's no literal European-credit node, say so honestly if none fits). Only "
            "visibly resizes the Quotes/Yield Curve/Sector Heatmap blocks today; other asset "
            "classes are recorded for real but have no dedicated block yet — the tool result "
            "tells you which happened."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"node_id": {"type": "string"}},
            "required": ["node_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "explain_layout",
        "description": (
            "Read the user's own real interest profile: with no node_id, the current dashboard "
            "layout plan (which blocks are bigger and why); with a node_id, that node's decayed "
            "score and the real source events (clicks, dwells, pins) that produced it. Always "
            "call this rather than guessing what's driving the page's current shape."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"node_id": {"type": "string"}},
            "additionalProperties": False,
        },
    },
]

__all__ = ["TOOLS", "TOOL_EXECUTORS", "ToolContext", "ToolOutcome", "execute_tool"]
