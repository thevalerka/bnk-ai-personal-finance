"""Market drivers graph (docs/DECISIONS.md ADR-0031): which of ~20 major
instruments is pushing the others around today.

Every input is a real Router-mediated call (candles/quote/news) — same
capabilities/providers every other endpoint already uses, just recombined
into a graph instead of a list. Three legs, computed pairwise over the
trailing 90 daily bars' returns:

- **correlation** — plain Pearson correlation of daily returns (the "how
  are these normally related" backdrop). Undirected.
- **lead/lag** — correlate node A's return at t against node B's return at
  t+1; whichever direction is stronger gives that edge a direction (A
  "leads" B).
- **markov** — discretize each node's daily return into down/flat/up and
  measure how much knowing A's state today reduces the uncertainty in B's
  *next* state (a conditional-information-gain / mutual-information
  measure) versus B's unconditional distribution. Catches nonlinear
  relationships the linear correlation leg misses.

Plus a fourth, present-tense leg: real breaking news. Equities/sector ETFs
get a real per-symbol headline count via Finnhub's company-news feed;
everything else (rates/macro/FX/crypto/commodities) gets matched against a
small explicit keyword map over the same merged news chains `/market/news`
already fetches. News deliberately does not participate in the historical
correlation/lag/Markov legs above — RSS-based feeds don't reliably carry 90
days of backfill, so no long history is invented for it. Its edges are
today-only, which is also the honest way to let a real breaking headline
outweigh a long-run statistical trend, per the product ask.

Dominance is a transparent, documented combination (see `_dominance`) of
(a) how much each node moved/made news today, normalized against the other
nodes, and (b) how much of the graph's leading/predictive edge weight
originates from that node — ranked descending, that's "today's main
drivers."
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from statistics import mean, pstdev

from app.market.router import MarketDataUnavailable, Router
from app.market.schemas import (
    Candle,
    MarketGraphAssetClass,
    MarketGraphEdge,
    MarketGraphNode,
    MarketGraphSnapshot,
)

NEWS_FLOW_ID = "NEWS_FLOW"
CANDLE_LOOKBACK_DAYS = 90
NEWS_LOOKBACK_HOURS = 12
NEWS_EDGE_CAP = 10.0  # headline count that saturates a news edge's weight to 1.0
MAX_EDGES_PER_NODE = 4
CORRELATION_EDGE_THRESHOLD = 0.5
LEAD_LAG_EDGE_THRESHOLD = 0.3
MARKOV_EDGE_THRESHOLD = 0.15
MARKOV_STATE_BAND_SIGMA = 0.5


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


def _returns_by_date(candles: list[Candle]) -> dict[date, float]:
    closes = sorted(((c.ts.date(), c.close) for c in candles), key=lambda pair: pair[0])
    out: dict[date, float] = {}
    for (_, prev_close), (day, close) in zip(closes, closes[1:], strict=False):
        if prev_close:
            out[day] = (close - prev_close) / prev_close
    return out


def _common_series(a: dict[date, float], b: dict[date, float]) -> tuple[list[float], list[float]]:
    common_dates = sorted(set(a) & set(b))
    return [a[d] for d in common_dates], [b[d] for d in common_dates]


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
    """How much knowing A's state today reduces uncertainty in B's next-day
    state, normalized to [0, 1] by the max possible entropy of a 3-state
    variable (log2 3 bits). `a_returns`/`b_returns` must already be paired
    on common trading days, same length, same order."""
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


async def _fetch_returns(
    router: Router,
) -> tuple[dict[str, dict[date, float]], dict[str, float], dict[str, float]]:
    returns_by_id: dict[str, dict[date, float]] = {}
    std_by_id: dict[str, float] = {}
    last_price: dict[str, float] = {}
    for spec in NODE_SPECS:
        try:
            candles = await router.candles(
                spec.candle_capability, spec.symbol, "1d", CANDLE_LOOKBACK_DAYS
            )
        except MarketDataUnavailable:
            continue
        if len(candles) < 20:
            continue
        rbd = _returns_by_date(candles)
        if len(rbd) < 10:
            continue
        returns_by_id[spec.id] = rbd
        std_by_id[spec.id] = pstdev(rbd.values())
        last_price[spec.id] = candles[-1].close
    return returns_by_id, std_by_id, last_price


async def _fetch_today_moves(router: Router, last_price: dict[str, float]) -> dict[str, float]:
    change_pct: dict[str, float] = {}
    for spec in NODE_SPECS:
        try:
            quotes = await router.quote(spec.quote_capability, [spec.symbol])
        except MarketDataUnavailable:
            continue
        if not quotes:
            continue
        if quotes[0].change_percent is not None:
            change_pct[spec.id] = quotes[0].change_percent
        last_price[spec.id] = quotes[0].price
    return change_pct


async def _fetch_news_counts(router: Router) -> tuple[dict[str, int], int, bool]:
    """Returns (per-node headline counts, total headline volume, whether at
    least one news call actually succeeded). The third value matters on its
    own: if every news capability is unreachable, `counts` must not quietly
    fill up with real-looking zeros for the keyword-matched nodes — that
    would look like "checked, found nothing" when it's really "couldn't
    check at all", and NEWS_FLOW shouldn't appear in the graph at all in
    that case (docs/DECISIONS.md ADR-0031)."""
    since = datetime.now(tz=UTC) - timedelta(hours=NEWS_LOOKBACK_HOURS)

    merged_headlines: list[str] = []
    merged_reachable = False
    for capability in _MERGED_NEWS_CAPABILITIES:
        try:
            items = await router.news(capability, [], since)
        except MarketDataUnavailable:
            continue
        merged_reachable = True
        merged_headlines.extend(item.headline.lower() for item in items)

    counts: dict[str, int] = {}
    total = len(merged_headlines)
    any_reachable = merged_reachable
    for spec in NODE_SPECS:
        if spec.is_equity_like:
            try:
                items = await router.news("equity_news", [spec.symbol], since)
            except MarketDataUnavailable:
                continue
            any_reachable = True
            counts[spec.id] = len(items)
            total += len(items)
        elif spec.news_keywords and merged_reachable:
            counts[spec.id] = sum(
                1
                for headline in merged_headlines
                if any(kw in headline for kw in spec.news_keywords)
            )
    return counts, total, any_reachable


def _dominance(
    node_ids: list[str],
    change_pct: dict[str, float],
    news_counts: dict[str, int],
    total_news: int,
    outgoing_weight: dict[str, float],
) -> dict[str, float]:
    today_signal: dict[str, float] = {}
    for node_id in node_ids:
        if node_id == NEWS_FLOW_ID:
            today_signal[node_id] = float(total_news)
        else:
            today_signal[node_id] = abs(change_pct.get(node_id, 0.0))

    today_norm = _min_max_normalize(today_signal)
    outgoing_norm = _min_max_normalize(
        {node_id: outgoing_weight.get(node_id, 0.0) for node_id in node_ids}
    )
    return {
        node_id: round(0.5 * today_norm[node_id] + 0.5 * outgoing_norm[node_id], 4)
        for node_id in node_ids
    }


async def compute_market_graph(router: Router) -> MarketGraphSnapshot:
    returns_by_id, std_by_id, last_price = await _fetch_returns(router)
    change_pct = await _fetch_today_moves(router, last_price)
    news_counts, total_news, news_reachable = await _fetch_news_counts(router)

    price_ids = sorted(returns_by_id)
    price_edges: list[MarketGraphEdge] = []
    for i, a in enumerate(price_ids):
        for b in price_ids[i + 1 :]:
            xa, xb = _common_series(returns_by_id[a], returns_by_id[b])
            if len(xa) < 10:
                continue
            price_edges.extend(_pair_edges(a, b, xa, xb, std_by_id[a], std_by_id[b]))

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

    dominance = _dominance(all_ids, change_pct, news_counts, total_news, outgoing_weight)

    grouped_edges: dict[str, list[MarketGraphEdge]] = defaultdict(list)
    for edge in (*price_edges, *news_edges):
        grouped_edges[edge.source].append(edge)
    pruned_edges: list[MarketGraphEdge] = []
    for source_edges in grouped_edges.values():
        source_edges.sort(key=lambda e: e.weight, reverse=True)
        pruned_edges.extend(source_edges[:MAX_EDGES_PER_NODE])

    node_by_id = {spec.id: spec for spec in NODE_SPECS}
    nodes: list[MarketGraphNode] = []
    for node_id in price_ids:
        spec = node_by_id[node_id]
        nodes.append(
            MarketGraphNode(
                id=spec.id,
                label=spec.label,
                asset_class=spec.asset_class,
                symbol=spec.symbol,
                last_price=last_price.get(node_id),
                change_pct=change_pct.get(node_id),
                dominance_score=dominance.get(node_id, 0.0),
                rank=0,
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
            )
        )

    nodes.sort(key=lambda n: n.dominance_score, reverse=True)
    for rank, node in enumerate(nodes, start=1):
        node.rank = rank

    return MarketGraphSnapshot(computed_at=datetime.now(tz=UTC), nodes=nodes, edges=pruned_edges)
