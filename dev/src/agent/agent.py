"""
ReAct Agent — supports Anthropic (claude-sonnet-4-5) and any OpenAI-compatible
local model (e.g. Ollama).  Priority: Anthropic if ANTHROPIC_API_KEY is set,
otherwise the URL in LOCAL_LLM_URL.

Implements the Reason-Act loop as an async generator, yielding structured
SSE events as the agent works. Each yield maps to one Server-Sent Event
that the frontend renders in the Graph Traversal Panel.

Event types yielded:
  - "thinking"    : model reasoning text before tool calls
  - "tool_call"   : agent is about to call a CDF graph tool
  - "tool_result" : tool returned a result (summarized)
  - "traversal"   : a graph node was visited (from traversal_log)
  - "final"       : final answer text (markdown)
  - "error"       : something went wrong
  - "done"        : stream complete
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
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "qwen2.5:14b")
LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "")
MAX_ITERATIONS = 15

SYSTEM_PROMPT = """You are an airworthiness advisor and fleet performance manager for Southwest Airlines, operating a Boeing 737 fleet. You have access to the fleet's complete knowledge graph in Cognite Data Fusion (CDF).

**Fleet:**
Twelve Boeing 737 aircraft (N287WN, N246WN, N231WN–N209WN). N287WN and N246WN are fully instrumented with engine telemetry; the remaining ten have limited data. All instrumented engines are CFM56-7B (externalId ENGINE_MODEL_CFM56_7B, TBO 30,000 EFH). Retrieve current tail numbers and EFH/SMOH values from the knowledge graph — do not assume values.

**Knowledge graph structure:**
- Asset hierarchy (instrumented aircraft): {TAIL} → {TAIL}-ENGINE-1, {TAIL}-ENGINE-2, {TAIL}-APU, {TAIL}-AIRFRAME, {TAIL}-AVIONICS, {TAIL}-LANDING-GEAR, {TAIL}-HYDRAULICS
- Fleet owner: Southwest_Airlines (connected to all 12 aircraft via GOVERNED_BY)
- Policies: six OperationalPolicy nodes (retrieve titles and rules from get_fleet_policies)
- Engine model: ENGINE_MODEL_CFM56_7B — each instrumented {TAIL}-ENGINE-1 links via IS_TYPE
- Time series (instrumented aircraft only): {TAIL}.aircraft.hobbs (AFH), {TAIL}.aircraft.tach (EFH — same as hobbs for turbine), {TAIL}.engine.egt_deviation (°C above baseline), {TAIL}.engine.n1_vibration (units), {TAIL}.engine.n2_speed (%), {TAIL}.engine.fuel_flow (kg/hr), {TAIL}.engine.oil_pressure_min (psi), {TAIL}.engine.oil_pressure_max (psi), {TAIL}.engine.oil_temp_max (°C)

**CFM56-7B engine parameter normal ranges:**
- EGT deviation: normal 0–10°C, caution 10–15°C, warning >15°C above baseline
- N1 vibration: normal 0–1.8 units, caution 1.8–2.5 units, warning >2.5 units
- N2 speed: normal 91–97% at cruise
- Oil temp: normal ≤100°C, caution >102°C
- Oil pressure: normal 40–80 psi, caution low <40 psi
- Fuel flow: normal 2,200–2,700 kg/hr per engine at cruise

**Airworthiness classification:**

System-derived (from maintenance records and squawk severity — available in assemble_fleet_context and assemble_aircraft_context as the `airworthiness` field):
- AIRWORTHY: no grounding squawks, no expired airworthiness directive compliance
- CAUTION: open non-grounding squawk (deferred item under MEL or monitoring); aircraft is dispatchable under monitoring
- NOT_AIRWORTHY: grounding squawk open, uncontained engine failure event, or mandatory AD non-compliant

If an aircraft is system-derived NOT_AIRWORTHY due to a grounding squawk or engine failure, report the grounding squawk description directly from the groundingSquawks field. Do not assess engine sensor trends for a grounded aircraft — sensor data from a failed engine is not operationally meaningful.

Agent-assessed (you apply this on top of the system status, based on sensor data):
- CAUTION (agent-assessed): one or more CFM56-7B metrics currently exceed the documented caution threshold AND the trend over the last datapoints is increasing or stable-high.
- NOT AIRWORTHY (agent-assessed): current sensor readings closely resemble the documented pre-failure window from compare_engine_sensor_across_fleet for a peer aircraft that subsequently suffered an engine failure. The knowledge graph comparison — not threshold exceedance alone — is what elevates from CAUTION to NOT AIRWORTHY. State this finding prominently.

