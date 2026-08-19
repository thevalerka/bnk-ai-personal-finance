"""Market drivers graph (docs/DECISIONS.md ADR-0031/0032): which of ~20 major
instruments is pushing the others around, at a selectable timeframe.

Every input is a real Router-mediated call (candles/quote/news) — same
capabilities/providers every other endpoint already uses, just recombined
into a graph instead of a list. Three statistical legs, computed pairwise
over each node's trailing returns at the selected timeframe:

- **correlation** — plain Pearson correlation of returns (the "how are
  these normally related" backdrop). Undirected.
- **lead/lag** — correlate node A's return at t against node B's return at
  t+1; whichever direction is stronger gives that edge a direction (A
  "leads" B).
- **markov** — discretize each node's return into down/flat/up and measure
  how much knowing A's state today reduces the uncertainty in B's *next*
  state (a conditional-information-gain / mutual-information measure)
  versus B's unconditional distribution. Catches nonlinear relationships
  the linear correlation leg misses.

Plus a fourth, present-tense leg: real breaking news. Equities/sector ETFs
get a real per-symbol headline count via Finnhub's company-news feed;
everything else (rates/macro/FX/crypto/commodities) gets matched against a
small explicit keyword map over the same merged news chains `/market/news`
already fetches. News deliberately does not participate in the historical
correlation/lag/Markov legs above — RSS-based feeds don't reliably carry
long backfill, so no long history is invented for it. Its edges are
present-window-only, which is also the honest way to let a real breaking
headline outweigh a long-run statistical trend, per the product ask. The
news lookback window itself scales down with the selected timeframe
(`NEWS_LOOKBACK_HOURS_BY_TF`) — "what's driving the last 5 minutes" should
weight only genuinely recent headlines.

**Timeframe (`tf`)**: one of `1d`/`4h`/`1h`/`15m`/`5m`. FRED-backed nodes
(rates/VIX/WTI/FX — `candle_capability == "macro_candles"`) have no real
intraday series anywhere in this app's provider set, so at any intraday
`tf` they fall back to their real daily bar/quote (`data_granularity:
"daily_fallback"` on the node — the frontend flags this rather than
silently presenting daily data as if it were 5-minute data). Every other
node (equities, crypto) recomputes for real at the requested granularity.

**Volatility**: each node's recent realized volatility (stdev of returns
over its current-timeframe window, annualized by sqrt(periods/year)) is
compared against its own trailing-1-year *daily* historical volatility,
also annualized. `PERIODS_PER_YEAR` uses a 24/7-calendar approximation for
intraday timeframes (real for crypto; an honest simplification for equities,
which don't actually trade around the clock) — documented here rather than
presented as more precise than it is.

Dominance is a transparent, documented combination (see `_dominance`) of
(a) how much each node moved/made news in the selected window, normalized
against the other nodes, and (b) how much of the graph's leading/predictive
edge weight originates from that node — ranked descending, that's "today's
main drivers" (or "this hour's", "this 5 minutes'", depending on `tf`).
"""

from __future__ import annotations

import asyncio
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from statistics import mean, pstdev

from app.market.router import MarketDataUnavailable, Router
from app.market.schemas import (
    Candle,
    MarketGraphAssetClass,
    MarketGraphCorrelation,
    MarketGraphDataGranularity,
    MarketGraphEdge,
    MarketGraphNode,
    MarketGraphSnapshot,
)

NEWS_FLOW_ID = "NEWS_FLOW"
NEWS_EDGE_CAP = 10.0  # headline count that saturates a single news edge's weight to 1.0
# Total merged+equity headline count (across every tracked node) that
# saturates NEWS_FLOW's own "today" dominance signal to 1.0 — a documented
# "busy news day" reference point, not derived. Deliberately much bigger
# than NEWS_EDGE_CAP (one node's mentions vs. the whole graph's headline
# volume) and never mixed into the same min-max pool as price % moves —
# see _dominance.
NEWS_FLOW_SIGNAL_CAP = 40.0
MAX_EDGES_PER_NODE = 4
CORRELATION_EDGE_THRESHOLD = 0.5
LEAD_LAG_EDGE_THRESHOLD = 0.3
MARKOV_EDGE_THRESHOLD = 0.15
MARKOV_STATE_BAND_SIGMA = 0.5

