"""
Application API Server — FastAPI on port 8080.

Southwest Airlines Fleet CAG Demo endpoints:
  POST /api/query           — SSE-streamed agent responses (body: {question, aircraft?})
  GET  /api/fleet           — all four aircraft status summary
  GET  /api/status          — single aircraft status (?aircraft=N287WN required)
  GET  /api/squawks         — open squawks (?aircraft=N287WN)
  GET  /api/maintenance/upcoming  — upcoming maintenance (?aircraft=N287WN)
  GET  /api/maintenance/history   — paginated history (?aircraft=N287WN)
  GET  /api/flights         — paginated flight records (?aircraft=N287WN)
  GET  /api/components      — component hierarchy with status (?aircraft=N287WN)
  GET  /api/policies        — operational policy list
  GET  /api/graph           — full knowledge graph for visualization
  GET  /api/health          — API key + mock CDF reachability
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

from .agent.agent import run_agent_streaming  # noqa: E402
from .agent.context import (  # noqa: E402
    _date_after_calendar_months,
    _oil_change_calendar_months_from_policy,
    assemble_aircraft_context,
)
from .date_only import calendar_days_until_iso  # noqa: E402
from .aircraft_times import (  # noqa: E402
    current_hobbs_from_cdf_store,
    current_tach_from_cdf_store,
    next_due_tach_from_meta,
)

TAILS = (
    "N287WN", "N246WN", "N220WN", "N235WN",
    "N231WN", "N251WN", "N266WN", "N277WN", "N291WN",
)
INSTRUMENTED_TAILS = ("N287WN", "N246WN", "N220WN", "N235WN")
DEFAULT_TAIL = "N246WN"

app = FastAPI(
    title="Southwest Airlines Fleet CAG Demo",
    description="Fleet knowledge graph query API with CAG-powered agent",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4000",
        "http://127.0.0.1:4000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    question: str
    aircraft: Optional[str] = None


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

async def _check_mock_cdf() -> bool:
    base_url = os.getenv("CDF_BASE_URL", "http://localhost:4001")
    try:
        async with httpx.AsyncClient(timeout=2.0) as http:
            resp = await http.get(f"{base_url}/health")
            return resp.status_code == 200
    except Exception:
        return False


def _mock_cdf_fleet_ready_sync() -> bool:
    """
    True only if we can retrieve a fleet aircraft via the same byids path the SDK uses.

    Port 4001 may be occupied by a non-mock process that still returns HTTP 200 on /health,
    which would make _check_mock_cdf True while assets.retrieve returns None.
    """
    base_url = os.getenv("CDF_BASE_URL", "http://localhost:4001").rstrip("/")
    project = os.getenv("CDF_PROJECT", "southwest_airlines")
    try:
        h = httpx.get(f"{base_url}/health", timeout=2.0)
        if h.status_code != 200:
            return False
        store = h.json().get("store") or {}
        if int(store.get("assets", 0) or 0) >= 4:
            return True
        url = f"{base_url}/api/v1/projects/{project}/assets/byids"
        r = httpx.post(
            url,
            json={"items": [{"externalId": "N287WN"}]},
            headers={"Content-Type": "application/json"},
            timeout=3.0,
        )
        if r.status_code != 200:
            return False
        items = r.json().get("items") or []
        return len(items) > 0
    except Exception:
        return False


async def _mock_cdf_fleet_ready() -> bool:
    return await asyncio.to_thread(_mock_cdf_fleet_ready_sync)


def _get_store_counts() -> dict[str, int]:
    try:
        base_url = os.getenv("CDF_BASE_URL", "http://localhost:4001")
        resp = httpx.get(f"{base_url}/health", timeout=2.0)
        if resp.status_code == 200:
            return resp.json().get("store", {})
    except Exception:
        pass
    return {}


@app.get("/api/health")
async def health_check() -> dict[str, Any]:
    """GET /api/health — frontend polls on load to check API key and services."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_configured = bool(api_key and not api_key.startswith("sk-ant-...") and len(api_key) > 20)
    local_llm_url = os.getenv("LOCAL_LLM_URL", "")
    local_llm_configured = bool(local_llm_url)
    llm_ready = anthropic_configured or local_llm_configured

    mock_cdf_reachable = await _check_mock_cdf()
    mock_cdf_fleet_ready = await _mock_cdf_fleet_ready() if mock_cdf_reachable else False
    store_counts = _get_store_counts()

    if not mock_cdf_reachable:
        status = "mock_cdf_offline"
    elif not mock_cdf_fleet_ready:
        status = "degraded"
    elif not llm_ready:
        status = "llm_missing"
    else:
        status = "ok"

    return {
        "status": status,
        "anthropic_api_key_configured": anthropic_configured,
        "local_llm_configured": local_llm_configured,
        "llm_ready": llm_ready,
        "mock_cdf_reachable": mock_cdf_reachable,
        "mock_cdf_fleet_ready": mock_cdf_fleet_ready,
        "store": store_counts,
        "checkedAt": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Agent query — SSE streaming
# ---------------------------------------------------------------------------

@app.post("/api/query")
async def query_agent(req: QueryRequest) -> EventSourceResponse:
    """
    POST /api/query — streams agent ReAct steps via Server-Sent Events.
    Body: { question: string, aircraft?: string }
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_configured = bool(api_key and not api_key.startswith("sk-ant-...") and len(api_key) > 20)
    local_llm_url = os.getenv("LOCAL_LLM_URL", "")
    if not anthropic_configured and not local_llm_url:
        raise HTTPException(
            status_code=503,
            detail={"error": "No LLM configured", "hint": "Set ANTHROPIC_API_KEY or LOCAL_LLM_URL in .env"},
        )

    async def event_stream() -> AsyncGenerator[dict[str, str], None]:
        async for step in run_agent_streaming(req.question, aircraft_id=req.aircraft):
            yield {"data": json.dumps(step)}

    return EventSourceResponse(event_stream())


# ---------------------------------------------------------------------------
# Fleet overview
# ---------------------------------------------------------------------------

@app.get("/api/fleet")
async def get_fleet() -> list[dict[str, Any]]:
    """GET /api/fleet — aggregate status for all four aircraft."""
    try:
        results = []
        for tail in TAILS:
            ctx = await asyncio.to_thread(assemble_aircraft_context, tail)
            if "error" in ctx:
                # Same shape as success so the UI never crashes on .toFixed / missing keys
                results.append({
                    "tail": tail,
                    "name": tail,
                    "smoh": 0.0,
                    "tbo": 2000,
                    "smohPercent": 0.0,
                    "hobbs": 0.0,
                    "tach": 0.0,
                    "airworthiness": "UNKNOWN",
                    "isAirworthy": False,
                    "openSquawkCount": 0,
                    "groundingSquawkCount": 0,
                    "oilHoursOverdue": 0.0,
                    "oilTachHoursOverdue": 0.0,
                    "oilTachHoursUntilDue": 0.0,
                    "oilDaysUntilDue": None,
                    "annualDaysRemaining": None,
                    "annualDueDate": "",
                    "lastMaintenanceDate": None,
                    "metadata": {"load_error": str(ctx.get("error", "unknown"))},
                })
                continue

            all_maint = ctx.get("allMaintenance", [])
            last_maint_date: Optional[str] = None
            if all_maint:
                most_recent = max(all_maint, key=lambda x: x.get("startTime") or 0)
                last_maint_date = most_recent.get("metadata", {}).get("date")

            results.append({
                "tail": tail,
                "name": ctx.get("aircraft", {}).get("name", tail),
                "smoh": ctx.get("engineSMOH", 0),
                "tbo": ctx.get("engineTBO", 2000),
                "smohPercent": ctx.get("engineSMOHPercent", 0),
                "engine2SMOH": ctx.get("engine2SMOH", 0),
                "engine2TBO": ctx.get("engine2TBO", 30000),
                "engine2SMOHPercent": ctx.get("engine2SMOHPercent", 0),
                "hobbs": ctx.get("currentHobbs", 0),
                "tach": ctx.get("currentTach", 0),
                "airworthiness": ctx.get("airworthiness", "UNKNOWN"),
                "isAirworthy": ctx.get("isAirworthy", False),
                "openSquawkCount": len(ctx.get("openSquawks", [])),
                "groundingSquawkCount": len(ctx.get("groundingSquawks", [])),
                "oilHoursOverdue": ctx.get("oilTachHoursOverdue", ctx.get("oilHoursOverdue", 0)),
                "oilTachHoursOverdue": ctx.get("oilTachHoursOverdue", 0),
                "oilTachHoursUntilDue": ctx.get("oilTachHoursUntilDue", 0),
                "oilDaysUntilDue": ctx.get("oilDaysUntilDue"),
                "annualDaysRemaining": ctx.get("annualDaysRemaining"),
                "annualDueDate": ctx.get("annualDueDate", ""),
                "lastMaintenanceDate": last_maint_date,
                "metadata": ctx.get("aircraft", {}).get("metadata", {}),
            })
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Per-aircraft endpoints (require ?aircraft= query param)
# ---------------------------------------------------------------------------

def _require_tail(aircraft: Optional[str]) -> str:
    if not aircraft:
        aircraft = DEFAULT_TAIL
    if aircraft not in TAILS:
        raise HTTPException(status_code=400, detail=f"Unknown aircraft '{aircraft}'. Valid: {TAILS}")
    return aircraft


@app.get("/api/status")
async def get_aircraft_status(aircraft: Optional[str] = Query(default=None)) -> dict[str, Any]:
    """GET /api/status?aircraft=N287WN — single aircraft health summary."""
    tail = _require_tail(aircraft)
    try:
        ctx = await asyncio.to_thread(assemble_aircraft_context, tail)
        if "error" in ctx:
            raise HTTPException(status_code=503, detail=ctx["error"])

        all_maint = ctx.get("allMaintenance", [])
        last_maint_date: Optional[str] = None
        if all_maint:
            most_recent = max(all_maint, key=lambda x: x.get("startTime") or 0)
            last_maint_date = most_recent.get("metadata", {}).get("date")

        return {
            "tail": tail,
            "hobbs": ctx.get("currentHobbs", 0),
            "tach": ctx.get("currentTach", 0),
            "engineSMOH": ctx.get("engineSMOH", 0),
            "engineTBO": ctx.get("engineTBO", 2000),
            "engineSMOHPercent": ctx.get("engineSMOHPercent", 0),
            "engine2SMOH": ctx.get("engine2SMOH", 0),
            "engine2TBO": ctx.get("engine2TBO", 30000),
            "engine2SMOHPercent": ctx.get("engine2SMOHPercent", 0),
            "annualDueDate": ctx.get("annualDueDate", ""),
            "annualDaysRemaining": ctx.get("annualDaysRemaining"),
            "openSquawkCount": len(ctx.get("openSquawks", [])),
            "groundingSquawkCount": len(ctx.get("groundingSquawks", [])),
            "airworthiness": ctx.get("airworthiness", "UNKNOWN"),
            "isAirworthy": ctx.get("isAirworthy", False),
            "oilHoursOverdue": ctx.get("oilTachHoursOverdue", ctx.get("oilHoursOverdue", 0)),
            "oilTachHoursOverdue": ctx.get("oilTachHoursOverdue", 0),
            "oilTachHoursUntilDue": ctx.get("oilTachHoursUntilDue", 0),
            "oilNextDueTach": ctx.get("oilNextDueTach", 0),
            "oilNextDueDate": ctx.get("oilNextDueDate", ""),
            "oilDaysUntilDue": ctx.get("oilDaysUntilDue"),
            "oilNextDueHobbs": ctx.get("oilNextDueTach", ctx.get("oilNextDueHobbs", 0)),
            "lastMaintenanceDate": last_maint_date,
            "dataFreshAt": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/squawks")
async def get_squawks(aircraft: Optional[str] = Query(default=None)) -> list[dict[str, Any]]:
    """GET /api/squawks?aircraft=N287WN — open squawks for one aircraft."""
    tail = _require_tail(aircraft)
    try:
        ctx = await asyncio.to_thread(assemble_aircraft_context, tail)
        if "error" in ctx:
            raise HTTPException(status_code=503, detail=ctx["error"])

        result = []
        for sq in ctx.get("allSquawks", []):
            meta = sq.get("metadata", {})
            result.append({
                "externalId": sq.get("externalId", ""),
                "description": sq.get("description", ""),
                "component": meta.get("component_id", ""),
                "severity": meta.get("severity", "non-grounding"),
                "status": meta.get("status", "open"),
                "dateIdentified": meta.get("date", ""),
                "tail": meta.get("tail", tail),
                "metadata": meta,
            })
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/maintenance/upcoming")
async def get_upcoming_maintenance(aircraft: Optional[str] = Query(default=None)) -> list[dict[str, Any]]:
    """GET /api/maintenance/upcoming?aircraft=N287WN"""
    tail = _require_tail(aircraft)
    try:
        ctx = await asyncio.to_thread(assemble_aircraft_context, tail)
        if "error" in ctx:
            raise HTTPException(status_code=503, detail=ctx["error"])
        return ctx.get("upcomingMaintenance", [])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/maintenance/history")
async def get_maintenance_history(
    aircraft: Optional[str] = Query(default=None),
    page: int = 1,
    per_page: int = 25,
    component: Optional[str] = None,
    year: Optional[int] = None,
    maint_type: Optional[str] = None,
) -> dict[str, Any]:
    """GET /api/maintenance/history?aircraft=N287WN — paginated maintenance records.

    Response includes ``available_years``: calendar years present after component/type
    filters (before ``year``), for populating the year filter UI.
    """
    tail = _require_tail(aircraft)
    try:
        ctx = await asyncio.to_thread(assemble_aircraft_context, tail)
        if "error" in ctx:
            raise HTTPException(status_code=503, detail=ctx["error"])

        records = ctx.get("allMaintenance", []) + ctx.get("allInspections", [])
        records_sorted = sorted(records, key=lambda x: x.get("startTime") or 0, reverse=True)

        if component:
            comp_lower = component.lower()
            records_sorted = [
                r for r in records_sorted
                if comp_lower in (r.get("metadata", {}).get("component_id", "") or "").lower()
            ]
        if year:
            records_sorted = [r for r in records_sorted if _record_year(r) == year]
        if maint_type:
            mt_lower = maint_type.lower()
            records_sorted = [
                r for r in records_sorted
                if mt_lower in (r.get("subtype") or "").lower()
                or mt_lower in (r.get("metadata", {}).get("maintenance_type", "") or "").lower()
            ]

        years_seen: set[int] = set()
        for r in records_sorted:
            y = _record_year(r)
            if y is not None:
                years_seen.add(y)
        available_years = sorted(years_seen, reverse=True)

        if year:
            records_sorted = [r for r in records_sorted if _record_year(r) == year]

        total = len(records_sorted)
        total_pages = max(1, (total + per_page - 1) // per_page)
        start = (page - 1) * per_page

        return {
            "records": records_sorted[start:start + per_page],
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "available_years": available_years,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _record_year(record: dict[str, Any]) -> Optional[int]:
    date_str = record.get("metadata", {}).get("date", "")
    if date_str:
        try:
            return int(date_str[:4])
        except (ValueError, TypeError):
            pass
    return None


_FLIGHT_SORT_FIELDS = frozenset({
    "timestamp",
    "duration",
    "route",
    "egt_deviation",
    "n1_vibration",
    "oil_temp_max",
    "oil_pressure_min",
    "oil_pressure_max",
    "fuel_flow_kgh",
})


@app.get("/api/flights")
async def get_flights(
    aircraft: Optional[str] = Query(default=None),
    page: int = 1,
    per_page: int = 25,
    route: Optional[str] = None,
    year: Optional[int] = None,
    sort: str = Query(default="timestamp"),
    order: str = Query(default="desc"),
) -> dict[str, Any]:
    """GET /api/flights?aircraft=N287WN — paginated flight records."""
    tail = _require_tail(aircraft)
    try:
        return await asyncio.to_thread(_sync_get_flights, tail, page, per_page, route, year, sort, order)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _sync_get_flights(
    tail: str,
    page: int,
    per_page: int,
    route: Optional[str],
    year: Optional[int],
    sort: str,
    order: str,
) -> dict[str, Any]:
    from mock_cdf.store.store import store as cdf_store  # type: ignore[import]

    # Flight events have all the per-flight data we need
    all_events = cdf_store.get_events()
    flight_events = [
        e for e in all_events
        if e.type == "Flight" and (e.metadata or {}).get("tail") == tail
    ]

    flights: list[dict[str, Any]] = []
    for e in flight_events:
        meta = e.metadata or {}
        ts_ms = e.startTime or 0
        ts_iso = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat() if ts_ms else ""
        flight_year = int(ts_iso[:4]) if ts_iso else 0

        try:
            hobbs_start = float(meta.get("hobbs_start", 0))
            hobbs_end = float(meta.get("hobbs_end", 0))
        except (ValueError, TypeError):
            hobbs_start = hobbs_end = 0.0

        try:
            duration = float(meta.get("duration", 0))
        except (ValueError, TypeError):
            duration = round(hobbs_end - hobbs_start, 2)

        def _f(key: str) -> Optional[float]:
            v = meta.get(key)
            if v and v != "nan":
                try:
                    return float(v)
                except (ValueError, TypeError):
                    pass
            return None

        def _f_optional(key: str) -> Optional[float]:
            """Float from metadata when present; None if missing (e.g. tach before re-ingest)."""
            v = meta.get(key)
            if v is None or v == "" or v == "nan":
                return None
            try:
                return float(v)
            except (ValueError, TypeError):
                return None

        op_min = _f("oil_pressure_min")
        op_max = _f("oil_pressure_max")
        if op_min is not None and op_max is not None and op_min > op_max:
            op_min, op_max = op_max, op_min

        flights.append({
            "timestamp": ts_iso,
            "hobbs_start": hobbs_start,
            "hobbs_end": hobbs_end,
            "tach_start": _f_optional("tach_start"),
            "tach_end": _f_optional("tach_end"),
            "duration": duration,
            "route": meta.get("route", ""),
            "egt_deviation": _f("egt_deviation"),
            "n1_vibration": _f("n1_vibration"),
            "n2_speed": _f("n2_speed"),
            "oil_pressure_min": op_min,
            "oil_pressure_max": op_max,
            "oil_temp_max": _f("oil_temp_max"),
            "fuel_flow_kgh": _f("fuel_flow_kgh"),
            "pilot_notes": meta.get("pilot_notes", ""),
            "anomalous": meta.get("anomalous", "") == "true",
            "year": flight_year,
        })

    # Apply filters
    filtered = flights
    if year:
        filtered = [f for f in filtered if f["year"] == year]
    if route:
        route_lower = route.lower()
        filtered = [f for f in filtered if route_lower in (f.get("route") or "").lower()]

    sort_key = sort if sort in _FLIGHT_SORT_FIELDS else "timestamp"
    descending = (order or "desc").lower() != "asc"

    def _flight_sort_tuple(f: dict[str, Any]) -> tuple[Any, ...]:
        """Primary sort plus timestamp tie-breaker (ISO strings sort chronologically)."""
        ts = f.get("timestamp") or ""
        if sort_key == "timestamp":
            return (ts,)
        if sort_key == "route":
            return ((f.get("route") or "").lower(), ts)
        v = f.get(sort_key)
        if v is None:
            num = float("-inf") if descending else float("inf")
        else:
            try:
                num = float(v)
            except (TypeError, ValueError):
                num = float("-inf") if descending else float("inf")
        return (num, ts)

    filtered.sort(key=_flight_sort_tuple, reverse=descending)

    total = len(filtered)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page

    return {
        "records": filtered[start:start + per_page],
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    }


@app.get("/api/components")
async def get_components(aircraft: Optional[str] = Query(default=None)) -> list[dict[str, Any]]:
    """GET /api/components?aircraft=N287WN — asset hierarchy with maintenance status."""
    tail = _require_tail(aircraft)
    try:
        return await asyncio.to_thread(_sync_get_components, tail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _sync_get_components(tail: str) -> list[dict[str, Any]]:
    from mock_cdf.store.store import store as cdf_store  # type: ignore[import]

    all_assets = cdf_store.get_assets()
    tail_assets = [
        a for a in all_assets
        if a.externalId == tail
        or (a.externalId or "").startswith(f"{tail}-")
    ]

    all_events = cdf_store.get_events()

    maint_by_asset: dict[int, list[Any]] = {}
    for event in all_events:
        if event.type in ("MaintenanceRecord", "Inspection"):
            for aid in event.assetIds or []:
                maint_by_asset.setdefault(aid, []).append(event)

    current_hobbs = current_hobbs_from_cdf_store(cdf_store, tail)
    current_tach = current_tach_from_cdf_store(cdf_store, tail)

    result: list[dict[str, Any]] = []

    for asset in sorted(tail_assets, key=lambda a: a.externalId or ""):
        ext_id = asset.externalId or ""
        raw_records = maint_by_asset.get(asset.id, [])
        maint_records = [
            e for e in raw_records
            if (e.metadata or {}).get("component_id", "") == ext_id
        ]
        maint_records = sorted(maint_records, key=lambda e: e.startTime or 0, reverse=True)

        last_maint_date: Optional[str] = None
        next_due_tach: Optional[float] = None
        next_due_date: Optional[str] = None
        oil_next_due_tach: Optional[float] = None
        oil_next_due_date: Optional[str] = None

        if maint_records:
            last_maint_date = (maint_records[0].metadata or {}).get("date")

        is_engine = ext_id == f"{tail}-ENGINE-1"
        is_root = ext_id == tail

        if is_engine:
            oil_recs = [
                e for e in maint_records
                if e.type == "MaintenanceRecord"
                and "oil_change" in (e.subtype or "").lower()
            ]
            if oil_recs:
                om = oil_recs[0].metadata or {}
                oil_next_due_tach = next_due_tach_from_meta(om)
                oil_next_due_date = (om.get("next_due_date") or "").strip() or None
                next_due_tach = oil_next_due_tach
                next_due_date = oil_next_due_date
                # IT rows often omit next_due_date; calendar leg still applies (policy months from sign-off).
                if not oil_next_due_date:
                    svc = str(om.get("date", "") or "").strip()
                    if svc:
                        try:
                            oil_next_due_date = _date_after_calendar_months(
                                svc, _oil_change_calendar_months_from_policy()
                            )
                            next_due_date = oil_next_due_date
                        except ValueError:
                            pass

        if is_root:
            # For 737: look for a_check (equivalent to annual) on the root asset
            annual_recs = [
                e for e in maint_records
                if (e.subtype or "").lower() in ("annual", "a_check")
            ]
            if annual_recs:
                am = annual_recs[0].metadata or {}
                next_due_date = (am.get("next_due_date") or "").strip() or None
                next_due_tach = None

        status = "ok"
        hours_until_tach: Optional[float] = None

        if is_engine and next_due_tach is not None and current_tach > 0:
            hours_until_tach = round(next_due_tach - current_tach, 1)
            if hours_until_tach < 0:
                status = "overdue"
            elif hours_until_tach <= 10:
                status = "due_soon"
            if oil_next_due_date:
                days_remaining = calendar_days_until_iso(oil_next_due_date)
                if days_remaining is not None:
                    if days_remaining < 0 and hours_until_tach is not None and hours_until_tach > 0:
                        pass
                    elif days_remaining < 0:
                        status = "overdue"
                    elif days_remaining <= 30 and status == "ok":
                        status = "due_soon"

        if is_root and next_due_date:
            days_remaining = calendar_days_until_iso(next_due_date)
            if days_remaining is not None:
                if days_remaining < 0:
                    status = "overdue"
                elif days_remaining <= 30 and status == "ok":
                    status = "due_soon"

        result.append({
            "externalId": ext_id,
            "name": asset.name,
            "description": asset.description,
            "parentExternalId": asset.parentExternalId,
            "metadata": asset.metadata or {},
            "lastMaintenanceDate": last_maint_date,
            "nextDueTach": next_due_tach,
            "nextDueHobbs": next_due_tach,
            "nextDueDate": next_due_date,
            "currentHobbs": current_hobbs,
            "currentTach": current_tach,
            "hoursUntilDue": hours_until_tach,
            "status": status,
            "maintenanceCount": len(maint_records),
        })

    return result


# ---------------------------------------------------------------------------
# Policies
# ---------------------------------------------------------------------------

@app.get("/api/policies")
async def get_policies() -> list[dict[str, Any]]:
    """GET /api/policies — list all fleet operational policies."""
    try:
        base_url = os.getenv("CDF_BASE_URL", "http://localhost:4001")
        project = os.getenv("CDF_PROJECT", "southwest_airlines")
        async with httpx.AsyncClient(timeout=5.0) as http:
            resp = await http.post(
                f"{base_url}/api/v1/projects/{project}/policies/list",
                json={},
            )
            resp.raise_for_status()
            return resp.json().get("items", [])
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))


# ---------------------------------------------------------------------------
# Knowledge graph
# ---------------------------------------------------------------------------

@app.get("/api/graph")
async def get_graph_data() -> dict[str, Any]:
    """GET /api/graph — full knowledge graph for visualization."""
    try:
        return await asyncio.to_thread(_sync_get_graph_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Node type color groups for the frontend
_NODE_COLORS = {
    "asset": 1,
    "timeseries": 2,
    "event": 3,
    "file": 4,
}

# Relationship type colors — tuned for the light canvas background. Each edge
# is one shade LIGHTER (Tailwind -400) than the matching node type (Tailwind
# -500) so edges visually recede behind nodes and the overall graph stays
# readable instead of turning into a dark web. Hues match the node palette so
# a HAS_TIMESERIES arc reads as the same color family as the TimeSeries node
# it points to. LINKED_TO bridges doc↔asset with no single owner, so it uses
# a near-invisible slate neutral to avoid clutter on the light background.
_EDGE_COLORS = {
    "HAS_COMPONENT":  "#60a5fa",              # blue-400    — matches asset nodes
    "GOVERNED_BY":    "#a5b4fc",              # indigo-300  — many edges route through fleet-owner node, keep light
    "HAS_POLICY":     "#c084fc",              # purple-400  — matches file nodes (policies are files)
    "HAS_TIMESERIES": "#4ade80",              # green-400   — matches timeseries nodes
    "IS_TYPE":        "#60a5fa",              # blue-400    — structural (engine model)
    "PERFORMED_ON":   "#fb923c",              # orange-400  — matches event nodes
    "IDENTIFIED_ON":  "#fb923c",              # orange-400  — matches event nodes
    "REFERENCES_AD":  "#c084fc",              # purple-400  — matches file nodes
    # LINKED_TO carries the fleet-wide doc↔aircraft traffic; many edges stack
    # through the middle. Low-alpha so cumulative ink stays light, but visible
    # enough to trace individual connections when zoomed in.
    "LINKED_TO":      "rgba(148,163,184,0.3)",
}


def _sync_get_graph_data() -> dict[str, Any]:
    from mock_cdf.store.store import store as cdf_store  # type: ignore[import]

    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()
    seen_links: set[tuple[str, str, str]] = set()

    def _add_node(node_id: str, label: str, node_type: str, meta: dict[str, Any] | None = None) -> None:
        if node_id not in seen_nodes:
            seen_nodes.add(node_id)
            nodes.append({
                "id": node_id,
                "label": label,
                "type": node_type,
                "group": _NODE_COLORS.get(node_type, 1),
                "metadata": meta or {},
            })

    def _add_link(src: str, tgt: str, rel_type: str) -> None:
        key = (src, tgt, rel_type)
        if key not in seen_links and src in seen_nodes and tgt in seen_nodes:
            seen_links.add(key)
            links.append({
                "source": src,
                "target": tgt,
                "type": rel_type,
                "color": _EDGE_COLORS.get(rel_type, "#666"),
            })

    # Assets (all rendered as "asset", including the engine model node)
    for asset in cdf_store.get_assets():
        node_id = asset.externalId or str(asset.id)
        meta = asset.metadata or {}
        _add_node(node_id, asset.name or node_id, "asset", meta)

    # TimeSeries
    for ts in cdf_store.get_timeseries():
        node_id = ts.externalId or str(ts.id)
        _add_node(node_id, ts.name or node_id, "timeseries", {"unit": ts.unit or ""})

    for pol in cdf_store.get_policies():
        _add_node(pol.externalId, pol.title, "file", {"category": pol.category})

    # Files
    for f in cdf_store.get_files():
        node_id = f.externalId or str(f.id)
        _add_node(node_id, f.name or node_id, "file")

    # Maintenance / squawk / inspection events that participate in REFERENCES_AD or PERFORMED_ON
    graph_event_external_ids: set[str] = set()
    for rel in cdf_store.get_relationships():
        if rel.relationshipType in ("REFERENCES_AD", "PERFORMED_ON") and rel.sourceType == "event":
            graph_event_external_ids.add(rel.sourceExternalId)

    for ev in cdf_store.get_events():
        if ev.externalId not in graph_event_external_ids:
            continue
        if ev.type == "Flight":
            continue
        sub = (ev.subtype or ev.type or "event").strip()
        desc = (ev.description or "").strip()
        body = desc[:40] + ("…" if len(desc) > 40 else "")
        label = f"{sub} {body}".strip()[:60]
        if not label:
            label = ev.externalId
        _add_node(
            ev.externalId,
            label,
            "event",
            {"eventType": ev.type or "", "subtype": sub, "tail": (ev.metadata or {}).get("tail", "")},
        )

    # Relationships → links
    for rel in cdf_store.get_relationships():
        src = rel.sourceExternalId
        tgt = rel.targetExternalId
        if src and tgt and src in seen_nodes and tgt in seen_nodes:
            _add_link(src, tgt, rel.relationshipType or "RELATED_TO")

    # Asset parent→child links from parentExternalId field
    for asset in cdf_store.get_assets():
        if asset.parentExternalId:
            _add_link(asset.parentExternalId, asset.externalId or str(asset.id), "HAS_COMPONENT")

    # TS → asset links
    for ts in cdf_store.get_timeseries():
        node_id = ts.externalId or str(ts.id)
        if ts.assetId:
            for asset in cdf_store.get_assets():
                if asset.id == ts.assetId:
                    _add_link(asset.externalId or str(asset.id), node_id, "HAS_TIMESERIES")
                    break

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


# ---------------------------------------------------------------------------
# Time Series
# ---------------------------------------------------------------------------

_METRIC_TO_TS_SUFFIX: dict[str, str] = {
    "egt_deviation":    "engine.egt_deviation",
    "n1_vibration":     "engine.n1_vibration",
    "n2_speed":         "engine.n2_speed",
    "fuel_flow":        "engine.fuel_flow",
    "oil_pressure_min": "engine.oil_pressure_min",
    "oil_pressure_max": "engine.oil_pressure_max",
    "oil_temp":         "engine.oil_temp_max",
    "hobbs":            "aircraft.hobbs",
}

_METRIC_UNITS: dict[str, str] = {
    "egt_deviation": "°C", "n1_vibration": "units", "n2_speed": "%",
    "fuel_flow": "kg/hr", "oil_pressure_min": "psi", "oil_pressure_max": "psi",
    "oil_temp": "°C", "hobbs": "AFH",
}

_METRIC_CAUTION: dict[str, Optional[float]] = {
    "egt_deviation": 10.0, "n1_vibration": 1.8, "n2_speed": None,
    "fuel_flow": None, "oil_pressure_min": 40.0, "oil_pressure_max": None,
    "oil_temp": 102.0, "hobbs": None,
}

_METRIC_CRITICAL: dict[str, Optional[float]] = {
    "egt_deviation": 18.0, "n1_vibration": 2.8, "n2_speed": None,
    "fuel_flow": None, "oil_pressure_min": 30.0, "oil_pressure_max": None,
    "oil_temp": 110.0, "hobbs": None,
}


@app.get("/api/timeseries")
async def get_timeseries(
    aircraft: Optional[str] = Query(default=None),
    metric: str = Query(default="egt_deviation"),
    limit: int = Query(default=30),
) -> dict[str, Any]:
    """GET /api/timeseries?aircraft=N287WN&metric=egt_deviation&limit=30"""
    tail = _require_tail(aircraft)
    ts_suffix = _METRIC_TO_TS_SUFFIX.get(metric, f"engine.{metric}")
    ts_ext_id = f"{tail}.{ts_suffix}"

    try:
        return await asyncio.to_thread(_sync_get_timeseries, tail, ts_ext_id, metric, limit)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _sync_get_timeseries(tail: str, ts_ext_id: str, metric: str, limit: int) -> dict[str, Any]:
    from mock_cdf.store.store import store as cdf_store  # type: ignore[import]

    datapoints = cdf_store.get_datapoints(ts_ext_id)
    if not datapoints:
        return {
            "aircraft": tail, "metric": metric,
            "unit": _METRIC_UNITS.get(metric, ""),
            "caution_threshold": _METRIC_CAUTION.get(metric),
            "critical_threshold": _METRIC_CRITICAL.get(metric),
            "datapoints": [],
        }

    # Sort by timestamp and take the last `limit` points
    sorted_pts = sorted(datapoints, key=lambda d: d.timestamp)
    recent = sorted_pts[-limit:]
    result_pts = [
        {"timestamp": d.timestamp, "value": d.value, "flight_index": i}
        for i, d in enumerate(recent)
    ]
    return {
        "aircraft": tail, "metric": metric,
        "unit": _METRIC_UNITS.get(metric, ""),
        "caution_threshold": _METRIC_CAUTION.get(metric),
        "critical_threshold": _METRIC_CRITICAL.get(metric),
        "datapoints": result_pts,
    }


# ---------------------------------------------------------------------------
# Agentic Insights
# ---------------------------------------------------------------------------

_insights_cache: dict[str, Any] = {"insights": [], "generated_at": None, "is_fallback": False}
_insights_refresh_in_progress: bool = False


_TAIL_RE = re.compile(r"\bN\d{3,4}[A-Z]{1,2}\b")


def _extract_aircraft_mentioned(text: str) -> list[str]:
    """Pull tail numbers out of the LLM response so the UI can badge them."""
    found = _TAIL_RE.findall(text)
    seen: list[str] = []
    for t in found:
        if t not in seen:
            seen.append(t)
        if len(seen) >= 6:
            break
    return seen


def _strip_markdown(text: str) -> str:
    """Remove bold/italic tokens and headers so the card text renders cleanly."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\1", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    return text.strip()


# One consolidated prompt produces all four insight sections as structured JSON.
# Running a single agent conversation avoids the rate-limit and inconsistency
# issues we hit when firing four parallel agent tool-use loops.
_INSIGHTS_COMBINED_PROMPT = """You are generating a four-section fleet-intelligence brief for Southwest Airlines' 737 fleet.

Do this in order:
1. Call get_fleet_failure_history() once. This tells you which aircraft have already failed and gives you each one's pre-failure sensor snapshot (EGT deviation, N1 vibration, oil temp max, oil pressure min).
2. Call assemble_fleet_context() once. This returns airworthiness, open-squawk counts, engine sensor trends, and upcoming-maintenance data for every aircraft.
3. Using the data from steps 1 and 2, compose exactly these four sections.

Sections (keep each body to 2–4 short sentences of plain prose, no markdown formatting, no line breaks beyond sentence separation):

- safety: Which aircraft are grounded or flying with restrictions? For each, name the tail and the driving squawk in one sentence.
- pattern: Which currently-flying instrumented aircraft have sensor trends that overlap a grounded peer's pre-failure envelope? Name the flying tail AND the grounded peer tail, and cite the specific overlapping sensor values (e.g. "N246WN EGT +20.1C overlaps N287WN's pre-failure +19.6C"). If no overlap exists, say so in one sentence.
- maintenance: List every maintenance item coming due within the next 30 calendar days across the fleet (oil changes, A-checks, annual inspections, borescope inspections, AD compliance). Group by tail. If nothing is due, say "No maintenance items due in the next 30 days."
- compliance: Notable open squawks fleet-wide — safety-relevant items, anything exceeding typical MEL deferral windows, recurring issue types across multiple aircraft.

Output format — return ONLY this JSON object (no surrounding prose, no markdown code fences, no commentary):

{
  "safety":      {"title": "<=60 char title", "severity": "critical", "body": "plain prose"},
  "pattern":     {"title": "...",             "severity": "warning",  "body": "..."},
  "maintenance": {"title": "...",             "severity": "warning",  "body": "..."},
  "compliance":  {"title": "...",             "severity": "info",     "body": "..."}
}

Rules:
- Do NOT use markdown bold (**) or italic (*) in titles or bodies.
- Do NOT cite operator policies as the justification for risk — cite the actual aircraft data and peer comparisons.
- Always name specific tail numbers. Never output placeholders like "the aircraft"."""


_INSIGHT_CATEGORY_ORDER = ("safety", "pattern", "maintenance", "compliance")
_INSIGHT_DEFAULT_SEVERITY = {"safety": "critical", "pattern": "warning", "maintenance": "warning", "compliance": "info"}

_MAINT_URGENT_KEYWORDS = (
    "overdue", "past due", "past-due", "expired",
    "immediate", "urgent", "out of compliance", "non-compliant", "noncompliance",
)


def _derive_severity(category: str, body: str, llm_choice: str) -> str:
    """Adjust LLM-chosen severity when the content contradicts it.

    The consolidated insights prompt hardcodes default severities in its JSON
    example and the LLM often copies those literally (e.g. "warning" for
    maintenance even when nothing is actually urgent). This override targets
    only the maintenance category — safety/pattern/compliance severities are
    left to the LLM since it picks those accurately from context.
    """
    if category == "maintenance":
        body_l = body.lower()
        if any(k in body_l for k in _MAINT_URGENT_KEYWORDS):
            return "warning"
        return "info"
    if llm_choice in ("critical", "warning", "info"):
        return llm_choice
    return _INSIGHT_DEFAULT_SEVERITY.get(category, "info")


def _parse_insights_json(full_text: str) -> list[dict[str, Any]]:
    """Extract the JSON object from the agent's final response and build insight records."""
    if not full_text:
        return []
    t = full_text.strip()
    # Strip code fences if the model included them
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t[3:]
        if t.endswith("```"):
            t = t[: t.rfind("```")]
    start = t.find("{")
    end = t.rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        parsed = json.loads(t[start : end + 1])
    except Exception:
        return []
    insights: list[dict[str, Any]] = []
    for i, key in enumerate(_INSIGHT_CATEGORY_ORDER):
        entry = parsed.get(key)
        if not isinstance(entry, dict):
            continue
        title = _strip_markdown(str(entry.get("title", "")).strip()) or key.title()
        body = _strip_markdown(str(entry.get("body", "")).strip())
        if not body:
            continue
        llm_sev = str(entry.get("severity", "")).strip().lower()
        severity = _derive_severity(key, body, llm_sev)
        insights.append({
            "id": f"ai-{i + 1}",
            "title": title[:100],
            "summary": body[:600],
            "severity": severity,
            "aircraft": _extract_aircraft_mentioned(title + " " + body),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "reasoning": body,
            "category": key,
        })
    return insights


async def _refresh_insights_background() -> None:
    """Run one agent conversation that produces all four insight sections as JSON."""
    global _insights_cache, _insights_refresh_in_progress
    if _insights_refresh_in_progress:
        return
    _insights_refresh_in_progress = True
    try:
        from .agent.agent import run_agent_streaming  # noqa: E402
        full_text = ""
        try:
            async for step in run_agent_streaming(_INSIGHTS_COMBINED_PROMPT, max_iterations=25):
                if step.get("type") == "final":
                    full_text = step.get("content", "")
        except Exception:
            full_text = ""

        insights = _parse_insights_json(full_text)
        _insights_cache = {
            "insights": insights,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "is_fallback": len(insights) == 0,
        }
    finally:
        _insights_refresh_in_progress = False


def _extract_insight_title(text: str) -> str:
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    for line in lines[:3]:
        clean = line.lstrip("#").strip()
        if 10 < len(clean) < 80:
            return clean
    return lines[0][:80] if lines else "Fleet Insight"


def _extract_insight_summary(text: str) -> str:
    lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
    body = [l for l in lines if not l.startswith("#")]
    return " ".join(body[:3])[:400] if body else text[:400]


@app.get("/api/insights")
async def get_insights() -> dict[str, Any]:
    """GET /api/insights — pre-computed AI fleet intelligence."""
    return _insights_cache


@app.post("/api/insights/refresh")
async def refresh_insights(force: bool = Query(default=False)) -> dict[str, Any]:
    """POST /api/insights/refresh — re-run AI insight generation.

    Cache-aware: if insights are already populated (and not a fallback), skip the LLM
    and return "already_cached". Use ?force=true to regenerate unconditionally.
    """
    if not force and _insights_cache.get("insights") and not _insights_cache.get("is_fallback"):
        return {"status": "already_cached"}
    if _insights_refresh_in_progress:
        return {"status": "already_running"}
    task = asyncio.create_task(_refresh_insights_background())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"status": "refresh_started"}


