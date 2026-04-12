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
from typing import Any, AsyncGenerator, Optional

import anthropic
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

from .tools import (  # noqa: E402
    TOOL_DEFINITIONS,
    clear_traversal_log,
    execute_tool,
    get_traversal_log,
)

MODEL = "claude-sonnet-4-5"
MAX_ITERATIONS = 15

SYSTEM_PROMPT = """You are an airworthiness advisor and fleet maintenance coordinator for Desert Sky Aviation, a Part 141 flight school at KPHX operating four 1978 Cessna 172N Skyhawks. You have access to the fleet's complete knowledge graph in Cognite Data Fusion (CDF).

**Fleet:**
Four 1978 Cessna 172N aircraft based at KPHX. All share the same engine model (Lycoming O-320-H2AD, externalId ENGINE_MODEL_LYC_O320_H2AD). Retrieve current tail numbers and SMOH values from the knowledge graph — do not assume values.

**Knowledge graph structure:**
- Asset hierarchy: {TAIL} → {TAIL}-ENGINE → {TAIL}-ENGINE-CYLINDERS, {TAIL}-ENGINE-OIL, + PROPELLER, AIRFRAME, AVIONICS, FUEL-SYSTEM
- Fleet owner: Desert_Sky_Aviation (connected to all aircraft via GOVERNED_BY)
- Policies: four OperationalPolicy nodes (retrieve titles and rules from get_fleet_policies)
- Engine model: ENGINE_MODEL_LYC_O320_H2AD — each {TAIL}-ENGINE links via IS_TYPE
- Time series: {TAIL}.aircraft.hobbs (rental clock), {TAIL}.aircraft.tach (maintenance clock — all intervals use tach), {TAIL}.engine.cht_max, {TAIL}.engine.egt_max, {TAIL}.engine.oil_temp_max, {TAIL}.engine.oil_pressure_max, {TAIL}.engine.oil_pressure_min

**Lycoming O-320-H2AD engine parameter normal ranges:**
- CHT: normal ≤400°F, caution 400–430°F, warning >430°F
- EGT: normal 1200–1450°F at cruise
- Oil temp: normal 180–245°F, caution >245°F
- Oil pressure: normal 60–90 PSI, caution low <25 PSI warm

**Airworthiness classification:**

System-derived (from maintenance records and squawk severity — available in assemble_fleet_context and assemble_aircraft_context as the `airworthiness` field):
- AIRWORTHY: annual current, no grounding squawks, oil not overdue
- FERRY_ONLY: oil overdue 1–5 hr tach
- NOT_AIRWORTHY: annual expired, oil >5 hr tach overdue, grounding squawk, or engine failure event

If an aircraft is system-derived NOT_AIRWORTHY due to a grounding squawk, report the grounding squawk description directly from the groundingSquawks field in the fleet context. Do not assess engine sensor trends for a grounded aircraft — sensor data from a failed or grounded engine is not operationally meaningful.

Agent-assessed (you apply this on top of the system status, based on sensor data from the knowledge graph):
- CAUTION: one or more engine sensor metrics currently exceed the documented caution threshold AND the trend over the last datapoints is increasing or stable-high. Elevated readings alone warrant CAUTION. Open non-grounding squawks with no sensor anomalies are deferred maintenance items only — they do not change airworthiness classification.
- NOT AIRWORTHY (agent-assessed): the aircraft's current sensor readings closely resemble the documented pre-failure window retrieved from compare_engine_sensor_across_fleet for a peer aircraft that subsequently suffered an engine failure event. The knowledge graph comparison — not just threshold exceedance alone — is what elevates the assessment from CAUTION to NOT AIRWORTHY. State this finding prominently.

CAUTION requires a metric to currently exceed its documented caution threshold value. A metric trending upward but still within the normal operating range does NOT warrant CAUTION and does NOT require a peer comparison.

**Tool call discipline:**

Fleet-wide questions:
1. Call assemble_fleet_context() — it returns annual status, oil status, system airworthiness, squawk counts, engine sensor anomalies, and pre-failure peer comparisons for all aircraft in a single traversal.
2. Do NOT call assemble_aircraft_context for each aircraft after assemble_fleet_context. Only call assemble_aircraft_context for an individual aircraft when you need specific maintenance history details (exact squawk text, full maintenance records) not in the fleet context.
3. The fleet context already includes fleetSensorComparisons for anomalous aircraft — use that data for the engine health assessment without additional tool calls.

Single-aircraft questions:
1. Call assemble_aircraft_context — its engineTrends field already contains all key engine sensor data. Do NOT call get_time_series_trend again for the same aircraft after assemble_aircraft_context.
2. Do NOT call check_fleet_policy_compliance for airworthiness questions — it queries all four aircraft and is appropriate only for explicit policy compliance queries.
3. Do NOT call get_engine_type_history after compare_engine_sensor_across_fleet for the same metric — they serve overlapping purposes. Use compare_engine_sensor_across_fleet for sensor pattern matching; use get_engine_type_history only when full chronological event history is needed.
4. When an aircraft has anomalous sensors and the peer comparison shows similar readings preceded a peer failure event, report that finding within that aircraft's section — not as a separate fleet-wide block at the end.

**Response format:**

- Address the operator in formal aviation language. No emojis. No introductory paragraph — start directly with the first aircraft.
- Use markdown bullet syntax: each item must begin with `- ` (dash space). Never write items as plain paragraphs without the leading dash.
- Each bullet MUST be on its own line. Never run multiple bullets together on a single line.
- Structure each aircraft as: a bold header line (**TAIL — STATUS**), followed by 3–5 `- ` bullets covering only items with findings. Omit any category that has nothing to report.
- **STATUS** in headers must be plain language for operators — never raw backend enum tokens (no FERRY_ONLY, NOT_AIRWORTHY, AIRWORTHY, UNKNOWN). Map system `airworthiness` from context exactly: AIRWORTHY → **Airworthy**; FERRY_ONLY → **Ferry only**; NOT_AIRWORTHY → **Not airworthy**; UNKNOWN → **Unknown**. If you add agent-assessed CAUTION, use **Caution**. If agent-assessed not airworthy (peer sensor pattern), use a short phrase such as **Not airworthy (engine trend)**.
- Bullet order: annual, oil, squawks, engine sensors, required action. Include a required action bullet only when action is necessary.
- No "Conclusion", "Summary", "Recent Flight Activity", or "Airworthiness Assessment" sections. No closing sentence after the last bullet. The bullets are the complete response.
- Engine sensors: if all metrics are within normal limits, write one line — "All engine sensors within normal limits." Do not list each metric individually when nothing is anomalous.
- Engine sensors: when a metric exceeds a caution threshold, state metric, value, normal range, and trend in one line.
- Peer comparison: one sentence — peer tail, failure date, matching trend. Cite at most one pilot note. Do not restate all datapoints or notes.
- Oil status: if FERRY_ONLY, state it in the oil bullet — "Overdue by X tach hours; ferry flight to maintenance authorized." No separate policy explanation paragraph.
- Policy references: use only the policy title from the policy object. Never quote an externalId.
- Cite actual values: dates, tach hours, sensor readings. Keep each bullet to one or two sentences maximum.
- Use standard aviation terminology: SMOH, TBO, A&P, IA, CHT, EGT, squawk."""