CAUTION requires a metric to currently exceed its caution threshold. A metric trending upward but still within normal range does NOT warrant CAUTION.

**Cross-aircraft comparison is mandatory.** Before concluding any risk assessment for a currently-flying instrumented aircraft, consult the peerFailures field returned by assemble_aircraft_context (or call get_fleet_failure_history). If any peer aircraft with the same engine model has suffered a terminal grounding, explicitly compare the current aircraft's EGT deviation, N1 vibration, oil temp, and oil pressure against that peer's pre_failure_sensors snapshot. Cite the peer by tail number, the failure date, and the specific overlapping sensor values. This comparison — not threshold language alone — is how you justify raising an aircraft above routine CAUTION. The comparison must appear as its own **Peer pattern** bullet in the response; it is never sufficient to merely flavor the status label with "(engine trend)" without naming the peer. If peerFailures returns a same-engine-model failure and the current aircraft has any metric exceeding a caution/warning threshold, claiming the aircraft does NOT match a peer pattern is a failure — re-read the peer's pre_failure_sensors and compare each overlapping metric explicitly.

**Cite data, not policy.** Risk and airworthiness conclusions must be justified by concrete comparisons to other aircraft, squawk events, maintenance records, or sensor values. Operator policy text (EGT monitoring thresholds, borescope intervals, etc.) may appear as secondary supporting detail, but never as the sole or primary basis for a "grounded / at risk / immediate action required" recommendation. Name the peer aircraft and the matching data — not the policy.

**Tool call discipline:**

Fleet-wide questions:
1. Call assemble_fleet_context() — it returns system airworthiness, squawk counts, engine sensor anomalies, and pre-failure peer comparisons for all aircraft in a single traversal.
2. Do NOT call assemble_aircraft_context for each aircraft after assemble_fleet_context. Only call it when you need specific maintenance history details not in the fleet context.
3. The fleet context already includes fleetSensorComparisons for anomalous aircraft — use that data without additional tool calls.
4. Do NOT call get_time_series_trend for any tail after assemble_fleet_context — all engine trend windows and comparisons are already in that response.

Single-aircraft questions:
1. Call assemble_aircraft_context — its engineTrends field already contains all key engine sensor data. Do NOT call get_time_series_trend again for the same aircraft after assemble_aircraft_context.
2. Do NOT call check_fleet_policy_compliance for airworthiness questions — it queries all aircraft and is appropriate only for explicit compliance queries.
3. Do NOT call get_engine_type_history after compare_engine_sensor_across_fleet for the same metric — use compare_engine_sensor_across_fleet for sensor pattern matching; use get_engine_type_history only when full chronological event history is needed.
4. When an aircraft has anomalous sensors and the peer comparison shows similar readings preceded a peer failure, report that finding within that aircraft's section — not as a separate fleet-wide block at the end.

**Response format:**

