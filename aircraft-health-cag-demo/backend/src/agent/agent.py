"""
Claude ReAct Agent — Python equivalent of src/agent/agent.ts.

Implements the Reason-Act loop as an async generator, yielding structured
SSE events as the agent works. Each yield maps to one Server-Sent Event
that the frontend renders in the Graph Traversal Panel.

Event types yielded:
  - "thinking"    : Claude's reasoning text before tool calls
  - "tool_call"   : Agent is about to call a CDF graph tool
  - "tool_result" : Tool returned a result (summarized)
  - "traversal"   : A graph node was visited (from traversal_log)
  - "final"       : Final answer text (markdown)
  - "error"       : Something went wrong
  - "done"        : Stream complete
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any, AsyncGenerator

import anthropic
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

from .tools import (  # noqa: E402
    TOOL_DEFINITIONS,
    clear_traversal_log,
    execute_tool,
    traversal_log,
)

MODEL = "claude-sonnet-4-5"
MAX_ITERATIONS = 12

SYSTEM_PROMPT = """You are an expert aviation mechanic and airworthiness advisor for N4798E, a 1978 Cessna 172N Skyhawk powered by a Lycoming O-320-H2AD engine. You have access to the aircraft's complete knowledge graph stored in Cognite Data Fusion (CDF), which includes:

- **Asset hierarchy**: N4798E → ENGINE-1 → ENGINE-1-CAM-LIFTERS, ENGINE-1-MAGS, etc.
- **Time series (OT)**: Real sensor readings — hobbs time, CHT, EGT, oil pressure, tach
- **Events (IT)**: Full maintenance history since 1978, squawks, annual inspections
- **Documents (ET)**: POH sections, applicable ADs (80-04-03 R2, 2001-23-03, 2011-10-09, 90-06-03 R1), Lycoming SB 480F

**Domain context:**
- The O-320-H2AD has a known cam/lifter spalling issue — this is the H2AD's defining characteristic. Barrel-shaped hydraulic lifters were used instead of mushroom-type; they caused premature wear under higher loads. AD 80-04-03 R2 mandates recurring inspection intervals.
- Engine TBO is 2000 hours. Current SMOH: ~1450 hours (72.5% of TBO).
- Annual inspection required every 12 calendar months per 14 CFR 91.409.
- Oil change interval: 50 hours per Lycoming SB 480F.
- Based at KPHX (Phoenix Sky Harbor International Airport), Arizona.

**CAG approach:** Always traverse the knowledge graph to answer questions. Use specific tools to retrieve connected context — don't guess from memory. After each tool call, reason about what you learned and whether you need more context.

**Response format:**
- Be specific and technical — cite actual values from the graph (hobbs times, dates, AD numbers)
- Reference the graph nodes that informed each part of your answer
- For airworthiness questions, explicitly state whether each relevant criterion is met
- Use aviation standard terminology (SMOH, TBO, TT, A&P/IA, etc.)
"""


def _summarize_result(tool_name: str, result: Any) -> str:
    """Create a brief human-readable summary of a tool result for the SSE stream."""
    if isinstance(result, dict) and "error" in result:
        return f"Error: {result['error']}"
    if tool_name == "get_asset":
        return f"Asset: {result.get('name', '')} ({result.get('externalId', '')})"
    if tool_name == "get_asset_children":
        count = len(result.get("children", []))
        return f"{count} child components"
    if tool_name == "get_asset_subgraph":
        count = len(result.get("nodes", []))
        return f"{count} nodes in subgraph"
    if tool_name == "get_time_series":
        count = len(result.get("timeSeries", []))
        return f"{count} time series found"
    if tool_name == "get_datapoints":
        count = result.get("count", 0)
        return f"{count} datapoints retrieved"
    if tool_name == "get_events":
        count = result.get("count", 0)
        return f"{count} events found"
    if tool_name == "get_relationships":
        count = result.get("count", 0)
        return f"{count} relationships traversed"
    if tool_name == "get_linked_documents":
        count = result.get("count", 0)
        return f"{count} documents retrieved"
    if tool_name == "assemble_aircraft_context":
        squawks = len(result.get("openSquawks", []))
        hobbs = result.get("currentHobbs", 0)
        return f"Full context assembled — hobbs {hobbs:.1f}, {squawks} open squawks"
    return "Result retrieved"


def _extract_text_blocks(content: list[Any]) -> str:
    """Extract all text from a Claude message content list."""
    parts = []
    for block in content:
        if hasattr(block, "type") and block.type == "text":
            parts.append(block.text)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(parts)


async def run_agent_streaming(
    user_query: str,
    max_iterations: int = MAX_ITERATIONS,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    ReAct agent loop as an async generator.

    Each iteration:
      1. Call Claude with current message history and tool definitions
      2. If stop_reason == "end_turn": yield final answer and return
      3. If stop_reason == "tool_use": yield tool_call events, execute tools,
         yield tool_result events, append results to message history
      4. Emit traversal log entries as "traversal" events after each tool batch

    Each yielded dict becomes one JSON-encoded SSE data field.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("sk-ant-..."):
        yield {"type": "error", "message": "ANTHROPIC_API_KEY not configured"}
        yield {"type": "done"}
        return

    anthropic_client = anthropic.Anthropic(api_key=api_key)
    clear_traversal_log()

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": user_query}
    ]

    for iteration in range(max_iterations):
        try:
            response = await asyncio.to_thread(
                anthropic_client.messages.create,
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOL_DEFINITIONS,
                messages=messages,
            )
        except anthropic.AuthenticationError:
            yield {"type": "error", "message": "Invalid ANTHROPIC_API_KEY — check your .env file"}
            yield {"type": "done"}
            return
        except Exception as e:
            yield {"type": "error", "message": f"Claude API error: {str(e)}"}
            yield {"type": "done"}
            return

        # Emit any thinking/text blocks before tool calls
        thinking_text = _extract_text_blocks(response.content)
        if thinking_text.strip():
            yield {"type": "thinking", "content": thinking_text}

        if response.stop_reason == "end_turn":
            final_text = _extract_text_blocks(response.content)
            yield {"type": "final", "content": final_text}
            yield {"type": "done"}
            return

        if response.stop_reason != "tool_use":
            # Unexpected stop reason — treat as final
            yield {"type": "final", "content": _extract_text_blocks(response.content)}
            yield {"type": "done"}
            return

        # Process tool calls
        tool_results: list[dict[str, Any]] = []
        prev_traversal_count = len(traversal_log)

        for block in response.content:
            if not (hasattr(block, "type") and block.type == "tool_use"):
                continue

            tool_name: str = block.name
            tool_input: dict[str, Any] = block.input
            tool_use_id: str = block.id

            yield {
                "type": "tool_call",
                "tool_name": tool_name,
                "args": tool_input,
                "iteration": iteration + 1,
            }

            result = await asyncio.to_thread(execute_tool, tool_name, tool_input)

            # Emit traversal events that were logged during this tool call
            new_traversal_entries = traversal_log[prev_traversal_count:]
            for entry in new_traversal_entries:
                yield {"type": "traversal", "node": entry}
            prev_traversal_count = len(traversal_log)

            summary = _summarize_result(tool_name, result)
            yield {
                "type": "tool_result",
                "tool_name": tool_name,
                "summary": summary,
                "iteration": iteration + 1,
            }

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": json.dumps(result, default=str),
            })

        # Append assistant turn + tool results to message history
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    # Max iterations reached
    yield {
        "type": "error",
        "message": f"Max iterations ({max_iterations}) reached without final answer",
    }
    yield {"type": "done"}
