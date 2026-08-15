import uuid

import asyncpg


async def test_schema_applied_and_profile_roundtrips(
    db_conn: asyncpg.pool.PoolConnectionProxy,
) -> None:
    profile_id = uuid.uuid4()
    await db_conn.execute("INSERT INTO profiles (id) VALUES ($1)", profile_id)
    row = await db_conn.fetchrow("SELECT id, persona FROM profiles WHERE id = $1", profile_id)
    assert row is not None
    assert row["id"] == profile_id
    assert row["persona"] is None


async def test_interest_score_upsert(db_conn: asyncpg.pool.PoolConnectionProxy) -> None:
    profile_id = uuid.uuid4()
    await db_conn.execute("INSERT INTO profiles (id) VALUES ($1)", profile_id)
    await db_conn.execute(
        "INSERT INTO interest_scores (profile_id, node_id, score) VALUES ($1, $2, $3)",
        profile_id,
        "equities.us_large_cap.technology",
        2.0,
    )
    score = await db_conn.fetchval(
        "SELECT score FROM interest_scores WHERE profile_id = $1 AND node_id = $2",
        profile_id,
        "equities.us_large_cap.technology",
    )
    assert score == 2.0


async def test_event_cascade_delete_with_profile(db_conn: asyncpg.pool.PoolConnectionProxy) -> None:
    profile_id = uuid.uuid4()
    await db_conn.execute("INSERT INTO profiles (id) VALUES ($1)", profile_id)
    await db_conn.execute(
        "INSERT INTO events (profile_id, node_id, kind, weight) VALUES ($1, $2, $3, $4)",
        profile_id,
        "equities.us_large_cap.technology",
        "click",
        2.0,
    )
    await db_conn.execute("DELETE FROM profiles WHERE id = $1", profile_id)
    count = await db_conn.fetchval("SELECT count(*) FROM events WHERE profile_id = $1", profile_id)
    assert count == 0