ALLOWED_TIMEFRAMES: tuple[str, ...] = ("1d", "4h", "1h", "15m", "5m")
DEFAULT_TIMEFRAME = "1d"
HV_LOOKBACK_DAYS = 260  # ~1 trading year, for the historical-volatility baseline

# How many bars of the *selected* timeframe to pull for the "current window"
# returns/correlation/dominance/volatility legs — same limits CandleChart.tsx
# offers on the frontend, reused here so backend and chart timeframe
# semantics match.
TF_LIMITS: dict[str, int] = {"1d": 90, "4h": 180, "1h": 168, "15m": 192, "5m": 180}

# 24/7-calendar approximation (see module docstring) used to annualize a
# per-bar return stdev into a comparable scale across timeframes.
PERIODS_PER_YEAR: dict[str, float] = {
    "1d": 252.0,
    "4h": 365.0 * 24 / 4,
    "1h": 365.0 * 24,
    "15m": 365.0 * 24 * 4,
    "5m": 365.0 * 24 * 12,
}

# News relevance window shrinks with the selected timeframe — a judgment
# call (documented, not derived), not a provider limit.
NEWS_LOOKBACK_HOURS_BY_TF: dict[str, float] = {
    "1d": 12.0,
    "4h": 8.0,
    "1h": 3.0,
    "15m": 1.0,
    "5m": 0.5,
}


@dataclass(frozen=True, slots=True)
class NodeSpec:
    id: str
    label: str
    asset_class: MarketGraphAssetClass
    symbol: str
    candle_capability: str
    quote_capability: str
    is_equity_like: bool = False
    news_keywords: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_fred_backed(self) -> bool:
        # FRED is the only macro_candles provider in config/providers.yaml —
        # the one real source for rates/VIX/WTI/FX, and daily-only.
        return self.candle_capability == "macro_candles"


NODE_SPECS: tuple[NodeSpec, ...] = (
    NodeSpec("SPY", "S&P 500 (SPY)", "equity", "SPY", "equity_candles", "equity_quote", True),
    NodeSpec("QQQ", "Nasdaq 100 (QQQ)", "equity", "QQQ", "equity_candles", "equity_quote", True),
    NodeSpec("DIA", "Dow 30 (DIA)", "equity", "DIA", "equity_candles", "equity_quote", True),
    NodeSpec("XLK", "Technology (XLK)", "equity", "XLK", "equity_candles", "equity_quote", True),
    NodeSpec("XLF", "Financials (XLF)", "equity", "XLF", "equity_candles", "equity_quote", True),
    NodeSpec("XLE", "Energy (XLE)", "equity", "XLE", "equity_candles", "equity_quote", True),
    NodeSpec("XLY", "Discretionary (XLY)", "equity", "XLY", "equity_candles", "equity_quote", True),
    NodeSpec("XLI", "Industrials (XLI)", "equity", "XLI", "equity_candles", "equity_quote", True),
    NodeSpec("XLV", "Healthcare (XLV)", "equity", "XLV", "equity_candles", "equity_quote", True),
    NodeSpec(
        "DGS2",
        "2Y Treasury",
        "rates",
        "DGS2",
        "macro_candles",
        "macro_series",
        news_keywords=("fed", "rate", "treasury", "yield", "fomc"),
    ),
    NodeSpec(
        "DGS10",
        "10Y Treasury",
        "rates",
        "DGS10",
        "macro_candles",
        "macro_series",
        news_keywords=("fed", "rate", "treasury", "yield", "fomc"),
    ),
    NodeSpec(
        "DGS30",
        "30Y Treasury",
        "rates",
        "DGS30",
        "macro_candles",
        "macro_series",
        news_keywords=("fed", "rate", "treasury", "yield", "fomc"),
    ),
    NodeSpec(
        "VIXCLS",
        "VIX",
        "macro",
        "VIXCLS",
        "macro_candles",
        "macro_series",
        news_keywords=("volatility", "vix", "selloff", "correction"),
    ),
    NodeSpec(
        "DCOILWTICO",
        "WTI Crude",
        "commodity",
        "DCOILWTICO",
        "macro_candles",
        "macro_series",
        news_keywords=("oil", "crude", "opec", "energy"),
    ),
    NodeSpec(
        "BTC",
        "Bitcoin",
        "crypto",
        "BTC",
        "crypto_candles",
        "crypto_quote",
        news_keywords=("bitcoin", "crypto", "btc"),
    ),
    NodeSpec(
        "ETH",
        "Ethereum",
        "crypto",
        "ETH",
        "crypto_candles",
        "crypto_quote",
        news_keywords=("ethereum", "crypto", "eth"),
    ),
    NodeSpec(
        "DEXJPUS",
        "USD/JPY",
        "fx",
        "DEXJPUS",
        "macro_candles",
        "macro_series",
        news_keywords=("yen", "jpy", "japan", "boj"),
    ),
    NodeSpec(
        "DEXUSEU",
        "EUR/USD",
        "fx",
        "DEXUSEU",
        "macro_candles",
        "macro_series",
        news_keywords=("euro", "eur", "ecb"),
    ),
    NodeSpec(
        "DEXUSUK",
        "GBP/USD",
        "fx",
        "DEXUSUK",
        "macro_candles",
        "macro_series",
        news_keywords=("pound", "sterling", "gbp", "boe"),
    ),
)

