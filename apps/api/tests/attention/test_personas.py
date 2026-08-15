import uuid

import asyncpg
import pytest

from app.attention.layout import compute_layout
from app.attention.personas import list_personas, load_persona, replay_persona
from app.attention.service import get_scores
from app.attention.taxonomy import load_taxonomy

TAXONOMY = load_taxonomy()


def test_list_personas_covers_the_four_from_the_plan() -> None:
    names = {p.name for p in list_personas()}
    assert names == {"macro", "equity_pm", "options_trader", "crypto_native"}


def test_unknown_persona_raises() -> None:
    with pytest.raises(ValueError, match="unknown persona"):
        load_persona("day_trader")


@pytest.mark.parametrize("persona_name", ["macro", "equity_pm", "options_trader", "crypto_native"])
async def test_persona_events_all_target_real_taxonomy_nodes(persona_name: str) -> None:
    persona = load_persona(persona_name)
    for event in persona.events:
        assert TAXONOMY.node(event.node_id) is not None, f"{persona_name}: {event.node_id}"


async def test_replay_macro_persona_makes_yield_curve_dominate(
    db_conn: asyncpg.pool.PoolConnectionProxy,
) -> None:
    persona = load_persona("macro")
    profile_id = uuid.uuid4()
    await replay_persona(db_conn, TAXONOMY, profile_id, persona)

    vector = await get_scores(db_conn, profile_id)
    layout = compute_layout(vector)
    by_type = {b.block_type: b for b in layout.blocks}
    assert by_type["yield_curve"].priority == 1
    assert by_type["yield_curve"].columns > by_type["quotes"].columns
    assert by_type["yield_curve"].columns > by_type["heatmap"].columns


async def test_replay_equity_pm_persona_favors_heatmap_and_quotes_over_curve(
    db_conn: asyncpg.pool.PoolConnectionProxy,
) -> None:
    persona = load_persona("equity_pm")
    profile_id = uuid.uuid4()
    await replay_persona(db_conn, TAXONOMY, profile_id, persona)

    vector = await get_scores(db_conn, profile_id)
    layout = compute_layout(vector)
    by_type = {b.block_type: b for b in layout.blocks}
    assert by_type["yield_curve"].priority == 3
    assert by_type["heatmap"].columns > by_type["yield_curve"].columns
    assert by_type["quotes"].columns > by_type["yield_curve"].columns


async def test_replay_sets_profile_persona_field(
    db_conn: asyncpg.pool.PoolConnectionProxy,
) -> None:
    persona = load_persona("crypto_native")
    profile_id = uuid.uuid4()
    await replay_persona(db_conn, TAXONOMY, profile_id, persona)
    stored = await db_conn.fetchval("SELECT persona FROM profiles WHERE id = $1", profile_id)
    assert stored == "crypto_native"