# ---------------------------------------------------------------------------
# Predictive Maintenance
# ---------------------------------------------------------------------------

_predictive_cache: dict[str, Any] = {}
_predictive_refresh_in_progress: set[str] = set()


_RISK_LEVEL_SCORES = {"low": 20, "moderate": 45, "high": 74, "critical": 88}


def _parse_risk_from_text(text: str) -> tuple[int, str]:
    """Read risk_level / risk_score explicitly from the LLM's structured output.

    Never returns "failed" — that level is reserved for already-grounded aircraft
    and is assigned by the short-circuit in _compute_predictive_risk, not by text.
    """
    m = re.search(r"risk[_\s]*level\s*[:=]\s*[\"']?(low|moderate|high|critical)", text, re.IGNORECASE)
    if m:
        level = m.group(1).lower()
        return _RISK_LEVEL_SCORES[level], level
    ms = re.search(r"risk[_\s]*score\s*[:=]\s*(\d+)", text, re.IGNORECASE)
    if ms:
        score = max(0, min(100, int(ms.group(1))))
        if score >= 85:
            level = "critical"
        elif score >= 65:
            level = "high"
        elif score >= 35:
            level = "moderate"
        else:
            level = "low"
        return score, level
    # Loose fallback — look for level words; ignore peer-failure mentions.
    lower = text.lower()
    if "critical" in lower:
        return 82, "critical"
    if "high risk" in lower or "high-risk" in lower:
        return 74, "high"
    if "moderate" in lower:
        return 45, "moderate"
    return 25, "low"


