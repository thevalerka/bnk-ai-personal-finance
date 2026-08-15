from datetime import timedelta

import pytest

from app.attention.decay import (
    EVENT_WEIGHTS,
    HALF_LIFE,
    EventKind,
    apply_event,
    decay_factor,
    decayed_score,
    propagate,
)
from app.attention.taxonomy import load_taxonomy


def test_decay_factor_at_zero_elapsed_is_one() -> None:
    assert decay_factor(timedelta(0)) == 1.0


def test_decay_factor_at_one_half_life_is_half() -> None:
    assert decay_factor(HALF_LIFE) == pytest.approx(0.5)


def test_decay_factor_at_two_half_lives_is_quarter() -> None:
    assert decay_factor(HALF_LIFE * 2) == pytest.approx(0.25)


def test_decayed_score_scales_stored_score() -> None:
    assert decayed_score(10.0, HALF_LIFE) == pytest.approx(5.0)


def test_apply_event_decays_then_adds() -> None:
    # score of 4 one half-life ago decays to 2, then a click (weight 2.0) lands.
    new_score = apply_event(stored_score=4.0, elapsed_since_last_update=HALF_LIFE, weight=2.0)
    assert new_score == pytest.approx(4.0)


def test_incremental_update_matches_summing_full_history() -> None:
    """The whole point of decay-on-read: replaying events one at a time with
    apply_event() must equal summing every event's individually-decayed
    contribution from scratch — otherwise the lazy-update shortcut is wrong."""
    half_life_seconds = HALF_LIFE.total_seconds()
    now = timedelta(days=10)
    event_times = [timedelta(days=d) for d in (0, 2, 5, 9)]
    weights = [1.0, 2.0, 0.5, 3.0]

    # Incremental: apply_event walked forward in time order.
    score = 0.0
    last_updated = event_times[0]
    for t, w in zip(event_times, weights, strict=True):
        score = apply_event(score, t - last_updated, w)
        last_updated = t
    incremental_at_now = decayed_score(score, now - last_updated)

    # From-scratch: sum each event's own decay to `now`.
    from_scratch = sum(
        w * 2.0 ** (-((now - t).total_seconds() / half_life_seconds))
        for t, w in zip(event_times, weights, strict=True)
    )

    assert incremental_at_now == pytest.approx(from_scratch)


def test_every_event_kind_has_a_weight() -> None:
    for kind in EventKind:
        assert kind in EVENT_WEIGHTS


def test_mute_is_the_only_negative_weight() -> None:
    negatives = [k for k, w in EVENT_WEIGHTS.items() if w < 0]
    assert negatives == [EventKind.MUTE]


def test_propagate_applies_child_parent_grandparent_factors() -> None:
    taxonomy = load_taxonomy()
    node_id = "equities.us_large_cap.technology"
    contributions = propagate(taxonomy, node_id, weight=2.0)
    assert contributions == {
        "equities.us_large_cap.technology": 2.0,
        "equities.us_large_cap": 1.2,
        "equities": 0.6,
    }


def test_propagate_from_an_asset_class_only_hits_itself() -> None:
    taxonomy = load_taxonomy()
    contributions = propagate(taxonomy, "equities", weight=1.0)
    assert contributions == {"equities": 1.0}
