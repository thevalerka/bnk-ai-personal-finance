import uuid
from datetime import UTC, datetime, timedelta

import asyncpg
import pytest

from app.attention.decay import HALF_LIFE, MUTE_CEILING, EventKind
from app.attention.service import ensure_profile, explain, get_scores, record_event
from app.attention.taxonomy import load_taxonomy

TAXONOMY = load_taxonomy()
NODE = "equities.us_large_cap.technology"


@pytest.fixture
async def profile_id(db_conn: asyncpg.pool.PoolConnectionProxy) -> uuid.UUID:
    pid = uuid.uuid4()
    await ensure_profile(db_conn, pid)
    return pid


async def test_record_event_rejects_unknown_node(
    db_conn: asyncpg.pool.PoolConnectionProxy, profile_id: uuid.UUID
) -> None:
    with pytest.raises(ValueError, match="unknown taxonomy node"):
        await record_event(db_conn, TAXONOMY, profile_id, "not.a.node", EventKind.CLICK)


async def test_record_event_propagates_up_the_dag(
    db_conn: asyncpg.pool.PoolConnectionProxy, profile_id: uuid.UUID
) -> None:
    await record_event(db_conn, TAXONOMY, profile_id, NODE, EventKind.CLICK)
    scores = await get_scores(db_conn, profile_id)
    assert scores[NODE] == pytest.approx(2.0)
    assert scores["equities.us_large_cap"] == pytest.approx(1.2)
    assert scores["equities"] == pytest.approx(0.6)


async def test_two_events_decay_between_them(
    db_conn: asyncpg.pool.PoolConnectionProxy, profile_id: uuid.UUID
) -> None:
    t0 = datetime(2026, 1, 1, tzinfo=UTC)
    await record_event(db_conn, TAXONOMY, profile_id, NODE, EventKind.CLICK, now=t0)
    await record_event(db_conn, TAXONOMY, profile_id, NODE, EventKind.CLICK, now=t0 + HALF_LIFE)
    scores = await get_scores(db_conn, profile_id, now=t0 + HALF_LIFE)
    # first click (2.0) decays to 1.0 after one half-life, then the second
    # click (2.0) lands on top.
    assert scores[NODE] == pytest.approx(3.0)


async def test_mute_caps_the_exact_node_but_not_ancestors(
    db_conn: asyncpg.pool.PoolConnectionProxy, profile_id: uuid.UUID
) -> None:
    # Build up real engagement first...
    await record_event(db_conn, TAXONOMY, profile_id, NODE, EventKind.CLICK)
    await record_event(db_conn, TAXONOMY, profile_id, NODE, EventKind.CLICK)
    # ...then explicitly mute it.
    await record_event(db_conn, TAXONOMY, profile_id, NODE, EventKind.MUTE)
    scores = await get_scores(db_conn, profile_id)
    assert scores[NODE] <= MUTE_CEILING
    # The mute's own -10 weight still propagated to the ancestors (real
    # negative signal), but they aren't hard-ceilinged the way the exact
    # muted node is — other nodes under "equities" can still pull it up.
    assert scores["equities"] > MUTE_CEILING


async def test_pin_after_mute_clears_the_ceiling(
    db_conn: asyncpg.pool.PoolConnectionProxy, profile_id: uuid.UUID
) -> None:
    await record_event(db_conn, TAXONOMY, profile_id, NODE, EventKind.MUTE)
    await record_event(db_conn, TAXONOMY, profile_id, NODE, EventKind.PIN)
    scores = await get_scores(db_conn, profile_id)
    # mute (-10) then pin (+8) with no time elapsed: -10 + 8 = -2, above the
    # -5 ceiling on its own, and the ceiling itself should no longer apply.
    assert scores[NODE] == pytest.approx(-2.0)


async def test_explain_leaf_only_returns_exact_node_events(
    db_conn: asyncpg.pool.PoolConnectionProxy, profile_id: uuid.UUID
) -> None:
    await record_event(db_conn, TAXONOMY, profile_id, NODE, EventKind.CLICK)
    await record_event(
        db_conn, TAXONOMY, profile_id, "equities.us_large_cap.financials", EventKind.CLICK
    )
    result = await explain(db_conn, profile_id, NODE)
    assert result.node_id == NODE
    assert result.score == pytest.approx(2.0)
    assert len(result.source_events) == 1
    assert result.source_events[0].node_id == NODE


async def test_explain_asset_class_aggregates_descendant_events(
    db_conn: asyncpg.pool.PoolConnectionProxy, profile_id: uuid.UUID
) -> None:
    await record_event(db_conn, TAXONOMY, profile_id, NODE, EventKind.CLICK)
    await record_event(
        db_conn, TAXONOMY, profile_id, "equities.us_large_cap.financials", EventKind.CLICK
    )
    result = await explain(db_conn, profile_id, "equities")
    assert result.score == pytest.approx(0.6 + 0.6)  # two clicks' grandparent contribution
    event_node_ids = {e.node_id for e in result.source_events}
    assert event_node_ids == {NODE, "equities.us_large_cap.financials"}


async def test_explain_with_no_events_yet_returns_zero_score(
    db_conn: asyncpg.pool.PoolConnectionProxy, profile_id: uuid.UUID
) -> None:
    result = await explain(db_conn, profile_id, NODE)
    assert result.score == 0.0
    assert result.last_updated is None
    assert result.source_events == []


async def test_scores_reconcile_with_explain_for_the_same_node(
    db_conn: asyncpg.pool.PoolConnectionProxy, profile_id: uuid.UUID
) -> None:
    """DoD (docs/PLAN.md P3): "explain panel numbers reconcile with the
    stored vector" — get_scores() and explain() must never disagree."""
    now = datetime(2026, 2, 1, tzinfo=UTC)
    await record_event(db_conn, TAXONOMY, profile_id, NODE, EventKind.CLICK, now=now)
    later = now + timedelta(days=1)
    vector = await get_scores(db_conn, profile_id, now=later)
    result = await explain(db_conn, profile_id, NODE, now=later)
    assert vector[NODE] == pytest.approx(result.score)
