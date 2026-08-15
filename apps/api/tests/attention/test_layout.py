import pytest

from app.attention.layout import (
    GRID_COLUMNS,
    MAX_COLUMNS,
    MIN_COLUMNS,
    area_weights_to_columns,
    block_scores,
    clamp_and_renormalize,
    compute_layout,
    softmax,
)


def test_block_scores_sums_only_mapped_nodes() -> None:
    scores = block_scores(
        {
            "equities.us_large_cap.broad_market": 3.0,
            "crypto.majors.btc": 1.0,
            "fixed_income.rates_ust.long_end": 5.0,
            "equities.us_large_cap.technology": 2.0,
            "some.unmapped.node": 100.0,  # must be ignored entirely
        }
    )
    assert scores["quotes"] == pytest.approx(4.0)
    assert scores["yield_curve"] == pytest.approx(5.0)
    assert scores["heatmap"] == pytest.approx(2.0)


def test_softmax_sums_to_one_and_favors_higher_score() -> None:
    weights = softmax({"a": 10.0, "b": 1.0, "c": 1.0})
    assert sum(weights.values()) == pytest.approx(1.0)
    assert weights["a"] > weights["b"] == pytest.approx(weights["c"])


def test_softmax_equal_scores_split_evenly() -> None:
    weights = softmax({"a": 2.0, "b": 2.0, "c": 2.0})
    for w in weights.values():
        assert w == pytest.approx(1 / 3)


def test_clamp_prevents_starvation_and_domination() -> None:
    # "a" would otherwise take ~99% of the weight; clamp caps it at 40% and
    # gives the floor back to "b"/"c" rather than letting them vanish.
    weights = clamp_and_renormalize({"a": 0.98, "b": 0.01, "c": 0.01})
    assert weights["a"] == pytest.approx(0.40 / (0.40 + 0.06 + 0.06))
    assert weights["b"] == pytest.approx(0.06 / (0.40 + 0.06 + 0.06))
    assert sum(weights.values()) == pytest.approx(1.0)


def test_area_weights_to_columns_sums_to_grid_columns() -> None:
    for weights in [
        {"a": 0.8, "b": 0.1, "c": 0.1},
        {"a": 1 / 3, "b": 1 / 3, "c": 1 / 3},
        {"a": 0.05, "b": 0.05, "c": 0.9},
    ]:
        columns = area_weights_to_columns(weights)
        assert sum(columns.values()) == GRID_COLUMNS
        for c in columns.values():
            assert MIN_COLUMNS <= c <= MAX_COLUMNS


def test_area_weights_to_columns_equal_split() -> None:
    columns = area_weights_to_columns({"a": 1 / 3, "b": 1 / 3, "c": 1 / 3})
    assert columns == {"a": 4, "b": 4, "c": 4}


def test_compute_layout_returns_all_three_blocks_summing_to_full_row() -> None:
    plan = compute_layout({})
    assert {b.block_type for b in plan.blocks} == {"quotes", "yield_curve", "heatmap"}
    assert sum(b.columns for b in plan.blocks) == GRID_COLUMNS
    assert sum(b.area_weight for b in plan.blocks) == pytest.approx(1.0)


def test_compute_layout_priority_matches_area_weight_rank() -> None:
    plan = compute_layout({"fixed_income.rates_ust.long_end": 20.0})
    ranked = sorted(plan.blocks, key=lambda b: b.priority)
    assert ranked[0].block_type == "yield_curve"
    assert [b.priority for b in ranked] == [1, 2, 3]


def test_golden_five_rates_clicks_over_three_days_grows_yield_curve() -> None:
    """docs/PLAN.md section 4.5 DoD: "a scripted event sequence (user clicks
    into 5 rates blocks over 3 days) produces an expected layout plan within
    tolerance." Five CLICK events (weight 2.0 each, decay.py) on rates_ust
    leaf nodes, no decay applied within the window (all same day for this
    test — decay.py's own half-life math is covered separately in
    test_decay.py) should make yield_curve dominate the row."""
    node_scores = {
        "fixed_income.rates_ust.short_end": 2.0,
        "fixed_income.rates_ust.belly": 2.0 * 2,
        "fixed_income.rates_ust.long_end": 2.0 * 2,
        # cold-start baseline ambient interest elsewhere, unchanged
        "equities.us_large_cap.broad_market": 0.2,
        "equities.us_large_cap.technology": 0.2,
    }
    plan = compute_layout(node_scores)
    by_type = {b.block_type: b for b in plan.blocks}

    assert by_type["yield_curve"].columns == MAX_COLUMNS
    # Clamped at MAX_AREA (0.40) then renormalized against the other two
    # sitting at their MIN_AREA floor (0.06 each) — same arithmetic
    # test_clamp_prevents_starvation_and_domination pins directly.
    assert by_type["yield_curve"].area_weight == pytest.approx(0.40 / (0.40 + 0.06 + 0.06))
    assert by_type["yield_curve"].priority == 1
    # quotes/heatmap still hold their floor, not squeezed to zero.
    assert by_type["quotes"].columns == MIN_COLUMNS
    assert by_type["heatmap"].columns == MIN_COLUMNS
