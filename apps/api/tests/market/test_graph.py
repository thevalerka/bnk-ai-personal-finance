from datetime import UTC, date, datetime, timedelta

import pytest

from app.market.graph import (
    NEWS_FLOW_ID,
    NODE_SPECS,
    _common_series,
    _dominance,
    _markov_info_gain,
    _min_max_normalize,
    _pair_edges,
    _pearson,
    _returns_by_date,
    compute_market_graph,
)
from app.market.providers.base import CallSpec, DateRange, Provider, ProviderError
from app.market.router import Router
from app.market.schemas import Candle, NewsItem, Quote


def test_pearson_perfectly_correlated_series() -> None:
    xs = [0.01, -0.02, 0.03, -0.01, 0.02]
    ys = [0.02, -0.04, 0.06, -0.02, 0.04]  # ys = 2 * xs

    assert _pearson(xs, ys) == pytest.approx(1.0)


def test_pearson_perfectly_anticorrelated_series() -> None:
    xs = [0.01, -0.02, 0.03, -0.01, 0.02]
    ys = [-x for x in xs]

    assert _pearson(xs, ys) == pytest.approx(-1.0)


def test_pearson_zero_variance_series_is_zero_not_a_crash() -> None:
    assert _pearson([0.0, 0.0, 0.0], [0.01, -0.01, 0.02]) == 0.0


def test_pearson_too_few_points_is_zero() -> None:
    assert _pearson([0.01, 0.02], [0.01, 0.02]) == 0.0


def test_returns_by_date_computes_pct_change_in_chronological_order() -> None:
    candles = [
        Candle(
            symbol="X",
            ts=datetime(2026, 1, 3, tzinfo=UTC),
            open=1,
            high=1,
            low=1,
            close=110,
            source="t",
        ),
        Candle(
            symbol="X",
            ts=datetime(2026, 1, 1, tzinfo=UTC),
            open=1,
            high=1,
            low=1,
            close=100,
            source="t",
        ),
        Candle(
            symbol="X",
            ts=datetime(2026, 1, 2, tzinfo=UTC),
            open=1,
            high=1,
            low=1,
            close=105,
            source="t",
        ),
    ]

    returns = _returns_by_date(candles)

    assert returns[date(2026, 1, 2)] == pytest.approx(0.05)
    assert returns[date(2026, 1, 3)] == pytest.approx(105 / 105 * 0 + (110 - 105) / 105)
    assert date(2026, 1, 1) not in returns  # first bar has no prior close to diff against


def test_common_series_intersects_and_sorts_by_date() -> None:
    a = {date(2026, 1, 1): 0.01, date(2026, 1, 2): 0.02, date(2026, 1, 3): 0.03}
    b = {date(2026, 1, 2): 0.5, date(2026, 1, 3): 0.6, date(2026, 1, 4): 0.7}

    xa, xb = _common_series(a, b)

    assert xa == [0.02, 0.03]
    assert xb == [0.5, 0.6]


def test_markov_info_gain_is_high_when_a_deterministically_sets_bs_next_state() -> None:
    # B's next state always mirrors A's current sign — a deterministic
    # dependency an info-gain measure should catch clearly.
    a_returns = [0.02, -0.02, 0.02, -0.02, 0.02, -0.02, 0.02, -0.02, 0.02, -0.02, 0.02, -0.02]
    b_returns = [0.0, 0.02, -0.02, 0.02, -0.02, 0.02, -0.02, 0.02, -0.02, 0.02, -0.02, 0.02]
    std = 0.01

    gain = _markov_info_gain(a_returns, std, b_returns, std)

    assert gain > 0.5


def test_markov_info_gain_is_near_zero_for_independent_noise() -> None:
    # A alternates deterministically; B is flat/near-zero regardless of A's
    # state, so knowing A should tell you almost nothing about B's next move.
    a_returns = [0.02, -0.02] * 6
    b_returns = [0.0] * 12
    std = 0.01

    gain = _markov_info_gain(a_returns, std, b_returns, std)

    assert gain == pytest.approx(0.0)


def test_markov_info_gain_handles_too_few_points() -> None:
    assert _markov_info_gain([0.01, 0.02], 0.01, [0.01, 0.02], 0.01) == 0.0


def test_min_max_normalize_scales_into_zero_one() -> None:
    normalized = _min_max_normalize({"a": 1.0, "b": 3.0, "c": 5.0})

    assert normalized == {"a": 0.0, "b": 0.5, "c": 1.0}


def test_min_max_normalize_flat_input_is_all_zero_not_a_div_by_zero() -> None:
    assert _min_max_normalize({"a": 2.0, "b": 2.0}) == {"a": 0.0, "b": 0.0}


