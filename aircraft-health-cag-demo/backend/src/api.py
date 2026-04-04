"""
Application API Server — FastAPI on port 3000.

Exposes the aircraft health assistant to the React frontend via:
  POST /api/query           — SSE-streamed agent responses
  GET  /api/status          — aircraft health dashboard data
  GET  /api/squawks         — open squawks
  GET  /api/maintenance/upcoming — upcoming maintenance items
  GET  /api/health          — API key + mock CDF reachability check

CORS is enabled for http://localhost:5173 (Vite dev server).
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

from .agent.agent import run_agent_streaming  # noqa: E402
from .agent.context import assemble_aircraft_context  # noqa: E402

app = FastAPI(
    title="Aircraft Health CAG Demo API",
    description="N4798E knowledge graph query API with CAG-powered agent",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    question: str


class AircraftStatusResponse(BaseModel):
    hobbs: float
    tach: float
    engineSMOH: float
    engineTBO: int
    engineSMOHPercent: float
    annualDueDate: str
    annualDaysRemaining: Optional[int]
    openSquawkCount: int
    groundingSquawkCount: int
    isAirworthy: bool
    lastMaintenanceDate: Optional[str]
    dataFreshAt: str


class SquawkResponse(BaseModel):
    externalId: str
    description: str
    component: str
    severity: str
    status: str
    dateIdentified: Optional[str]
    metadata: dict[str, str]


class MaintenanceItemResponse(BaseModel):
    component: str
    description: str
    maintenanceType: str
    nextDueHobbs: float
    hoursUntilDue: float
    nextDueDate: Optional[str]
    daysUntilDue: Optional[int]


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

async def _check_mock_cdf() -> bool:
    """Verify the mock CDF server is reachable."""
    base_url = os.getenv("CDF_BASE_URL", "http://localhost:4000")
    try:
        async with httpx.AsyncClient(timeout=2.0) as http:
            resp = await http.get(f"{base_url}/health")
            return resp.status_code == 200
    except Exception:
        return False


def _get_store_counts() -> dict[str, int]:
    """Import store counts for the health endpoint."""
    try:
        from .agent.tools import client
        project = os.getenv("CDF_PROJECT", "n4798e")
        base_url = os.getenv("CDF_BASE_URL", "http://localhost:4000")
        resp = httpx.get(f"{base_url}/health", timeout=2.0)
        if resp.status_code == 200:
            return resp.json().get("store", {})
    except Exception:
        pass
    return {}


@app.get("/api/health")
async def health_check() -> dict[str, Any]:
    """
    GET /api/health — frontend polls this on load.

    Returns anthropic_api_key_configured: false if the key is missing/placeholder,
    triggering the SetupBanner in the UI and disabling the query input.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    key_configured = bool(api_key and not api_key.startswith("sk-ant-...") and len(api_key) > 20)
    mock_cdf_reachable = await _check_mock_cdf()
    store_counts = _get_store_counts()

    status = "ok" if (key_configured and mock_cdf_reachable) else "degraded"
    if not mock_cdf_reachable:
        status = "mock_cdf_offline"
    if not key_configured:
        status = "api_key_missing" if not api_key else "api_key_invalid"

    return {
        "status": status,
        "anthropic_api_key_configured": key_configured,
        "mock_cdf_reachable": mock_cdf_reachable,
        "store": store_counts,
        "checkedAt": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Agent query — SSE streaming
# ---------------------------------------------------------------------------

@app.post("/api/query")
async def query_agent(req: QueryRequest) -> EventSourceResponse:
    """
    POST /api/query — streams agent ReAct loop steps via Server-Sent Events.

    Each SSE event has a JSON data payload with a "type" field:
      thinking, tool_call, tool_result, traversal, final, error, done
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key.startswith("sk-ant-...") or len(api_key) <= 20:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "ANTHROPIC_API_KEY not configured",
                "hint": "Add your Anthropic API key to backend/.env",
            },
        )

    async def event_stream() -> AsyncGenerator[dict[str, str], None]:
        async for step in run_agent_streaming(req.question):
            yield {"data": json.dumps(step)}

    return EventSourceResponse(event_stream())


# ---------------------------------------------------------------------------
# Dashboard endpoints
# ---------------------------------------------------------------------------

@app.get("/api/status")
async def get_aircraft_status() -> dict[str, Any]:
    """
    GET /api/status — assembles aircraft health summary for the dashboard.
    Calls the CAG context assembler and extracts key status fields.
    """
    try:
        ctx = await asyncio.to_thread(assemble_aircraft_context)
        if "error" in ctx:
            raise HTTPException(status_code=503, detail=ctx["error"])

        sensors = ctx.get("sensors", {})
        hobbs = ctx.get("currentHobbs", 0.0)
        tach = ctx.get("currentTach", 0.0)
        engine_smoh = ctx.get("engineSMOH", 1450.0)

        # Most recent maintenance date
        all_maint = ctx.get("allMaintenance", [])
        last_maint_date: Optional[str] = None
        if all_maint:
            most_recent = max(all_maint, key=lambda x: x.get("startTime") or 0)
            last_maint_date = most_recent.get("metadata", {}).get("date")

        # Oil change overdue calculation — derived from upcoming maintenance list
        upcoming = ctx.get("upcomingMaintenance", [])
        oil_item = next(
            (u for u in upcoming if "oil_change" in (u.get("maintenanceType") or "").lower()),
            None,
        )
        oil_hours_overdue = (
            round(-oil_item["hoursUntilDue"], 1)
            if oil_item and oil_item.get("isOverdue")
            else 0.0
        )

        return {
            "hobbs": hobbs,
            "tach": tach,
            "engineSMOH": engine_smoh,
            "engineTBO": ctx.get("engineTBO", 2000),
            "engineSMOHPercent": ctx.get("engineSMOHPercent", 0.0),
            "annualDueDate": ctx.get("annualDueDate", ""),
            "annualDaysRemaining": ctx.get("annualDaysRemaining"),
            "openSquawkCount": len(ctx.get("openSquawks", [])),
            "groundingSquawkCount": len(ctx.get("groundingSquawks", [])),
            "isAirworthy": ctx.get("isAirworthy", False),
            "oilHoursOverdue": oil_hours_overdue,
            "lastMaintenanceDate": last_maint_date,
            "dataFreshAt": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/squawks")
async def get_squawks() -> list[dict[str, Any]]:
    """GET /api/squawks — returns all open squawks with metadata."""
    try:
        ctx = await asyncio.to_thread(assemble_aircraft_context)
        if "error" in ctx:
            raise HTTPException(status_code=503, detail=ctx["error"])

        result = []
        for sq in ctx.get("openSquawks", []):
            meta = sq.get("metadata", {})
            result.append({
                "externalId": sq.get("externalId", ""),
                "description": sq.get("description", ""),
                "component": meta.get("component_id", ""),
                "severity": meta.get("severity", "unknown"),
                "status": meta.get("status", "open"),
                "dateIdentified": meta.get("date_identified", ""),
                "metadata": meta,
            })
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/maintenance/upcoming")
async def get_upcoming_maintenance() -> list[dict[str, Any]]:
    """GET /api/maintenance/upcoming — returns maintenance due in the next 100 hobbs."""
    try:
        ctx = await asyncio.to_thread(assemble_aircraft_context)
        if "error" in ctx:
            raise HTTPException(status_code=503, detail=ctx["error"])

        return ctx.get("upcomingMaintenance", [])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/maintenance/history")
async def get_maintenance_history(
    limit: int = 1000,
    page: int = 1,
    per_page: int = 25,
    component: Optional[str] = None,
    year: Optional[int] = None,
) -> dict[str, Any]:
    """
    GET /api/maintenance/history — paginated maintenance records with optional filters.

    Query params:
      page     — page number (1-indexed, default 1)
      per_page — records per page (default 25)
      component — filter by component_id substring (optional)
      year     — filter by year of service date (optional)
    """
    try:
        ctx = await asyncio.to_thread(assemble_aircraft_context)
        if "error" in ctx:
            raise HTTPException(status_code=503, detail=ctx["error"])

        records = ctx.get("allMaintenance", [])
        # Sort oldest → newest for display
        records_sorted = sorted(records, key=lambda x: x.get("startTime") or 0, reverse=True)

        # Apply filters
        if component:
            component_lower = component.lower()
            records_sorted = [
                r for r in records_sorted
                if component_lower in (r.get("metadata", {}).get("component_id", "") or "").lower()
            ]
        if year:
            records_sorted = [
                r for r in records_sorted
                if _record_year(r) == year
            ]

        total = len(records_sorted)
        total_pages = max(1, (total + per_page - 1) // per_page)
        start = (page - 1) * per_page
        end = start + per_page
        page_records = records_sorted[start:end]

        return {
            "records": page_records,
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _record_year(record: dict[str, Any]) -> Optional[int]:
    """Extract the year from a maintenance record's date metadata."""
    date_str = record.get("metadata", {}).get("date", "")
    if date_str:
        try:
            return int(date_str[:4])
        except (ValueError, TypeError):
            pass
    return None


class DemoStateRequest(BaseModel):
    state: str


@app.post("/api/demo-state")
async def set_demo_state(req: DemoStateRequest) -> dict[str, Any]:
    """
    POST /api/demo-state — switch the active demo state on both the mock CDF server
    and the local in-memory store reference.

    Valid states: clean, caution, grounded.

    The mock CDF server maintains three sets of events/datapoints in memory,
    loaded from state-specific JSON files at startup. This endpoint instructs it
    to switch which set is "active" — subsequent CDF SDK queries will return data
    for the selected state.

    The frontend calls this whenever the demo mode selector changes.
    """
    state = req.state.lower()
    valid = ("clean", "caution", "grounded")
    if state not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid state '{state}'. Must be one of: {valid}")

    base_url = os.getenv("CDF_BASE_URL", "http://localhost:4000")
    try:
        async with httpx.AsyncClient(timeout=5.0) as http:
            resp = await http.post(
                f"{base_url}/admin/set-state",
                json={"state": state},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            return {"status": "ok", "active_state": state, "mock_cdf": resp.json()}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Mock CDF unreachable: {e}")


@app.get("/api/flights")
async def get_flights(
    page: int = 1,
    per_page: int = 25,
    route: Optional[str] = None,
    year: Optional[int] = None,
) -> dict[str, Any]:
    """
    GET /api/flights — paginated flight records with optional filters.

    Reads datapoints from the active demo state's store via the CDF SDK.
    Returns one row per flight constructed from the hobbs time series datapoints.

    Query params:
      page     — page number (1-indexed, default 1)
      per_page — records per page (default 25)
      route    — filter by route substring (optional)
      year     — filter by flight year (optional)
    """
    try:
        from .agent.tools import get_events  # noqa: PLC0415

        # Use maintenance events to find matching flight notes, but primarily
        # build the flight list from the events store which has all flight-linked data.
        # We fetch all MaintenanceRecord events and look for flight metadata.
        # Actually, the canonical flight history lives in the CSV — read it via the store.
        from mock_cdf.store.store import store as cdf_store  # type: ignore[import]

        # Gather datapoints from the hobbs time series
        dp_list = cdf_store.get_datapoints("aircraft.hobbs")
        if not dp_list:
            return {"records": [], "total": 0, "page": page, "per_page": per_page, "total_pages": 0}

        # Each datapoint corresponds to a flight (hobbs_end reading)
        # Pair consecutive datapoints as hobbs_start / hobbs_end
        sorted_dps = sorted(dp_list, key=lambda d: d.timestamp)

        # Build flights from consecutive hobbs readings
        flights: list[dict[str, Any]] = []
        for i in range(len(sorted_dps)):
            dp = sorted_dps[i]
            hobbs_end = dp.value
            hobbs_start = sorted_dps[i - 1].value if i > 0 else max(0.0, hobbs_end - 1.0)
            ts_iso = datetime.fromtimestamp(dp.timestamp / 1000, tz=timezone.utc).isoformat()

            # Pull matching engine readings for same timestamp from other time series
            cht = _dp_at(cdf_store, "engine.cht_max", dp.timestamp)
            egt = _dp_at(cdf_store, "engine.egt_max", dp.timestamp)
            oil_p_min = _dp_at(cdf_store, "engine.oil_pressure_min", dp.timestamp)
            oil_p_max = _dp_at(cdf_store, "engine.oil_pressure_max", dp.timestamp)
            oil_t = _dp_at(cdf_store, "engine.oil_temp_max", dp.timestamp)
            fuel = _dp_at(cdf_store, "aircraft.fuel_used", dp.timestamp)

            flight_year = int(ts_iso[:4])
            flights.append({
                "timestamp": ts_iso,
                "hobbs_start": round(hobbs_start, 1),
                "hobbs_end": round(hobbs_end, 1),
                "duration": round(hobbs_end - hobbs_start, 1),
                "cht_max": cht,
                "egt_max": egt,
                "oil_pressure_min": oil_p_min,
                "oil_pressure_max": oil_p_max,
                "oil_temp_max": oil_t,
                "fuel_used_gal": fuel,
                "year": flight_year,
            })

        # Apply filters
        filtered = flights
        if year:
            filtered = [f for f in filtered if f["year"] == year]
        if route:
            # Route info isn't stored in datapoints — pass through for now
            pass

        # Sort newest first
        filtered = sorted(filtered, key=lambda f: f["timestamp"], reverse=True)

        total = len(filtered)
        total_pages = max(1, (total + per_page - 1) // per_page)
        start = (page - 1) * per_page
        return {
            "records": filtered[start : start + per_page],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _dp_at(store: Any, ts_ext_id: str, timestamp_ms: int) -> Optional[float]:
    """Return the datapoint value at the given timestamp_ms from a time series."""
    dps = store.get_datapoints(ts_ext_id)
    if not dps:
        return None
    for dp in dps:
        if dp.timestamp == timestamp_ms:
            return dp.value
    return None


@app.get("/api/graph")
async def get_graph_data() -> dict[str, Any]:
    """
    GET /api/graph — returns the full knowledge graph structure for visualization.

    Returns nodes and links suitable for react-force-graph-2d:
      nodes: [{id, label, type, group, metadata}]
      links: [{source, target, type}]

    Node types map to CDF resource types:
      asset     → blue   (component hierarchy)
      timeseries → green (sensor metrics)
      event     → orange (maintenance records, squawks)
      file      → purple (POH, ADs, SBs)
    """
    try:
        return await asyncio.to_thread(_sync_get_graph_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _sync_get_graph_data() -> dict[str, Any]:
    """Synchronous graph data builder — called via asyncio.to_thread."""
    from mock_cdf.store.store import store as cdf_store  # type: ignore[import]

    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()
    seen_links: set[tuple[str, str, str]] = set()

    def _add_link(src: str, tgt: str, rel_type: str) -> None:
        key = (src, tgt, rel_type)
        if key not in seen_links:
            seen_links.add(key)
            links.append({"source": src, "target": tgt, "type": rel_type})

    # Asset nodes + parent-child hierarchy links
    for asset in cdf_store.get_assets():
        node_id = asset.externalId or str(asset.id)
        if node_id not in seen_nodes:
            nodes.append({
                "id": node_id,
                "label": asset.name or node_id,
                "type": "asset",
                "group": 1,
                "metadata": asset.metadata or {},
            })
            seen_nodes.add(node_id)
        # Add parent→child link from the asset's own parentExternalId field
        if asset.parentExternalId:
            _add_link(asset.parentExternalId, node_id, "HAS_COMPONENT")

    # TimeSeries nodes
    for ts in cdf_store.get_timeseries():
        node_id = ts.externalId or str(ts.id)
        if node_id not in seen_nodes:
            nodes.append({
                "id": node_id,
                "label": ts.name or node_id,
                "type": "timeseries",
                "group": 2,
                "unit": ts.unit,
            })
            seen_nodes.add(node_id)
        # Link TS to its parent asset
        parent_id = _asset_ext_id_from_id(cdf_store, ts.assetId)
        if parent_id:
            _add_link(parent_id, node_id, "HAS_TIMESERIES")

    # Relationship-driven links (document links, AD/SB references, etc.)
    for rel in cdf_store.get_relationships():
        src = rel.sourceExternalId
        tgt = rel.targetExternalId
        if src and tgt:
            _add_link(src, tgt, rel.relationshipType or "RELATED_TO")

    # File nodes
    for f in cdf_store.get_files():
        node_id = f.externalId or str(f.id)
        if node_id not in seen_nodes:
            nodes.append({
                "id": node_id,
                "label": f.name or node_id,
                "type": "file",
                "group": 4,
            })
            seen_nodes.add(node_id)

    # Count links per node for sizing
    link_counts: dict[str, int] = {}
    for link in links:
        link_counts[link["source"]] = link_counts.get(link["source"], 0) + 1
        link_counts[link["target"]] = link_counts.get(link["target"], 0) + 1
    for node in nodes:
        node["linkCount"] = link_counts.get(node["id"], 0)

    return {
        "nodes": nodes,
        "links": links,
        "stats": {
            "assets": sum(1 for n in nodes if n["type"] == "asset"),
            "timeseries": sum(1 for n in nodes if n["type"] == "timeseries"),
            "events": sum(1 for n in nodes if n["type"] == "event"),
            "files": sum(1 for n in nodes if n["type"] == "file"),
            "relationships": len(links),
        },
    }


def _asset_ext_id_from_id(store: Any, asset_id: Optional[int]) -> Optional[str]:
    """Look up asset externalId from numeric asset id."""
    if not asset_id:
        return None
    for asset in store.get_assets():
        if asset.id == asset_id:
            return asset.externalId
    return None


@app.get("/api/components")
async def get_components() -> list[dict[str, Any]]:
    """
    GET /api/components — returns the full asset component hierarchy with status info.

    Each component includes:
      - Basic asset metadata (name, type, description)
      - Last maintenance date
      - Next maintenance due (hobbs / date)
      - Status indicator derived from overdue/upcoming maintenance
    """
    try:
        return await asyncio.to_thread(_sync_get_components)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _sync_get_components() -> list[dict[str, Any]]:
    """Synchronous components builder — called via asyncio.to_thread."""
    from mock_cdf.store.store import store as cdf_store  # type: ignore[import]

    assets = cdf_store.get_assets()
    events = list(cdf_store.get_events())

    # Build maintenance lookup: assetId → sorted maintenance events
    maint_by_asset: dict[int, list[Any]] = {}
    for event in events:
        if event.type in ("MaintenanceRecord", "Inspection"):
            for aid in event.assetIds or []:
                if aid not in maint_by_asset:
                    maint_by_asset[aid] = []
                maint_by_asset[aid].append(event)

    # Get current hobbs
    hobbs_dps = cdf_store.get_datapoints("aircraft.hobbs")
    current_hobbs = 0.0
    if hobbs_dps:
        current_hobbs = max(dp.value for dp in hobbs_dps)

    today = datetime.now(timezone.utc)
    result: list[dict[str, Any]] = []

    for asset in sorted(assets, key=lambda a: a.externalId or ""):
        maint_records = sorted(
            maint_by_asset.get(asset.id, []),
            key=lambda e: e.startTime or 0,
            reverse=True,
        )

        last_maint_date: Optional[str] = None
        next_due_hobbs: Optional[float] = None
        next_due_date: Optional[str] = None

        if maint_records:
            last_maint_date = maint_records[0].metadata.get("date") if maint_records[0].metadata else None
            # Use the most-recent record that has a next_due_hobbs value.
            # Taking max() would resurrect stale historical records with old Hobbs baselines.
            for rec in maint_records:
                meta = rec.metadata or {}
                ndh = meta.get("next_due_hobbs")
                if ndh:
                    try:
                        next_due_hobbs = float(ndh)
                        next_due_date = meta.get("next_due_date")
                        break  # Stop at first (most recent) record with a value
                    except (ValueError, TypeError):
                        pass

        # Determine status
        status = "ok"
        if next_due_hobbs is not None and current_hobbs > 0:
            hours_remaining = next_due_hobbs - current_hobbs
            if hours_remaining < 0:
                status = "overdue"
            elif hours_remaining <= 10:
                status = "due_soon"
        if next_due_date:
            try:
                due_dt = datetime.fromisoformat(next_due_date.replace("Z", "+00:00"))
                if due_dt.tzinfo is None:
                    due_dt = due_dt.replace(tzinfo=timezone.utc)
                days_remaining = (due_dt - today).days
                if days_remaining < 0:
                    status = "overdue"
                elif days_remaining <= 30 and status == "ok":
                    status = "due_soon"
            except (ValueError, TypeError):
                pass

        meta = asset.metadata or {}
        result.append({
            "externalId": asset.externalId,
            "name": asset.name,
            "description": asset.description,
            "parentExternalId": asset.parentExternalId,
            "metadata": meta,
            "lastMaintenanceDate": last_maint_date,
            "nextDueHobbs": next_due_hobbs,
            "nextDueDate": next_due_date,
            "currentHobbs": current_hobbs,
            "hoursUntilDue": round(next_due_hobbs - current_hobbs, 1) if next_due_hobbs and current_hobbs > 0 else None,
            "status": status,
            "maintenanceCount": len(maint_records),
        })

    return result


@app.on_event("startup")
async def on_startup() -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    key_ok = bool(api_key and not api_key.startswith("sk-ant-...") and len(api_key) > 20)
    mock_cdf_ok = await _check_mock_cdf()

    print("\n✈  Aircraft Health CAG Demo API running on port 3000")
    print(f"   ANTHROPIC_API_KEY: {'✓ configured' if key_ok else '✗ MISSING — add to backend/.env'}")
    print(f"   Mock CDF server:   {'✓ reachable' if mock_cdf_ok else '✗ not reachable — start mock-cdf first'}")
    print("   Endpoints: POST /api/query, GET /api/status, /api/squawks, /api/maintenance/upcoming\n")
