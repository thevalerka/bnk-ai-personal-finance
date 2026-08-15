"""Seeded interest vectors for the "View as" switcher (docs/PLAN.md section
1 + 4.4) and `scripts/simulate_user.py`. A persona is a scripted event
sequence — replayed through the real record_event()/decay pipeline, oldest
first — not a hand-tuned final score, so "seeded" personas exercise exactly
the same code path a real user's history does.
"""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml
from pydantic import BaseModel

from app.attention import service
from app.attention.decay import EventKind
from app.attention.service import DbConn
from app.attention.taxonomy import Taxonomy

CONFIG_DIR = Path(__file__).resolve().parents[4] / "config" / "personas"


class PersonaEvent(BaseModel):
    node_id: str
    kind: EventKind
    days_ago: float


class Persona(BaseModel):
    name: str
    label: str
    description: str
    events: list[PersonaEvent]


def load_persona(name: str) -> Persona:
    path = CONFIG_DIR / f"{name}.yaml"
    if not path.exists():
        raise ValueError(f"unknown persona: {name}")
    with path.open() as f:
        return Persona.model_validate(yaml.safe_load(f))


def list_personas() -> list[Persona]:
    return [load_persona(path.stem) for path in sorted(CONFIG_DIR.glob("*.yaml"))]


async def replay_persona(
    conn: DbConn,
    taxonomy: Taxonomy,
    profile_id: uuid.UUID,
    persona: Persona,
    now: datetime | None = None,
) -> None:
    now = now or datetime.now(UTC)
    await service.ensure_profile(conn, profile_id, persona=persona.name)
    for event in persona.events:
        await service.record_event(
            conn,
            taxonomy,
            profile_id,
            event.node_id,
            event.kind,
            now=now - timedelta(days=event.days_ago),
        )
