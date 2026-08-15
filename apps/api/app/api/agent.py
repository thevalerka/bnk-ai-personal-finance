"""POST /agent/stream — the prompt bar's backend (docs/PLAN.md section 5.1).
SSE, not the raw Anthropic stream shape: text/tool_call/tool_result/chart/
mutation/done/error events the frontend renders directly.
"""

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any, Literal

import anthropic
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from app.agent.budget import AgentBudget
from app.agent.service import stream_agent_turn
from app.agent.tools import ToolContext
from app.api.profile import resolve_profile
from app.attention.taxonomy import load_taxonomy
from app.config import get_settings

router = APIRouter(prefix="/agent", tags=["agent"])

_TAXONOMY = load_taxonomy()
_MAX_MESSAGE_CHARS = 2000
_MAX_HISTORY_MESSAGES = 20


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class StreamIn(BaseModel):
    message: str
    # Prior turns as plain display text only — the tool_use/tool_result
    # scaffolding a turn's own answer was built from doesn't need replaying
    # into later turns' context, only its resulting text does. The Messages
    # API is stateless either way; this is what the client resends.
    history: list[HistoryMessage] = []


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


async def _event_stream(
    request: Request, body: StreamIn, profile_id: uuid.UUID
) -> AsyncIterator[str]:
    settings = get_settings()
    agent_budget: AgentBudget = request.app.state.agent_budget
    if not await agent_budget.try_consume_request(str(profile_id)):
        yield _sse("error", {"message": "Rate limit exceeded — wait a minute and try again."})
        return
    if not await agent_budget.has_budget():
        yield _sse(
            "error", {"message": "Monthly token budget exhausted — agent is unavailable for now."}
        )
        return

    client: anthropic.AsyncAnthropic = request.app.state.anthropic_client
    ctx = ToolContext(
        gateway=request.app.state.market_gateway,
        db_pool=request.app.state.db_pool,
        taxonomy=_TAXONOMY,
        profile_id=profile_id,
    )
    messages: list[dict[str, Any]] = [
        {"role": h.role, "content": h.content} for h in body.history[-_MAX_HISTORY_MESSAGES:]
    ] + [{"role": "user", "content": body.message}]

    async for event in stream_agent_turn(client, settings.agent_model, ctx, messages):
        if event["event"] == "done":
            await agent_budget.record_spend(
                event["data"].get("input_tokens", 0), event["data"].get("output_tokens", 0)
            )
        yield _sse(event["event"], event["data"])


@router.post("/stream")
async def post_stream(request: Request, body: StreamIn) -> StreamingResponse:
    if not body.message.strip():
        raise HTTPException(status_code=422, detail="message must not be empty")
    if len(body.message) > _MAX_MESSAGE_CHARS:
        raise HTTPException(status_code=422, detail="message too long")
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=503, detail="agent is not configured (no API key)")

    # Placeholder iterator, immediately replaced below once `response`
    # exists — the body_iterator itself needs the response object (see
    # _event_stream), same reasoning that forces resolve_profile to run
    # here rather than inside the generator (next comment).
    response = StreamingResponse(
        iter(()),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
    # Must happen here, before the response is returned — not inside
    # _event_stream. StreamingResponse sends its headers (including any
    # Set-Cookie from resolve_profile) to the client before it starts
    # consuming body_iterator, so a set_cookie call made from inside the
    # generator arrives too late to ever reach the client.
    profile_id = await resolve_profile(request, response)
    response.body_iterator = _event_stream(request, body, profile_id)
    return response