def test_min_max_normalize_empty_input() -> None:
    assert _min_max_normalize({}) == {}


def test_pair_edges_gives_leader_the_directed_lead_lag_edge() -> None:
    # B's return is A's return from the previous step — A unambiguously leads.
    a = [0.02, -0.02, 0.03, -0.01, 0.02, -0.03, 0.01, -0.02, 0.02, -0.01, 0.03]
    b = [0.0, 0.02, -0.02, 0.03, -0.01, 0.02, -0.03, 0.01, -0.02, 0.02, -0.01]

    edges = _pair_edges("A", "B", a, b, 0.02, 0.02)

    lead_lag = [e for e in edges if e.kind == "lead_lag"]
    assert len(lead_lag) == 1
    assert lead_lag[0].source == "A"
    assert lead_lag[0].target == "B"
    assert lead_lag[0].weight > 0


def test_pair_edges_no_edges_for_genuinely_unrelated_series() -> None:
    # Two independently-drawn synthetic return series, pre-checked to sit
    # well below every edge threshold on all three legs (correlation,
    # lead/lag, markov) — see docs/DECISIONS.md ADR-0031 for why a plain
    # alternating +/- series doesn't work for this: it's actually perfectly
    # (anti)correlated, not unrelated.
    a = [
        -0.0105,
        0.0018,
        -0.0052,
        0.0042,
        0.005,
        -0.0174,
        -0.0195,
        0.0135,
        -0.0096,
        -0.0106,
        0.0198,
        -0.0012,
        0.0135,
        -0.0009,
        0.0056,
        -0.014,
        0.0054,
        0.0147,
        0.0009,
        0.0097,
        0.0069,
        -0.0174,
        0.0103,
        0.0036,
        -0.0079,
        -0.0188,
        0.0146,
        -0.0011,
        0.0088,
        0.0152,
        0.0086,
        0.0168,
        -0.0042,
        0.012,
        -0.0022,
        0.0174,
        0.0152,
        -0.0161,
        -0.0146,
        -0.0113,
    ]
    b = [
        0.0186,
        -0.0026,
        0.0051,
        -0.008,
        0.0003,
        -0.0046,
        -0.006,
        0.0034,
        0.0034,
        0.0162,
        0.0073,
        0.0172,
        0.0143,
        0.0196,
        0.0069,
        -0.0135,
        0.0144,
        0.0186,
        0.0162,
        0.0028,
        0.0086,
        -0.0116,
        0.0133,
        0.0029,
        -0.0086,
        -0.0175,
        0.0142,
        0.0196,
        -0.0165,
        0.012,
        -0.0036,
        -0.014,
        -0.0082,
        0.0108,
        0.0149,
        -0.0182,
        0.0046,
        -0.0182,
        0.0087,
        -0.0068,
    ]

    edges = _pair_edges("A", "B", a, b, 0.012, 0.012)

    assert edges == []


def test_dominance_ranks_bigger_mover_and_bigger_news_day_higher() -> None:
    scores = _dominance(
        node_ids=["A", "B", NEWS_FLOW_ID],
        change_pct={"A": 5.0, "B": 0.1},
        news_counts={},
        total_news=20,
        outgoing_weight={"A": 0.0, "B": 0.0, NEWS_FLOW_ID: 0.0},
    )

    assert scores["A"] > scores["B"]
    assert scores[NEWS_FLOW_ID] > scores["B"]


class _SyntheticProvider:
    """Router-mediated test double: returns a caller-supplied, per-symbol
    synthetic candle series so correlation/lead-lag/markov behavior can be
    exercised end-to-end through compute_market_graph, not just unit-by-unit."""

    def __init__(
        self,
        name: str,
        candles_by_symbol: dict[str, list[Candle]],
        quotes_by_symbol: dict[str, Quote],
        news_items: list[NewsItem] | None = None,
    ) -> None:
        self.name = name
        self._candles = candles_by_symbol
        self._quotes = quotes_by_symbol
        self._news = news_items or []

    async def quote(self, symbols: list[str]) -> list[Quote]:
        return [self._quotes[s] for s in symbols if s in self._quotes]

    async def candles(self, symbol: str, tf: str, limit: int) -> list[Candle]:
        return self._candles.get(symbol, [])

    async def news(self, topics: list[str], since: datetime) -> list[NewsItem]:
        if not topics:
            return self._news
        return [item for item in self._news if item.tickers and item.tickers[0] in topics]

    async def calendar(self, window: DateRange) -> list[object]:
        raise NotImplementedError

    def cost(self, call: CallSpec) -> int:
        return 1