def _parse_field(text: str, *keys: str, max_len: int = 180) -> str:
    """Extract a structured field from the LLM response (e.g. primary_driver: ...)."""
    for key in keys:
        pattern = rf"{re.escape(key)}\s*[:=]\s*[\"']?([^\"'\n]+?)(?:\"|'|$|\n)"
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val = m.group(1).strip().rstrip(".,;")
            if val:
                return _strip_markdown(val)[:max_len]
    return ""


def _summarize_agent_reasoning(text: str, max_len: int = 700) -> str:
    """Produce a clean, human-readable reasoning summary.

    Strips markdown syntax, drops structured-field echo lines (risk_score:, etc.)
    so what's left is actual prose the agent wrote.
    """
    text = _strip_markdown(text)
    lines: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if re.match(r"^(risk[_\s]*score|risk[_\s]*level|primary[_\s]*driver|recommended[_\s]*action|confidence)\s*[:=]", line, re.IGNORECASE):
            continue
        lines.append(line)
    out = " ".join(lines)
    return out[:max_len].rstrip()


def _format_sensor(value: Any) -> str:
    return f"{value:.1f}" if isinstance(value, (int, float)) else "N/A"


def _format_peer_failures(peer_failures: list[dict[str, Any]]) -> str:
    if not peer_failures:
        return "- (No peer aircraft have failed)"
    lines = []
    for p in peer_failures:
        pfs = p.get("pre_failure_sensors") or {}
        lines.append(
            f"- {p.get('tail', '?')} (grounded {p.get('grounded_on', '?')}): "
            f"EGT {pfs.get('egt_deviation', 'N/A')}°C, "
            f"N1 vib {pfs.get('n1_vibration', 'N/A')} units, "
            f"oil temp {pfs.get('oil_temp_max', 'N/A')}°C, "
            f"oil pressure min {pfs.get('oil_pressure_min', 'N/A')} psi. "
            f"Cause: {(p.get('primary_cause') or '')[:140]}"
        )
    return "\n".join(lines)