# Non-equity merged news chains — same capabilities /market/news already
# fetches (apps/api/app/api/market.py::NEWS_CAPABILITIES), minus equity_news
# (handled per-node via Finnhub company-news instead, below).
_MERGED_NEWS_CAPABILITIES = ("macro_news", "regional_fed_news", "media_news")


@dataclass
class NodeSeries:
    """Everything computed from real candle data for one node at one
    timeframe request — the unit `compute_market_graph` builds per node
    before running the pairwise legs over it."""

    returns: dict[datetime, float]
    std: float
    last_price: float
    last_bar_change_pct: float | None
    hv_annualized: float | None
    current_annualized: float | None
    granularity: MarketGraphDataGranularity


def _returns_by_ts(candles: list[Candle]) -> dict[datetime, float]:
    closes = sorted(((c.ts, c.close) for c in candles), key=lambda pair: pair[0])
    out: dict[datetime, float] = {}
    for (_, prev_close), (ts, close) in zip(closes, closes[1:], strict=False):
        if prev_close:
            out[ts] = (close - prev_close) / prev_close
    return out


def _common_series(
    a: dict[datetime, float], b: dict[datetime, float]
) -> tuple[list[float], list[float]]:
    common = sorted(set(a) & set(b))
    return [a[t] for t in common], [b[t] for t in common]


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 3 or len(ys) != n:
        return 0.0
    mx, my = mean(xs), mean(ys)
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / n
    sx, sy = pstdev(xs), pstdev(ys)
    if sx == 0 or sy == 0:
        return 0.0
    return max(-1.0, min(1.0, cov / (sx * sy)))


def _states(values: list[float], std: float) -> list[int]:
    if std <= 0:
        return [0] * len(values)
    band = std * MARKOV_STATE_BAND_SIGMA
    return [1 if v > band else (-1 if v < -band else 0) for v in values]


def _entropy(counts: dict[int, int], total: int) -> float:
    if total == 0:
        return 0.0
    entropy = 0.0
    for count in counts.values():
        if count == 0:
            continue
        p = count / total
        entropy -= p * math.log2(p)
    return entropy


