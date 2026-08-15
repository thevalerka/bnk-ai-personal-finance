import uuid

import anthropic
import asyncpg
import httpx
import pytest
from redis.asyncio import Redis

from app.agent.service import MAX_TOOL_TURNS, stream_agent_turn
from app.agent.tools import ToolContext
from app.attention.taxonomy import Taxonomy
from tests.agent.conftest import (
    FakeAsyncAnthropic,
    FakeContentBlockDeltaEvent,
    FakeMessage,
    FakeTextBlock,
    FakeTextDelta,
    FakeToolUseBlock,
    build_gateway,
)


def make_ctx(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> ToolContext:
    gateway = build_gateway(redis, {})
    return ToolContext(gateway=gateway, db_pool=db_pool, taxonomy=taxonomy, profile_id=profile_id)


async def _collect(agen: object) -> list[dict[str, object]]:
    return [event async for event in agen]  # type: ignore[attr-defined]


async def test_simple_turn_streams_text_then_done(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id)
    fake = FakeAsyncAnthropic(
        turns=[
            (
                [
                    FakeContentBlockDeltaEvent(delta=FakeTextDelta(text="SPY is ")),
                    FakeContentBlockDeltaEvent(delta=FakeTextDelta(text="776.34.")),
                ],
                FakeMessage(content=[FakeTextBlock(text="SPY is 776.34.")], stop_reason="end_turn"),
            )
        ]
    )
    messages = [{"role": "user", "content": "what's SPY at?"}]
    events = await _collect(stream_agent_turn(fake, "claude-sonnet-5", ctx, messages))  # type: ignore[arg-type]

    text_events = [e for e in events if e["event"] == "text"]
    assert "".join(e["data"]["text"] for e in text_events) == "SPY is 776.34."
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["stop_reason"] == "end_turn"
    assert events[-1]["data"]["input_tokens"] == 10
    assert events[-1]["data"]["output_tokens"] == 5
    # Assistant turn was appended for the caller to keep as history.
    assert messages[-1]["role"] == "assistant"


async def test_tool_use_turn_executes_the_real_tool_and_continues(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id)
    fake = FakeAsyncAnthropic(
        turns=[
            (
                [],
                FakeMessage(
                    content=[FakeToolUseBlock(name="explain_layout", input={}, id="toolu_abc")],
                    stop_reason="tool_use",
                ),
            ),
            (
                [FakeContentBlockDeltaEvent(delta=FakeTextDelta(text="Here's your layout."))],
                FakeMessage(
                    content=[FakeTextBlock(text="Here's your layout.")], stop_reason="end_turn"
                ),
            ),
        ]
    )
    messages = [{"role": "user", "content": "why am I seeing this?"}]
    events = await _collect(stream_agent_turn(fake, "claude-sonnet-5", ctx, messages))  # type: ignore[arg-type]

    assert [e["event"] for e in events] == ["tool_call", "tool_result", "text", "done"]
    assert events[0]["data"]["name"] == "explain_layout"
    assert events[1]["data"]["is_error"] is False
    assert len(fake.messages.calls) == 2  # tool_use, then the continuation
    # `messages` is mutated in place and shared by reference across both
    # recorded calls, so inspect final state rather than calls[1] — by the
    # end it's [user q, assistant(tool_use), user(tool_result), assistant(text)].
    assert messages[-2]["content"][0]["tool_use_id"] == "toolu_abc"
    assert events[-1]["data"]["input_tokens"] == 20  # 10 + 10 across two turns


async def test_chart_and_mutation_side_effects_emit_their_own_events(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id)
    fake = FakeAsyncAnthropic(
        turns=[
            (
                [],
                FakeMessage(
                    content=[
                        FakeToolUseBlock(
                            name="set_focus", input={"node_id": "crypto.majors.btc"}, id="toolu_1"
                        )
                    ],
                    stop_reason="tool_use",
                ),
            ),
            (
                [],
                FakeMessage(content=[FakeTextBlock(text="Done.")], stop_reason="end_turn"),
            ),
        ]
    )
    messages = [{"role": "user", "content": "I care about crypto"}]
    events = await _collect(stream_agent_turn(fake, "claude-sonnet-5", ctx, messages))  # type: ignore[arg-type]

    assert "mutation" in [e["event"] for e in events]


async def test_refusal_stops_the_loop_without_a_second_call(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id)
    fake = FakeAsyncAnthropic(
        turns=[
            ([], FakeMessage(content=[], stop_reason="refusal")),
        ]
    )
    messages = [{"role": "user", "content": "what should I buy?"}]
    events = await _collect(stream_agent_turn(fake, "claude-sonnet-5", ctx, messages))  # type: ignore[arg-type]

    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["stop_reason"] == "refusal"
    assert len(fake.messages.calls) == 1


async def test_max_tool_turns_is_a_hard_cap(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id)
    infinite_tool_use = (
        [],
        FakeMessage(
            content=[FakeToolUseBlock(name="explain_layout", input={}, id="toolu_x")],
            stop_reason="tool_use",
        ),
    )
    fake = FakeAsyncAnthropic(turns=[infinite_tool_use] * MAX_TOOL_TURNS)
    messages = [{"role": "user", "content": "loop forever"}]
    events = await _collect(stream_agent_turn(fake, "claude-sonnet-5", ctx, messages))  # type: ignore[arg-type]

    assert events[-1]["event"] == "error"
    assert len(fake.messages.calls) == MAX_TOOL_TURNS


async def test_api_status_error_yields_an_error_event(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id)
    response = httpx.Response(500, request=httpx.Request("POST", "https://api.anthropic.com"))
    fake = FakeAsyncAnthropic(
        turns=[anthropic.APIStatusError("boom", response=response, body=None)]
    )
    messages = [{"role": "user", "content": "hello"}]
    events = await _collect(stream_agent_turn(fake, "claude-sonnet-5", ctx, messages))  # type: ignore[arg-type]

    assert events == [{"event": "error", "data": {"message": "Claude API error: boom"}}]


async def test_api_connection_error_yields_an_error_event(
    redis: Redis, db_pool: asyncpg.Pool, taxonomy: Taxonomy, profile_id: uuid.UUID
) -> None:
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id)
    request = httpx.Request("POST", "https://api.anthropic.com")
    fake = FakeAsyncAnthropic(turns=[anthropic.APIConnectionError(request=request)])
    messages = [{"role": "user", "content": "hello"}]
    events = await _collect(stream_agent_turn(fake, "claude-sonnet-5", ctx, messages))  # type: ignore[arg-type]

    assert events[0]["event"] == "error"
    assert "Could not reach" in events[0]["data"]["message"]


@pytest.mark.parametrize("node_id", ["equities.us_large_cap.technology"])
async def test_system_prompt_is_sent_with_a_cache_breakpoint(
    redis: Redis,
    db_pool: asyncpg.Pool,
    taxonomy: Taxonomy,
    profile_id: uuid.UUID,
    node_id: str,
) -> None:
    ctx = make_ctx(redis, db_pool, taxonomy, profile_id)
    fake = FakeAsyncAnthropic(
        turns=[([], FakeMessage(content=[FakeTextBlock(text="ok")], stop_reason="end_turn"))]
    )
    messages = [{"role": "user", "content": "hi"}]
    await _collect(stream_agent_turn(fake, "claude-sonnet-5", ctx, messages))  # type: ignore[arg-type]

    sent_system = fake.messages.calls[0]["system"]
    assert sent_system[0]["cache_control"] == {"type": "ephemeral"}
    # Guardrail rules actually made it into what gets sent, not just the
    # constant module — this is what the DoD's "refusal/guardrail tests"
    # actually check at the code layer (see docs/PLAN.md P4).
    prompt_text = sent_system[0]["text"]
    assert "not investment advice" in prompt_text or "not a financial advisor" in prompt_text