async def _compute_predictive_risk(tail: str) -> dict[str, Any]:
    """Compute AI risk score for one instrumented aircraft.

    All context is pre-computed in Python and handed to Claude in a single prompt so the
    agent does not need to call any tools. This avoids the tool-use iteration exhaustion
    we saw when the ReAct loop was responsible for data gathering.
    """
    try:
        from .agent.context import assemble_aircraft_context  # noqa: E402
        ctx = assemble_aircraft_context(tail)
    except Exception:
        result = _insufficient_data(tail)
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        return result

    # Short-circuit grounded aircraft — no LLM call.
    grounding = ctx.get("groundingSquawks") or []
    if grounding:
        sq = grounding[0]
        cause = (sq.get("description") or "engine failure").strip()
        return {
            "aircraft": tail,
            "status": "scored",
            "risk_score": 100,
            "risk_level": "failed",
            "primary_driver": cause[:140] if cause else "Engine failure — aircraft grounded",
            "reasoning": (
                f"{tail} is currently grounded with an open grounding squawk. "
                "Predictive risk scoring is not applicable — the failure has already occurred."
            ),
            "recommended_action": "Resolve grounding squawk; engine replacement before return to service.",
            "confidence": "high",
            "data_points_analyzed": 0,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    sensors = ctx.get("sensors") or {}
    peer_failures = ctx.get("peerFailures") or []

    current_text = (
        f"- EGT deviation: {_format_sensor(sensors.get('engine.egt_deviation', {}).get('value'))} °C "
        "(normal 0–10, caution 10–15, warning >15)\n"
        f"- N1 vibration: {_format_sensor(sensors.get('engine.n1_vibration', {}).get('value'))} units "
        "(normal ≤1.8, caution 1.8–2.5, warning >2.5)\n"
        f"- Oil temp max: {_format_sensor(sensors.get('engine.oil_temp_max', {}).get('value'))} °C "
        "(normal ≤100, caution >102)\n"
        f"- Oil pressure min: {_format_sensor(sensors.get('engine.oil_pressure_min', {}).get('value'))} psi "
        "(normal 40–80, caution low <40)"
    )

    prompt = f"""Assess predictive engine-failure risk for Southwest Airlines aircraft {tail}. This aircraft is currently flying — not grounded. ALL data you need is provided below. DO NOT call any tools. Respond directly with the JSON.

Current engine sensor readings for {tail}:
{current_text}

Peer aircraft in the fleet that have already suffered engine failures (CFM56-7B peers):
{_format_peer_failures(peer_failures)}

Assessment guidance:
- If any current reading overlaps a peer's pre-failure envelope, that is strong evidence of elevated risk — cite the peer by tail.
- If any reading is in the warning range, risk is at least high.
- If any reading is in the caution range, risk is at least moderate.
- If all readings are normal and no peer overlap exists, risk is low.
- Justify conclusions with concrete sensor comparisons — NOT operator policies.

Return ONLY this JSON object (no prose around it, no markdown code fences):
{{
  "risk_level": "low" | "moderate" | "high" | "critical",
  "risk_score": <integer 0-100>,
  "primary_driver": "<short phrase naming the driving sensor and peer aircraft if applicable>",
  "recommended_action": "<one sentence>",
  "confidence": "low" | "moderate" | "high",
  "reasoning": "<2–3 plain-prose sentences citing specific sensor values and peer-aircraft comparisons. Plain text only, no markdown.>"
}}"""

    full_text = ""
    try:
        from .agent.agent import call_claude_direct  # noqa: E402
        # Direct API call with no tools — guaranteed single-shot, no iteration
        # budget to exhaust on unexpected tool calls.
        full_text = await call_claude_direct(prompt, max_tokens=1024)
    except Exception:
        full_text = ""

    if full_text:
        parsed: dict[str, Any] = {}
        try:
            t = full_text.strip()
            if t.startswith("```"):
                t = t.split("\n", 1)[1] if "\n" in t else t[3:]
                if t.endswith("```"):
                    t = t[: t.rfind("```")]
            start = t.find("{")
            end = t.rfind("}")
            if start >= 0 and end > start:
                parsed = json.loads(t[start : end + 1])
        except Exception:
            parsed = {}

        level = str(parsed.get("risk_level", "")).strip().lower()
        if level in _RISK_LEVEL_SCORES:
            score_val = parsed.get("risk_score")
            try:
                score = int(score_val) if score_val is not None else _RISK_LEVEL_SCORES[level]
            except Exception:
                score = _RISK_LEVEL_SCORES[level]
            score = max(0, min(100, score))
        else:
            score, level = _parse_risk_from_text(full_text)

        primary_driver = (
            _strip_markdown(str(parsed.get("primary_driver", "")).strip())
            or _parse_field(full_text, "primary_driver", "primary driver")
            or "Engine sensor trend"
        )
        recommended = (
            _strip_markdown(str(parsed.get("recommended_action", "")).strip())
            or _parse_field(full_text, "recommended_action", "recommended action")
            or "Continue enhanced ACARS monitoring"
        )
        confidence = str(parsed.get("confidence", "")).strip().lower()
        if confidence not in ("low", "moderate", "high"):
            confidence = "moderate"
        reasoning_raw = str(parsed.get("reasoning", "")).strip()
        reasoning = (
            _strip_markdown(reasoning_raw)
            if reasoning_raw
            else _summarize_agent_reasoning(full_text)
        )

        return {
            "aircraft": tail,
            "status": "scored",
            "risk_score": score,
            "risk_level": level,
            "primary_driver": primary_driver[:180],
            "reasoning": reasoning[:700],
            "recommended_action": recommended[:180],
            "confidence": confidence,
            "data_points_analyzed": 30,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    result = _insufficient_data(tail)
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    return result


def _insufficient_data(tail: str) -> dict[str, Any]:
    return {
        "aircraft": tail, "status": "insufficient_data",
        "risk_score": None, "risk_level": None, "primary_driver": None,
        "reasoning": None, "recommended_action": None, "confidence": None,
        "data_points_analyzed": None, "generated_at": None,
    }


@app.get("/api/predictive")
async def get_predictive(aircraft: Optional[str] = Query(default=None)) -> dict[str, Any]:
    """GET /api/predictive?aircraft=N246WN — AI risk score for one aircraft."""
    tail = _require_tail(aircraft)
    if tail in _predictive_cache:
        return _predictive_cache[tail]
    result = _insufficient_data(tail)
    _predictive_cache[tail] = result
    return result


@app.post("/api/predictive/refresh")
async def refresh_predictive(
    aircraft: Optional[str] = Query(default=None),
    force: bool = Query(default=False),
) -> dict[str, Any]:
    """POST /api/predictive/refresh?aircraft=N246WN — recompute AI risk score.

    Cache-aware: if a score is already cached for this tail, skip. Use ?force=true to regenerate.
    """
    tail = _require_tail(aircraft)
    if tail not in INSTRUMENTED_TAILS:
        return _insufficient_data(tail)
    cached = _predictive_cache.get(tail)
    if not force and cached and cached.get("status") == "scored":
        return {"status": "already_cached", "aircraft": tail}
    if tail in _predictive_refresh_in_progress:
        return {"status": "already_running", "aircraft": tail}

    async def _run() -> None:
        _predictive_refresh_in_progress.add(tail)
        try:
            result = await _compute_predictive_risk(tail)
            _predictive_cache[tail] = result
        finally:
            _predictive_refresh_in_progress.discard(tail)

    task = asyncio.create_task(_run())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"status": "refresh_started", "aircraft": tail}


# ---------------------------------------------------------------------------
# Suggested queries
# ---------------------------------------------------------------------------

_suggestions_cache: list[dict[str, Any]] = []
_aircraft_suggestions_cache: dict[str, list[dict[str, Any]]] = {}

_FALLBACK_SUGGESTIONS = [
    {"question": "What is the current fleet health status?", "context": None},
    {"question": "Which aircraft need immediate attention?", "context": None},
    {"question": "Any upcoming scheduled inspections this month?", "context": None},
    {"question": "Are there any active safety concerns fleet-wide?", "context": None},
    {"question": "What maintenance actions are most urgent?", "context": None},
]

_AIRCRAFT_FALLBACK_SUGGESTIONS: dict[str, list[dict[str, Any]]] = {
    "N287WN": [
        {"question": "Why is N287WN grounded?", "context": "N287WN"},
        {"question": "What repairs are needed to return to service?", "context": "N287WN"},
        {"question": "What caused the engine failure?", "context": "N287WN"},
        {"question": "What open squawks does N287WN have?", "context": "N287WN"},
    ],
    "N246WN": [
        {"question": "Show EGT deviation trend for N246WN.", "context": "N246WN"},
        {"question": "Does N246WN match N287WN's pre-failure pattern?", "context": "N246WN"},
        {"question": "What is N246WN's current risk level?", "context": "N246WN"},
        {"question": "What action is recommended for N246WN?", "context": "N246WN"},
    ],
}


async def _refresh_suggestions_background() -> None:
    """Generate contextual fleet query suggestions from the LLM (single-shot, no tools)."""
    global _suggestions_cache
    try:
        from .agent.agent import call_claude_direct  # noqa: E402

        prompt = (
            "Generate 5 distinct short questions (each under 12 words) that a Southwest Airlines "
            "maintenance engineer or fleet manager would ask an AI assistant about a 737 fleet. "
            "Topics: fleet health, grounded aircraft, degrading engine sensors, upcoming maintenance, "
            "safety concerns across aircraft. "
            "Output format: one question per line, numbered 1 through 5. No other text."
        )
        full_text = await call_claude_direct(prompt, max_tokens=512)

        if full_text:
            questions = [
                line.lstrip("0123456789.-) ").strip()
                for line in full_text.splitlines()
                if line.strip() and "?" in line and len(line.strip()) > 10
            ][:6]
            if questions:
                _suggestions_cache = [
                    {"question": q, "context": None} for q in questions
                ]
                return
    except Exception:
        pass
    _suggestions_cache = list(_FALLBACK_SUGGESTIONS)


async def _refresh_aircraft_suggestions_background(tail: str) -> None:
    """Generate per-aircraft query suggestions from the LLM (single-shot, no tools)."""
    global _aircraft_suggestions_cache
    try:
        from .agent.agent import call_claude_direct  # noqa: E402

        prompt = (
            f"Generate 4 distinct short questions (each under 12 words) that a maintenance "
            f"engineer would ask an AI assistant about Southwest Airlines aircraft {tail}. "
            f"Questions should be specific and actionable — things like checking sensor trends, "
            f"comparing to peer aircraft, open squawks, upcoming maintenance. "
            "Output format: one question per line, numbered 1 through 4. No other text."
        )
        full_text = await call_claude_direct(prompt, max_tokens=512)

        if full_text:
            questions = [
                line.lstrip("0123456789.-) ").strip()
                for line in full_text.splitlines()
                if line.strip() and "?" in line and len(line.strip()) > 10
            ][:4]
            if questions:
                _aircraft_suggestions_cache[tail] = [
                    {"question": q, "context": tail} for q in questions
                ]
                return
    except Exception:
        pass
    _aircraft_suggestions_cache[tail] = list(_AIRCRAFT_FALLBACK_SUGGESTIONS.get(tail, []))


@app.get("/api/suggestions")
async def get_suggestions(aircraft: Optional[str] = Query(None)) -> list[dict[str, Any]]:
    """GET /api/suggestions — AI-generated contextual query suggestions.

    If ?aircraft=TAIL is provided for an instrumented aircraft, returns per-aircraft suggestions.
    Otherwise returns fleet-wide suggestions.
    """
    if aircraft and aircraft in INSTRUMENTED_TAILS:
        if aircraft in _aircraft_suggestions_cache:
            return _aircraft_suggestions_cache[aircraft]
        return list(_AIRCRAFT_FALLBACK_SUGGESTIONS.get(aircraft, []))
    if _suggestions_cache:
        return _suggestions_cache
    return list(_FALLBACK_SUGGESTIONS)


@app.post("/api/suggestions/refresh")
async def refresh_suggestions_endpoint(
    aircraft: Optional[str] = Query(default=None),
    force: bool = Query(default=False),
) -> dict[str, Any]:
    """POST /api/suggestions/refresh[?aircraft=TAIL] — trigger LLM-generated suggestions.

    Cache-aware: skips when suggestions are already cached. Use ?force=true to regenerate.
    """
    if aircraft:
        if aircraft not in INSTRUMENTED_TAILS:
            return {"status": "ignored", "aircraft": aircraft}
        if not force and aircraft in _aircraft_suggestions_cache:
            return {"status": "already_cached", "aircraft": aircraft}
        task = asyncio.create_task(_refresh_aircraft_suggestions_background(aircraft))
    else:
        if not force and _suggestions_cache:
            return {"status": "already_cached"}
        task = asyncio.create_task(_refresh_suggestions_background())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"status": "refresh_started", "aircraft": aircraft}