def _markov_info_gain(
    a_returns: list[float], a_std: float, b_returns: list[float], b_std: float
) -> float:
    """How much knowing A's state now reduces uncertainty in B's next
    state, normalized to [0, 1] by the max possible entropy of a 3-state
    variable (log2 3 bits). `a_returns`/`b_returns` must already be paired
    on common bars, same length, same order."""
    if len(a_returns) < 10 or len(a_returns) != len(b_returns):
        return 0.0
    a_states = _states(a_returns[:-1], a_std)
    b_next_states = _states(b_returns[1:], b_std)
    n = len(a_states)

    marginal: dict[int, int] = {-1: 0, 0: 0, 1: 0}
    for s in b_next_states:
        marginal[s] += 1
    h_marginal = _entropy(marginal, n)

    joint: dict[int, dict[int, int]] = {
        -1: {-1: 0, 0: 0, 1: 0},
        0: {-1: 0, 0: 0, 1: 0},
        1: {-1: 0, 0: 0, 1: 0},
    }
    for sa, sb in zip(a_states, b_next_states, strict=True):
        joint[sa][sb] += 1

    h_conditional = 0.0
    for counts in joint.values():
        total = sum(counts.values())
        if total == 0:
            continue
        h_conditional += (total / n) * _entropy(counts, total)

    max_bits = math.log2(3)
    return max(0.0, min(1.0, (h_marginal - h_conditional) / max_bits))


