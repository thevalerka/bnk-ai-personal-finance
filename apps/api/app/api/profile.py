import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from app.attention import identity, service
from app.attention.decay import EventKind
from app.attention.layout import LayoutPlan
from app.attention.personas import list_personas, load_persona, replay_persona
from app.attention.service import ExplainResult
from app.attention.taxonomy import load_taxonomy
from app.config import get_settings

router = APIRouter(prefix="/profile", tags=["profile"])

# Loaded once at import time, same as app/market/config_loader.py's chains —
# it's a static YAML file, not something that changes per request.
_TAXONOMY = load_taxonomy()


def set_profile_cookie(response: Response, profile_id: uuid.UUID) -> None:
    settings = get_settings()
    response.set_cookie(
        identity.COOKIE_NAME,
        identity.sign(profile_id, settings.secret_key),
        httponly=True,
        samesite="lax",
        secure=settings.env != "development",
        max_age=identity.COOKIE_MAX_AGE,
    )


async def resolve_profile(request: Request, response: Response) -> uuid.UUID:
    """Read the signed profile_id cookie, or mint and persist a new one on
    first visit (docs/PLAN.md section 4.1). Public — also used by
    app.api.agent, which needs the same identity to attribute set_focus/
    add_block tool calls to the visitor's real interest vector."""
    settings = get_settings()
    raw_cookie = request.cookies.get(identity.COOKIE_NAME)
    profile_id = identity.verify(raw_cookie, settings.secret_key) if raw_cookie else None
    is_new = profile_id is None
    if profile_id is None:
        profile_id = uuid.uuid4()

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        await service.ensure_profile(conn, profile_id)

    if is_new:
        set_profile_cookie(response, profile_id)
    return profile_id


class EventIn(BaseModel):
    node_id: str
    kind: EventKind
    magnitude: float = 1.0
    meta: dict[str, Any] | None = None


class EventsIn(BaseModel):
    events: list[EventIn]


@router.post("/events", status_code=204)
async def post_events(request: Request, response: Response, body: EventsIn) -> None:
    profile_id = await resolve_profile(request, response)
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        for event in body.events:
            try:
                await service.record_event(
                    conn,
                    _TAXONOMY,
                    profile_id,
                    event.node_id,
                    event.kind,
                    magnitude=event.magnitude,
                    meta=event.meta,
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/vector")
async def get_vector(request: Request, response: Response) -> dict[str, float]:
    profile_id = await resolve_profile(request, response)
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        return await service.get_scores(conn, profile_id)


@router.get("/layout")
async def get_layout(request: Request, response: Response) -> LayoutPlan:
    profile_id = await resolve_profile(request, response)
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        return await service.get_layout(conn, profile_id)


_VALID_DAG_IDS = (
    set(_TAXONOMY.asset_class_ids()) | set(_TAXONOMY.bucket_ids()) | set(_TAXONOMY.node_ids())
)


@router.get("/explain")
async def get_explain(request: Request, response: Response, node_id: str) -> ExplainResult:
    if node_id not in _VALID_DAG_IDS:
        raise HTTPException(status_code=404, detail=f"unknown taxonomy node: {node_id}")
    profile_id = await resolve_profile(request, response)
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        return await service.explain(conn, profile_id, node_id)


class PersonaOut(BaseModel):
    name: str
    label: str
    description: str


class ProfileOut(BaseModel):
    profile_id: uuid.UUID
    persona: str | None
    layout: LayoutPlan


@router.get("/me")
async def get_me(request: Request, response: Response) -> ProfileOut:
    profile_id = await resolve_profile(request, response)
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        persona = await conn.fetchval("SELECT persona FROM profiles WHERE id = $1", profile_id)
        layout = await service.get_layout(conn, profile_id)
    return ProfileOut(profile_id=profile_id, persona=persona, layout=layout)


@router.get("/personas")
async def get_personas() -> list[PersonaOut]:
    return [
        PersonaOut(name=p.name, label=p.label, description=p.description) for p in list_personas()
    ]


@router.post("/persona/{name}")
async def post_persona(request: Request, response: Response, name: str) -> ProfileOut:
    """ "View as" (docs/PLAN.md section 1): always starts a fresh profile —
    switching persona replaces whatever profile_id the cookie held rather
    than mixing a seeded persona's history into an existing one."""
    try:
        persona = load_persona(name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    profile_id = uuid.uuid4()
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        await replay_persona(conn, _TAXONOMY, profile_id, persona)
        layout = await service.get_layout(conn, profile_id)

    set_profile_cookie(response, profile_id)
    return ProfileOut(profile_id=profile_id, persona=persona.name, layout=layout)


@router.post("/reset")
async def post_reset(request: Request, response: Response) -> ProfileOut:
    """Back to "View as: Default" — a brand new, organic, empty profile."""
    profile_id = uuid.uuid4()
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        await service.ensure_profile(conn, profile_id)
        layout = await service.get_layout(conn, profile_id)

    set_profile_cookie(response, profile_id)
    return ProfileOut(profile_id=profile_id, persona=None, layout=layout)
