"""Business logic behind the /profile endpoints (app/api/profile.py) — kept
out of the router so it's independently testable against a real transactional
Postgres connection (tests/attention/) without spinning up FastAPI.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import asyncpg
from pydantic import BaseModel

from app.attention.decay import (
    EVENT_WEIGHTS,
    MUTE_CEILING,
    EventKind,
    apply_event,
    decayed_score,
    propagate,
)
from app.attention.layout import BLOCK_NODES, LayoutPlan, compute_layout
from app.attention.taxonomy import Taxonomy

DbConn = asyncpg.pool.PoolConnectionProxy | asyncpg.Connection


async def ensure_profile(conn: DbConn, profile_id: uuid.UUID, persona: str | None = None) -> None:
    await conn.execute(
        "INSERT INTO profiles (id, persona) VALUES ($1, $2) ON CONFLICT (id) DO NOTHING",
        profile_id,
        persona,
    )


async def record_event(
    conn: DbConn,
    taxonomy: Taxonomy,
    profile_id: uuid.UUID,
    node_id: str,
    kind: EventKind,
    magnitude: float = 1.0,
    meta: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> None:
    """Log the raw event (source-of-truth for the explain panel) and apply
    its decayed-score contribution to the node and its DAG ancestors."""
    if taxonomy.node(node_id) is None:
        raise ValueError(f"unknown taxonomy node: {node_id}")
    now = now or datetime.now(UTC)
    weight = EVENT_WEIGHTS[kind] * magnitude

    await conn.execute(
        "INSERT INTO events (profile_id, node_id, kind, weight, ts, meta) "
        "VALUES ($1, $2, $3, $4, $5, $6)",
        profile_id,
        node_id,
        kind.value,
        weight,
        now,
        json.dumps(meta) if meta else None,
    )

    for dotted_id, contribution in propagate(taxonomy, node_id, weight).items():
        is_target = dotted_id == node_id
        await _upsert_score(
            conn,
            profile_id,
            dotted_id,
            contribution,
            now,
            mute=kind is EventKind.MUTE and is_target,
            unmute=kind is EventKind.PIN and is_target,
        )


async def _upsert_score(
    conn: DbConn,
    profile_id: uuid.UUID,
    node_id: str,
    contribution: float,
    now: datetime,
    mute: bool,
    unmute: bool,
) -> None:
    row = await conn.fetchrow(
        "SELECT score, last_updated, muted FROM interest_scores "
        "WHERE profile_id = $1 AND node_id = $2",
        profile_id,
        node_id,
    )
    if row is None:
        new_score = contribution
        muted = mute
    else:
        new_score = apply_event(row["score"], now - row["last_updated"], contribution)
        muted = mute or (row["muted"] and not unmute)

    if muted:
        new_score = min(new_score, MUTE_CEILING)

    await conn.execute(
        """
        INSERT INTO interest_scores (profile_id, node_id, score, last_updated, muted)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (profile_id, node_id)
        DO UPDATE SET score = $3, last_updated = $4, muted = $5
        """,
        profile_id,
        node_id,
        new_score,
        now,
        muted,
    )


async def get_scores(
    conn: DbConn,
    profile_id: uuid.UUID,
    node_ids: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, float]:
    """Every stored (or a specific subset of) DAG node scores, decayed to
    `now` — the decay-on-read half of decay.py's incremental-update trick."""
    now = now or datetime.now(UTC)
    if node_ids is None:
        rows = await conn.fetch(
            "SELECT node_id, score, last_updated FROM interest_scores WHERE profile_id = $1",
            profile_id,
        )
    else:
        rows = await conn.fetch(
            "SELECT node_id, score, last_updated FROM interest_scores "
            "WHERE profile_id = $1 AND node_id = ANY($2::text[])",
            profile_id,
            node_ids,
        )
    return {row["node_id"]: decayed_score(row["score"], now - row["last_updated"]) for row in rows}


async def get_layout(
    conn: DbConn, profile_id: uuid.UUID, now: datetime | None = None
) -> LayoutPlan:
    relevant_nodes = [node_id for nodes in BLOCK_NODES.values() for node_id in nodes]
    scores = await get_scores(conn, profile_id, relevant_nodes, now)
    return compute_layout(scores)


class SourceEvent(BaseModel):
    kind: str
    weight: float
    ts: datetime
    node_id: str
    meta: dict[str, Any] | None = None


class ExplainResult(BaseModel):
    node_id: str
    score: float
    last_updated: datetime | None
    muted: bool
    source_events: list[SourceEvent]


async def explain(
    conn: DbConn,
    profile_id: uuid.UUID,
    node_id: str,
    now: datetime | None = None,
    limit: int = 20,
) -> ExplainResult:
    now = now or datetime.now(UTC)
    score_row = await conn.fetchrow(
        "SELECT score, last_updated, muted FROM interest_scores "
        "WHERE profile_id = $1 AND node_id = $2",
        profile_id,
        node_id,
    )
    score = decayed_score(score_row["score"], now - score_row["last_updated"]) if score_row else 0.0
    last_updated = score_row["last_updated"] if score_row else None
    muted = bool(score_row["muted"]) if score_row else False

    # A leaf node (3 dotted parts) only ever receives events targeting it
    # exactly; a bucket/asset_class (1-2 parts) is the sum of every
    # descendant leaf's events, so match it as a prefix.
    is_leaf = len(node_id.split(".")) == 3
    if is_leaf:
        event_rows = await conn.fetch(
            "SELECT kind, weight, ts, node_id, meta FROM events "
            "WHERE profile_id = $1 AND node_id = $2 ORDER BY ts DESC LIMIT $3",
            profile_id,
            node_id,
            limit,
        )
    else:
        event_rows = await conn.fetch(
            "SELECT kind, weight, ts, node_id, meta FROM events "
            "WHERE profile_id = $1 AND (node_id = $2 OR node_id LIKE $3) "
            "ORDER BY ts DESC LIMIT $4",
            profile_id,
            node_id,
            f"{node_id}.%",
            limit,
        )

    return ExplainResult(
        node_id=node_id,
        score=score,
        last_updated=last_updated,
        muted=muted,
        source_events=[
            SourceEvent(
                kind=row["kind"],
                weight=row["weight"],
                ts=row["ts"],
                node_id=row["node_id"],
                meta=json.loads(row["meta"]) if row["meta"] else None,
            )
            for row in event_rows
        ],
    )