def _synthetic_candles(symbol: str, closes: list[float], start: date) -> list[Candle]:
    return [
        Candle(
            symbol=symbol,
            ts=datetime.combine(start + timedelta(days=i), datetime.min.time(), tzinfo=UTC),
            open=c,
            high=c,
            low=c,
            close=c,
            source="test",
        )
        for i, c in enumerate(closes)
    ]


def _build_router(candles_by_symbol: dict[str, list[Candle]]) -> Router:
    from fakeredis import FakeAsyncRedis

    from app.market.budget import BudgetManager
    from app.market.cache import Cache

    now = datetime.now(tz=UTC)
    quotes_by_symbol = {
        symbol: Quote(
            symbol=symbol, price=candles[-1].close, ts=now, change_percent=0.1, source="test"
        )
        for symbol, candles in candles_by_symbol.items()
    }
    provider = _SyntheticProvider("test", candles_by_symbol, quotes_by_symbol)
    empty_news = _SyntheticProvider("test-news", {}, {}, news_items=[])

    chains: dict[str, list[str]] = {}
    providers: dict[str, Provider] = {"test": provider, "test-news": empty_news}  # type: ignore[dict-item]
    for spec in NODE_SPECS:
        chains.setdefault(spec.candle_capability, ["test"])
        chains.setdefault(spec.quote_capability, ["test"])
    chains["equity_news"] = ["test"]
    chains["macro_news"] = ["test-news"]
    chains["regional_fed_news"] = ["test-news"]
    chains["media_news"] = ["test-news"]

    redis = FakeAsyncRedis()
    budget = BudgetManager(redis, {})
    cache = Cache(redis)
    return Router(providers=providers, chains=chains, budget=budget, cache=cache)


async def test_compute_market_graph_ranks_a_leading_series_above_a_follower_and_bystanders() -> (
    None
):
    start = date(2026, 1, 1)
    # SPY leads QQQ by one day (QQQ's close today mirrors SPY's move
    # yesterday); the rest of the universe is flat noise that shouldn't
    # dominate.
    base = 100.0
    spy_closes = [base]
    for i in range(1, 60):
        spy_closes.append(spy_closes[-1] * (1.02 if i % 2 == 0 else 0.98))
    qqq_closes = [base, base] + spy_closes[1:-1]

    candles_by_symbol: dict[str, list[Candle]] = {
        "SPY": _synthetic_candles("SPY", spy_closes, start),
        "QQQ": _synthetic_candles("QQQ", qqq_closes, start),
    }
    flat_symbols = [spec.symbol for spec in NODE_SPECS if spec.symbol not in ("SPY", "QQQ")]
    for symbol in flat_symbols:
        candles_by_symbol[symbol] = _synthetic_candles(symbol, [base] * 60, start)

    router = _build_router(candles_by_symbol)

    snapshot = await compute_market_graph(router)

    ids = {n.id for n in snapshot.nodes}
    assert "SPY" in ids
    assert "QQQ" in ids
    lead_lag_edges = [
        e
        for e in snapshot.edges
        if e.kind == "lead_lag" and e.source == "SPY" and e.target == "QQQ"
    ]
    assert lead_lag_edges, "expected SPY to lead QQQ"

    spy_node = next(n for n in snapshot.nodes if n.id == "SPY")
    flat_ranks = [n.rank for n in snapshot.nodes if n.id in flat_symbols]
    assert all(spy_node.rank < r for r in flat_ranks)


async def test_compute_market_graph_degrades_when_every_provider_is_down() -> None:
    from fakeredis import FakeAsyncRedis

    from app.market.budget import BudgetManager
    from app.market.cache import Cache

    class DownProvider:
        name = "down"

        async def quote(self, symbols: list[str]) -> list[Quote]:
            raise ProviderError("down")

        async def candles(self, symbol: str, tf: str, limit: int) -> list[Candle]:
            raise ProviderError("down")

        async def news(self, topics: list[str], since: datetime) -> list[NewsItem]:
            raise ProviderError("down")

        async def calendar(self, window: DateRange) -> list[object]:
            raise ProviderError("down")

        def cost(self, call: CallSpec) -> int:
            return 1

    chains: dict[str, list[str]] = {}
    for spec in NODE_SPECS:
        chains.setdefault(spec.candle_capability, ["down"])
        chains.setdefault(spec.quote_capability, ["down"])
    chains["equity_news"] = ["down"]
    chains["macro_news"] = ["down"]
    chains["regional_fed_news"] = ["down"]
    chains["media_news"] = ["down"]

    redis = FakeAsyncRedis()
    budget = BudgetManager(redis, {})
    cache = Cache(redis)
    router = Router(
        providers={"down": DownProvider()},  # type: ignore[dict-item]
        chains=chains,
        budget=budget,
        cache=cache,
    )

    snapshot = await compute_market_graph(router)

    assert snapshot.nodes == []
    assert snapshot.edges == []