- Address the operator in formal aviation language. No emojis. No introductory paragraph — start directly with the first aircraft.
- Use markdown bullet syntax: each item must begin with `- ` (dash space). Never write items as plain paragraphs without the leading dash.
- Each bullet MUST be on its own line. Never run multiple bullets together on a single line.
- Structure each aircraft as: a bold header line (**TAIL — STATUS**), followed by 3–5 `- ` bullets covering only items with findings. Omit any category that has nothing to report.
- **STATUS** in headers must be plain language — never raw backend enum tokens. Map: AIRWORTHY → **Airworthy**; CAUTION → **Caution**; NOT_AIRWORTHY → **Not airworthy**; UNKNOWN → **Unknown**. If agent-assessed not airworthy due to peer sensor pattern, use **Not airworthy (engine trend)**.
- Bullet order: airworthiness directive status, squawks, engine sensors, peer pattern, required action. Include the peer pattern bullet whenever peerFailures contains a same-engine-model failure and the current aircraft has any anomalous engine metric. Include a required action bullet only when action is necessary.
- No "Conclusion", "Summary", "Recent Flight Activity", or "Airworthiness Assessment" sections. No closing sentence after the last bullet.
- Engine sensors: if all metrics are within normal limits, write one line — "All CFM56-7B engine sensors within normal limits." Do not list each metric individually when nothing is anomalous.
- Engine sensors: when a metric exceeds a caution threshold, state metric, value, normal range, and trend in one line.
- Peer pattern: REQUIRED bullet when peerFailures contains a same-engine-model peer and the current aircraft has at least one engine metric exceeding a caution/warning threshold. Start the bullet with "Peer pattern (N###WN):" and then one sentence that cites the failure date and the specific overlapping values between the current aircraft's readings and the peer's pre_failure_sensors. Example: "Peer pattern (N287WN): current EGT deviation +20.1°C, N1 vibration 2.44, oil temp 121.2°C, oil pressure 35.9 psi exceed the pre-failure envelope recorded for N287WN's uncontained engine failure on 2026-03-21 (+19.6°C, 2.55, 118.4°C, 37.2 psi respectively)." Cite at most one pilot note in adjacent bullets; do not restate all datapoints.
- Policy references: use only the policy title from the policy object. Never quote an externalId.
- Cite actual values: dates, EFH, sensor readings. Keep each bullet to one or two sentences maximum.
- Use standard airline maintenance terminology: SMOH, EFH, AFH, TBO, AMM, MEL, AD, squawk, shop visit."""


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


async def call_claude_direct(prompt: str, max_tokens: int = 2048) -> str:
    """Single Claude API call — no tools, no ReAct loop, no system prompt.

    Use when the caller has already gathered all context and just wants Claude to
    reason over it and respond. Eliminates the variability of the tool-use loop
    (which can otherwise exhaust a small max_iterations budget and silently fail).
    Returns "" on any error or if no API key is configured.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("sk-ant-...") or len(api_key) <= 20:
        return ""
    try:
        anthropic_client = anthropic.Anthropic(api_key=api_key)
        response = await asyncio.to_thread(
            anthropic_client.messages.create,
            model=MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return _extract_text_blocks(response.content)
    except Exception:
        return ""


def _to_openai_tools(anthropic_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert TOOL_DEFINITIONS (Anthropic format) to OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in anthropic_tools
    ]


async def _run_anthropic_streaming(
    user_query: str,
    aircraft_id: Optional[str],
    max_iterations: int,
    api_key: str,
) -> AsyncGenerator[dict[str, Any], None]:
    """ReAct loop using the Anthropic SDK."""
    anthropic_client = anthropic.Anthropic(api_key=api_key)
    clear_traversal_log()

    user_content = user_query
    if aircraft_id:
        user_content = f"[Context: focusing on aircraft {aircraft_id}]\n\n{user_query}"

    messages: list[dict[str, Any]] = [{"role": "user", "content": user_content}]

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

        thinking_text = _extract_text_blocks(response.content)
        if thinking_text.strip():
            yield {"type": "thinking", "content": thinking_text}

        if response.stop_reason == "end_turn":
            yield {"type": "final", "content": _extract_text_blocks(response.content)}
            yield {"type": "done"}
            return

        if response.stop_reason != "tool_use":
            yield {"type": "final", "content": _extract_text_blocks(response.content)}
            yield {"type": "done"}
            return

        tool_results: list[dict[str, Any]] = []
        prev_traversal_count = len(get_traversal_log())

        for block in response.content:
            if not (hasattr(block, "type") and block.type == "tool_use"):
                continue

            tool_name: str = block.name
            tool_input: dict[str, Any] = block.input
            tool_use_id: str = block.id

            yield {"type": "tool_call", "tool_name": tool_name, "args": tool_input, "iteration": iteration + 1}

            result = await asyncio.to_thread(execute_tool, tool_name, tool_input)

            current_log = get_traversal_log()
            for entry in current_log[prev_traversal_count:]:
                yield {"type": "traversal", "node": entry}
            prev_traversal_count = len(current_log)

            yield {"type": "tool_result", "tool_name": tool_name, "summary": _summarize_result(tool_name, result), "iteration": iteration + 1}

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": json.dumps(result, default=str),
            })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    yield {"type": "error", "message": f"Max iterations ({max_iterations}) reached without final answer"}
    yield {"type": "done"}