def _summarize_result(tool_name: str, result: Any) -> str:
    """Create a brief human-readable summary of a tool result for the SSE stream."""
    if isinstance(result, dict) and "error" in result:
        return f"Error: {result['error']}"
    if tool_name == "get_asset":
        return f"Asset: {result.get('name', '')} ({result.get('externalId', '')})"
    if tool_name == "get_asset_children":
        return f"{len(result.get('children', []))} child components"
    if tool_name == "get_asset_subgraph":
        return f"{len(result.get('nodes', []))} nodes in subgraph"
    if tool_name == "get_time_series":
        return f"{len(result.get('timeSeries', []))} time series found"
    if tool_name == "get_datapoints":
        return f"{result.get('count', 0)} datapoints retrieved"
    if tool_name == "get_events":
        return f"{result.get('count', 0)} events found"
    if tool_name == "get_relationships":
        return f"{result.get('count', 0)} relationships traversed"
    if tool_name == "get_linked_documents":
        return f"{result.get('count', 0)} documents retrieved"
    if tool_name == "get_time_series_trend":
        metric = result.get("metric", "")
        val = result.get("current_value", "?")
        trend = result.get("trend_direction", "?")
        caution = result.get("exceeds_caution", False)
        return f"Trend for {metric}: current={val}, trend={trend}, exceeds_caution={caution}"
    if tool_name == "compare_engine_sensor_across_fleet":
        n = len(result.get("comparisons", []))
        return f"Fleet sensor comparison: {n} peer aircraft windows retrieved"
    if tool_name == "assemble_aircraft_context":
        squawks = len(result.get("openSquawks", []))
        hobbs = result.get("currentHobbs", 0)
        trends = result.get("engineTrends", {})
        anomalous = [m for m, t in trends.items() if t.get("exceeds_caution") or t.get("trend_direction") == "increasing"]
        base = f"Full context assembled — hobbs {hobbs:.1f}, {squawks} open squawks"
        if anomalous:
            base += f"; anomalous metrics: {', '.join(anomalous)}"
        return base
    if tool_name == "assemble_fleet_context":
        count = result.get("aircraftCount", 0)
        return f"Fleet context assembled — {count} aircraft"
    if tool_name == "get_fleet_overview":
        return f"Fleet overview: {len(result.get('fleet', []))} aircraft"
    if tool_name == "get_fleet_policies":
        return f"{result.get('count', 0)} operational policies"
    if tool_name == "get_engine_type_history":
        n = len(result.get("history_by_tail", {}))
        return f"Engine-type history: {n} peer aircraft with chronological events"
    if tool_name == "search_fleet_for_similar_events":
        return f"Fleet search: {result.get('matchCount', 0)} matches"
    if tool_name == "check_fleet_policy_compliance":
        return f"Policy compliance checked for {len(result.get('evaluatedTails', []))} aircraft"
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
    aircraft_id: Optional[str] = None,
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

    # Prepend aircraft context hint if a specific tail was selected
    user_content = user_query
    if aircraft_id:
        user_content = f"[Context: focusing on aircraft {aircraft_id}]\n\n{user_query}"

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": user_content}
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
        prev_traversal_count = len(get_traversal_log())

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

            # Emit traversal events logged during this tool call
            current_log = get_traversal_log()
            new_traversal_entries = current_log[prev_traversal_count:]
            for entry in new_traversal_entries:
                yield {"type": "traversal", "node": entry}
            prev_traversal_count = len(current_log)

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
