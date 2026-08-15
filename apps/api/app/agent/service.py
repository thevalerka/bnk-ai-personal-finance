"""The tool-use loop against the Anthropic Messages API (docs/PLAN.md
section 5.1). A manual loop rather than the SDK's tool_runner: this needs
its own SSE event contract to the browser (text/tool_call/tool_result/
chart/mutation/done — not Anthropic's raw stream shape) and side effects
(chart specs, dashboard mutation flags) the runner has nowhere to carry.
"""

import json
from collections.abc import AsyncIterator
from typing import Any

import anthropic

from app.agent.system_prompt import SYSTEM_PROMPT
from app.agent.tools import TOOLS, ToolContext, execute_tool

# Caps how many times the loop can go back to Claude after a batch of tool
# results within one user turn — a runaway tool-call loop degrades to a
# clear error instead of an unbounded number of vendor calls (same
# discipline as the BudgetManager's "refuse rather than call unbounded").
MAX_TOOL_TURNS = 6

MAX_TOKENS = 2048


async def stream_agent_turn(
    client: anthropic.AsyncAnthropic,
    model: str,
    ctx: ToolContext,
    messages: list[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    """Runs the tool-use loop for one user turn. `messages` already has the
    new user turn appended and is mutated in place with every assistant/
    tool_result turn — the caller keeps it as the conversation's history
    for the next turn (the Messages API is stateless).

    Yields SSE-ready {"event": ..., "data": ...} dicts:
    text / tool_call / tool_result / chart / mutation / done / error.
    """
    total_input_tokens = 0
    total_output_tokens = 0

    for _turn in range(1, MAX_TOOL_TURNS + 1):
        try:
            async with client.messages.stream(
                model=model,
                max_tokens=MAX_TOKENS,
                system=[
                    {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
                ],
                tools=TOOLS,  # type: ignore[arg-type]  # plain dicts, matches Anthropic's own docs
                messages=messages,  # type: ignore[arg-type]
            ) as stream:
                async for event in stream:
                    if event.type == "content_block_delta" and event.delta.type == "text_delta":
                        yield {"event": "text", "data": {"text": event.delta.text}}
                response = await stream.get_final_message()
        except anthropic.APIStatusError as exc:
            yield {"event": "error", "data": {"message": f"Claude API error: {exc.message}"}}
            return
        except anthropic.APIConnectionError:
            yield {"event": "error", "data": {"message": "Could not reach the Claude API."}}
            return

        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "refusal":
            yield {
                "event": "done",
                "data": {
                    "stop_reason": "refusal",
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                },
            }
            return

        if response.stop_reason != "tool_use":
            yield {
                "event": "done",
                "data": {
                    "stop_reason": response.stop_reason,
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                },
            }
            return

        tool_results: list[dict[str, Any]] = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            yield {"event": "tool_call", "data": {"name": block.name, "input": block.input}}
            outcome = await execute_tool(block.name, block.input, ctx)
            yield {
                "event": "tool_result",
                "data": {
                    "name": block.name,
                    "result": outcome.result,
                    "is_error": outcome.is_error,
                },
            }
            if outcome.chart is not None:
                yield {"event": "chart", "data": outcome.chart}
            if outcome.mutated:
                yield {"event": "mutation", "data": {}}
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(outcome.result, default=str),
                    "is_error": outcome.is_error,
                }
            )
        messages.append({"role": "user", "content": tool_results})

    yield {
        "event": "error",
        "data": {
            "message": f"stopped after {MAX_TOOL_TURNS} tool-use turns without a final answer"
        },
    }