def _min_max_normalize(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi - lo < 1e-9:
        return dict.fromkeys(values, 0.0)
    return {k: (v - lo) / (hi - lo) for k, v in values.items()}


def _annualized_stdev(returns: list[float], tf: str) -> float | None:
    if len(returns) < 5:
        return None
    periods = PERIODS_PER_YEAR.get(tf)
    if not periods:
        return None
    return pstdev(returns) * math.sqrt(periods)


def _volatility_ratio(series: NodeSeries) -> float | None:
    if series.hv_annualized is None or series.hv_annualized <= 0:
        return None
    if series.current_annualized is None:
        return None
    return series.current_annualized / series.hv_annualized


def _pair_edges(
    a: str, b: str, xa: list[float], xb: list[float], std_a: float, std_b: float
) -> list[MarketGraphEdge]:
    edges: list[MarketGraphEdge] = []

    corr = _pearson(xa, xb)
    if abs(corr) >= CORRELATION_EDGE_THRESHOLD:
        src, dst = (a, b) if a < b else (b, a)
        edges.append(
            MarketGraphEdge(source=src, target=dst, weight=round(abs(corr), 4), kind="correlation")
        )

    lag_ab = max(0.0, _pearson(xa[:-1], xb[1:]))
    lag_ba = max(0.0, _pearson(xb[:-1], xa[1:]))
    if lag_ab > 0 and lag_ab >= lag_ba and lag_ab >= LEAD_LAG_EDGE_THRESHOLD:
        edges.append(MarketGraphEdge(source=a, target=b, weight=round(lag_ab, 4), kind="lead_lag"))
    elif lag_ba > 0 and lag_ba > lag_ab and lag_ba >= LEAD_LAG_EDGE_THRESHOLD:
        edges.append(MarketGraphEdge(source=b, target=a, weight=round(lag_ba, 4), kind="lead_lag"))

    markov_ab = _markov_info_gain(xa, std_a, xb, std_b)
    markov_ba = _markov_info_gain(xb, std_b, xa, std_a)
    if markov_ab > 0 and markov_ab >= markov_ba and markov_ab >= MARKOV_EDGE_THRESHOLD:
        edges.append(MarketGraphEdge(source=a, target=b, weight=round(markov_ab, 4), kind="markov"))
    elif markov_ba > 0 and markov_ba > markov_ab and markov_ba >= MARKOV_EDGE_THRESHOLD:
        edges.append(MarketGraphEdge(source=b, target=a, weight=round(markov_ba, 4), kind="markov"))

    return edges


def _full_correlation_matrix(series_by_id: dict[str, NodeSeries]) -> list[MarketGraphCorrelation]:
    """Every pairwise correlation with enough common bars to be meaningful —
    not just the thresholded edges — so the frontend's correlation-clustered
    treemap layout has a real distance metric to work with, not just the
    already-pruned top-4-per-node edge list."""
    ids = sorted(series_by_id)
    out: list[MarketGraphCorrelation] = []
    for i, a in enumerate(ids):
        for b in ids[i + 1 :]:
            xa, xb = _common_series(series_by_id[a].returns, series_by_id[b].returns)
            if len(xa) < 10:
                continue
            out.append(MarketGraphCorrelation(a=a, b=b, corr=round(_pearson(xa, xb), 4)))
    return out


async def _fetch_node_series(router: Router, spec: NodeSpec, tf: str) -> NodeSeries | None:
    granularity: MarketGraphDataGranularity = (
        "daily_fallback" if (spec.is_fred_backed and tf != "1d") else "native"
    )
    effective_tf = "1d" if spec.is_fred_backed else tf

    if effective_tf == "1d":
        # One fetch covers both the "current window" (last TF_LIMITS["1d"]
        # bars) and the 1-year HV baseline — no need to double-fetch.
        try:
            long_candles = await router.candles(
                spec.candle_capability, spec.symbol, "1d", HV_LOOKBACK_DAYS
            )
        except MarketDataUnavailable:
            return None
        if len(long_candles) < 20:
            return None
        current_candles = long_candles[-TF_LIMITS["1d"] :]
        hv_candles = long_candles
    else:
        try:
            current_candles = await router.candles(
                spec.candle_capability, spec.symbol, effective_tf, TF_LIMITS[effective_tf]
            )
        except MarketDataUnavailable:
            return None
        if len(current_candles) < 20:
            return None
        try:
            hv_candles = await router.candles(
                spec.candle_capability, spec.symbol, "1d", HV_LOOKBACK_DAYS
            )
        except MarketDataUnavailable:
            hv_candles = []

    current_returns = _returns_by_ts(current_candles)
    if len(current_returns) < 10:
        return None

    hv_returns = list(_returns_by_ts(hv_candles).values()) if hv_candles else []
    last_bar = current_candles[-1]
    last_bar_change_pct = (
        (last_bar.close - last_bar.open) / last_bar.open * 100 if last_bar.open else None
    )

    return NodeSeries(
        returns=current_returns,
        std=pstdev(current_returns.values()),
        last_price=last_bar.close,
        last_bar_change_pct=last_bar_change_pct,
        hv_annualized=_annualized_stdev(hv_returns, "1d") if len(hv_returns) >= 20 else None,
        current_annualized=_annualized_stdev(list(current_returns.values()), effective_tf),
        granularity=granularity,
    )


async def _fetch_all_series(router: Router, tf: str) -> dict[str, NodeSeries]:
    # All 19 nodes fetched concurrently, not one-at-a-time — sequential
    # fetching was measured taking ~15s wall-clock for an intraday tf (each
    # native node needs 2 real network round trips); concurrent fetches
    # bring that down to roughly the slowest single node instead of the sum
    # of all of them, which also bounds the worst-case tail latency a lot
    # tighter than 19-in-a-row ever could.
    results = await asyncio.gather(*(_fetch_node_series(router, spec, tf) for spec in NODE_SPECS))
    return {
        spec.id: series
        for spec, series in zip(NODE_SPECS, results, strict=True)
        if series is not None
    }


async def _fetch_one_change_pct(
    router: Router, tf: str, spec: NodeSpec, series: NodeSeries
) -> tuple[str, float | None]:
    """Daily-tf and daily-fallback nodes use the real live quote's
    change_percent (fresher than a possibly-lagged daily bar); native
    intraday nodes use their own most recent bar's open->close move —
    both are real numbers, just sourced differently depending on what's
    actually available for that node at that timeframe."""
    if tf == "1d" or series.granularity == "daily_fallback":
        try:
            quotes = await router.quote(spec.quote_capability, [spec.symbol])
        except MarketDataUnavailable:
            quotes = []
        if quotes and quotes[0].change_percent is not None:
            series.last_price = quotes[0].price
            return spec.id, quotes[0].change_percent
    return spec.id, series.last_bar_change_pct


async def _fetch_change_pct(
    router: Router, tf: str, series_by_id: dict[str, NodeSeries]
) -> dict[str, float]:
    specs = [spec for spec in NODE_SPECS if spec.id in series_by_id]
    results = await asyncio.gather(
        *(_fetch_one_change_pct(router, tf, spec, series_by_id[spec.id]) for spec in specs)
    )
    return {node_id: pct for node_id, pct in results if pct is not None}


async def _fetch_merged_headlines(
    router: Router, capability: str, since: datetime
) -> list[str] | None:
    try:
        items = await router.news(capability, [], since)
    except MarketDataUnavailable:
        return None
    return [item.headline.lower() for item in items]


async def _fetch_equity_news_count(router: Router, spec: NodeSpec, since: datetime) -> int | None:
    try:
        items = await router.news("equity_news", [spec.symbol], since)
    except MarketDataUnavailable:
        return None
    return len(items)


async def _fetch_news_counts(router: Router, tf: str) -> tuple[dict[str, int], int, bool]:
    """Returns (per-node headline counts, total headline volume, whether at
    least one news call actually succeeded). The third value matters on its
    own: if every news capability is unreachable, `counts` must not quietly
    fill up with real-looking zeros for the keyword-matched nodes — that
    would look like "checked, found nothing" when it's really "couldn't
    check at all", and NEWS_FLOW shouldn't appear in the graph at all in
    that case (docs/DECISIONS.md ADR-0031). Every real network call here
    (3 merged feeds + one per equity/sector node) runs concurrently, not
    sequentially — same reasoning as _fetch_all_series."""
    since = datetime.now(tz=UTC) - timedelta(hours=NEWS_LOOKBACK_HOURS_BY_TF.get(tf, 12.0))

    merged_results = await asyncio.gather(
        *(
            _fetch_merged_headlines(router, capability, since)
            for capability in _MERGED_NEWS_CAPABILITIES
        )
    )
    merged_reachable = any(result is not None for result in merged_results)
    merged_headlines = [
        headline for result in merged_results if result is not None for headline in result
    ]

    equity_specs = [spec for spec in NODE_SPECS if spec.is_equity_like]
    equity_results = await asyncio.gather(
        *(_fetch_equity_news_count(router, spec, since) for spec in equity_specs)
    )

    counts: dict[str, int] = {}
    total = len(merged_headlines)
    any_reachable = merged_reachable
    for spec, count in zip(equity_specs, equity_results, strict=True):
        if count is None:
            continue
        any_reachable = True
        counts[spec.id] = count
        total += count

    for spec in NODE_SPECS:
        if not spec.is_equity_like and spec.news_keywords and merged_reachable:
            counts[spec.id] = sum(
                1
                for headline in merged_headlines
                if any(kw in headline for kw in spec.news_keywords)
            )

    return counts, total, any_reachable


def _dominance(
    node_ids: list[str],
    change_pct: dict[str, float],
    total_news: int,
    outgoing_weight: dict[str, float],
) -> dict[str, float]:
    # NEWS_FLOW's "today" signal (a real headline count, typically tens) and
    # every price node's (a real % move, typically low single digits) are
    # not the same unit — min-max normalizing them together would let
    # whichever one has the numerically bigger raw magnitude swamp the
    # other on *any* real news day (caught by eyeballing a live render: a
    # busy day gave NEWS_FLOW ~half the whole grid). Each is normalized
    # within its own kind instead: price nodes against each other, NEWS_FLOW
    # against a fixed reference scale (NEWS_FLOW_SIGNAL_CAP) — the same
    # "cap, don't compete on raw magnitude" treatment its own outgoing edge
    # weights already get (NEWS_EDGE_CAP).
    price_ids = [node_id for node_id in node_ids if node_id != NEWS_FLOW_ID]
    price_signal = {node_id: abs(change_pct.get(node_id, 0.0)) for node_id in price_ids}
    today_norm = _min_max_normalize(price_signal)
    if NEWS_FLOW_ID in node_ids:
        today_norm[NEWS_FLOW_ID] = min(1.0, total_news / NEWS_FLOW_SIGNAL_CAP)

    outgoing_norm = _min_max_normalize(
        {node_id: outgoing_weight.get(node_id, 0.0) for node_id in node_ids}
    )
    return {
        node_id: round(
            0.5 * today_norm.get(node_id, 0.0) + 0.5 * outgoing_norm.get(node_id, 0.0), 4
        )
        for node_id in node_ids
    }


async def compute_market_graph(router: Router, tf: str = DEFAULT_TIMEFRAME) -> MarketGraphSnapshot:
    if tf not in ALLOWED_TIMEFRAMES:
        tf = DEFAULT_TIMEFRAME

    series_by_id = await _fetch_all_series(router, tf)
    change_pct = await _fetch_change_pct(router, tf, series_by_id)
    news_counts, total_news, news_reachable = await _fetch_news_counts(router, tf)

    price_ids = sorted(series_by_id)
    price_edges: list[MarketGraphEdge] = []
    for i, a in enumerate(price_ids):
        for b in price_ids[i + 1 :]:
            xa, xb = _common_series(series_by_id[a].returns, series_by_id[b].returns)
            if len(xa) < 10:
                continue
            price_edges.extend(_pair_edges(a, b, xa, xb, series_by_id[a].std, series_by_id[b].std))

    news_edges = [
        MarketGraphEdge(
            source=NEWS_FLOW_ID,
            target=node_id,
            weight=round(min(1.0, count / NEWS_EDGE_CAP), 4),
            kind="news",
        )
        for node_id, count in news_counts.items()
        if count > 0
    ]

    all_ids = [*price_ids, NEWS_FLOW_ID] if news_reachable else list(price_ids)

    outgoing_weight: dict[str, float] = defaultdict(float)
    for edge in (*price_edges, *news_edges):
        if edge.kind in ("lead_lag", "markov", "news"):
            outgoing_weight[edge.source] += edge.weight

    dominance = _dominance(all_ids, change_pct, total_news, outgoing_weight)

    grouped_edges: dict[str, list[MarketGraphEdge]] = defaultdict(list)
    for edge in (*price_edges, *news_edges):
        grouped_edges[edge.source].append(edge)
    pruned_edges: list[MarketGraphEdge] = []
    for source_edges in grouped_edges.values():
        source_edges.sort(key=lambda e: e.weight, reverse=True)
        pruned_edges.extend(source_edges[:MAX_EDGES_PER_NODE])

    correlations = _full_correlation_matrix(series_by_id)

    node_by_id = {spec.id: spec for spec in NODE_SPECS}
    nodes: list[MarketGraphNode] = []
    for node_id in price_ids:
        spec = node_by_id[node_id]
        series = series_by_id[node_id]
        nodes.append(
            MarketGraphNode(
                id=spec.id,
                label=spec.label,
                asset_class=spec.asset_class,
                symbol=spec.symbol,
                last_price=series.last_price,
                change_pct=change_pct.get(node_id),
                dominance_score=dominance.get(node_id, 0.0),
                rank=0,
                data_granularity=series.granularity,
                volatility_ratio=_volatility_ratio(series),
            )
        )
    if news_reachable:
        nodes.append(
            MarketGraphNode(
                id=NEWS_FLOW_ID,
                label="Breaking News",
                asset_class="news",
                symbol=NEWS_FLOW_ID,
                last_price=None,
                change_pct=None,
                dominance_score=dominance.get(NEWS_FLOW_ID, 0.0),
                rank=0,
                data_granularity="native",
                volatility_ratio=None,
            )
        )

    nodes.sort(key=lambda n: n.dominance_score, reverse=True)
    for rank, node in enumerate(nodes, start=1):
        node.rank = rank

    return MarketGraphSnapshot(
        computed_at=datetime.now(tz=UTC), nodes=nodes, edges=pruned_edges, correlations=correlations
    )