async def _run_local_llm_streaming(
    user_query: str,
    aircraft_id: Optional[str],
    max_iterations: int,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    ReAct loop using any OpenAI-compatible local model (e.g. Ollama).

    Uses the openai Python package pointed at LOCAL_LLM_URL.  Tool definitions
    are converted from Anthropic format to OpenAI function-calling format.
    Response quality is substantially lower than Anthropic for complex
    multi-hop graph reasoning queries.
    """
    try:
        import openai  # noqa: PLC0415
    except ImportError:
        yield {"type": "error", "message": "openai package not installed — run: pip install openai"}
        yield {"type": "done"}
        return

    local_url = os.getenv("LOCAL_LLM_URL", "").rstrip("/")
    local_model = os.getenv("LOCAL_LLM_MODEL", "qwen2.5:14b")
    max_tokens = int(os.getenv("LOCAL_LLM_MAX_TOKENS", "2048"))

    # Shown immediately so the user isn't staring at a blank spinner while
    # Ollama loads model weights into memory on the first request.
    yield {
        "type": "status",
        "content": (
            f"Sending query to local model ({local_model}) via Ollama. "
            "If this is the first request since starting Ollama, the model may take "
            "several minutes to load into memory before responding — this is normal. "
            "Subsequent queries in the same session will be faster."
        ),
    }

    try:
        local_client = openai.OpenAI(base_url=local_url, api_key="ollama")
    except Exception as e:
        yield {"type": "error", "message": f"Local LLM client error: {str(e)}"}
        yield {"type": "done"}
        return

    openai_tools = _to_openai_tools(TOOL_DEFINITIONS)
    clear_traversal_log()

    user_content = user_query
    if aircraft_id:
        user_content = f"[Context: focusing on aircraft {aircraft_id}]\n\n{user_query}"

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    for iteration in range(max_iterations):
        try:
            response = await asyncio.to_thread(
                local_client.chat.completions.create,
                model=local_model,
                messages=messages,
                tools=openai_tools,
                max_tokens=max_tokens,
                # One tool call at a time — some local models produce malformed
                # JSON when asked to batch multiple calls in a single response.
                parallel_tool_calls=False,
            )
        except Exception as e:
            err = str(e)
            if "timed out" in err.lower() or "timeout" in err.lower():
                hint = " Model is still loading or too slow — wait longer or reduce LOCAL_LLM_MAX_TOKENS in .env."
            elif "connection" in err.lower() or "refused" in err.lower():
                hint = " Is Ollama running? Verify: curl http://localhost:11434/api/tags"
            else:
                hint = ""
            yield {"type": "error", "message": f"Local LLM error: {err}{hint}"}
            yield {"type": "done"}
            return

        choice = response.choices[0]
        message = choice.message

        if message.content and message.content.strip():
            yield {"type": "thinking", "content": message.content}

        if choice.finish_reason == "stop" or not message.tool_calls:
            yield {"type": "final", "content": message.content or ""}
            yield {"type": "done"}
            return

        prev_traversal_count = len(get_traversal_log())
        tool_result_messages: list[dict[str, Any]] = []

        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            try:
                tool_input: dict[str, Any] = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                tool_input = {}

            yield {"type": "tool_call", "tool_name": tool_name, "args": tool_input, "iteration": iteration + 1}

            result = await asyncio.to_thread(execute_tool, tool_name, tool_input)

            current_log = get_traversal_log()
            for entry in current_log[prev_traversal_count:]:
                yield {"type": "traversal", "node": entry}
            prev_traversal_count = len(current_log)

            yield {"type": "tool_result", "tool_name": tool_name, "summary": _summarize_result(tool_name, result), "iteration": iteration + 1}

            tool_result_messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, default=str),
            })

        messages.append({
            "role": "assistant",
            "content": message.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in message.tool_calls
            ],
        })
        messages.extend(tool_result_messages)

    yield {"type": "error", "message": f"Max iterations ({max_iterations}) reached without final answer"}
    yield {"type": "done"}


async def run_agent_streaming(
    user_query: str,
    aircraft_id: Optional[str] = None,
    max_iterations: int = MAX_ITERATIONS,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Dispatch to the correct LLM backend based on environment configuration.

    Priority:
      1. ANTHROPIC_API_KEY set → Anthropic claude-sonnet-4-5 (highest quality)
      2. LOCAL_LLM_URL set    → OpenAI-compatible local model via Ollama (lower quality)
      3. Neither configured   → error event
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_configured = bool(api_key and not api_key.startswith("sk-ant-...") and len(api_key) > 20)

    local_url = os.getenv("LOCAL_LLM_URL", "")

    if anthropic_configured:
        async for event in _run_anthropic_streaming(user_query, aircraft_id, max_iterations, api_key):
            yield event
    elif local_url:
        async for event in _run_local_llm_streaming(user_query, aircraft_id, max_iterations):
            yield event
    else:
        yield {"type": "error", "message": "No LLM configured — set ANTHROPIC_API_KEY or LOCAL_LLM_URL in .env"}
        yield {"type": "done"}