# Keep strong references to background tasks to prevent GC
_background_tasks: set[asyncio.Task[Any]] = set()


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def on_startup() -> None:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    key_ok = bool(api_key and not api_key.startswith("sk-ant-...") and len(api_key) > 20)
    mock_cdf_ok = await _check_mock_cdf()
    fleet_ready = await _mock_cdf_fleet_ready() if mock_cdf_ok else False

    print("\n✈  Southwest Airlines Fleet CAG API — port 8080")
    print(f"   ANTHROPIC_API_KEY: {'✓ configured' if key_ok else '✗ MISSING — add ANTHROPIC_API_KEY to .env'}")
    print(f"   Mock CDF server:   {'✓ reachable' if mock_cdf_ok else '✗ not reachable'}")
    if mock_cdf_ok and not fleet_ready:
        print(
            "   ⚠ Mock /health OK but fleet assets missing — port 4001 may be another app.\n"
            "     Stop the process on 4001 and restart so `npm run mock-cdf` can bind."
        )
    print("   Fleet: N287WN (NOT_AIRWORTHY)  N246WN (CAUTION)  + 45 asset-only planes\n")
    # NOTE: LLM generation is triggered by the frontend on website launch, guarded by
    # server-side cache-skip. This avoids re-firing expensive agent loops on every
    # uvicorn --reload cycle during development.
