"""
CAG Context Assembly — Python equivalent of src/agent/context.ts.

assembleAircraftContext() builds a structured AircraftContext dict by traversing
the knowledge graph. This is the core of Context Augmented Generation (CAG):
context comes from connected graph nodes, not from vector similarity search.

The traversal order mirrors how an aviation expert would investigate the aircraft:
  1. Root asset → understand what we're looking at
  2. Component hierarchy → map all sub-systems
  3. OT sensors → current operational state
  4. IT events → maintenance history, open squawks
  5. ET documents → regulatory and engineering context
  6. Derived insights → upcoming maintenance, AD compliance
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

from cognite.client import CogniteClient, ClientConfig
from cognite.client.credentials import Token
from cognite.client.data_classes import AssetFilter, EventFilter
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

from .tools import (  # noqa: E402
    client,
    log_traversal,
    clear_traversal_log,
    get_linked_documents,
)

# Current date for countdown calculations
_NOW = datetime.now(timezone.utc)


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _days_until(date_str: str) -> Optional[int]:
    """Parse YYYY-MM-DD and return days from today."""
    if not date_str:
        return None
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return (target - _NOW).days
    except ValueError:
        return None


def get_sensor_summaries() -> dict[str, Any]:
    """
    Retrieve latest sensor readings for all aircraft time series.
    This is the OT layer — current operational state from instruments.
    """
    sensor_ids = [
        "aircraft.hobbs",
        "aircraft.tach",
        "aircraft.cycles",
        "aircraft.fuel_used",
        "engine.oil_pressure_min",
        "engine.oil_pressure_max",
        "engine.oil_temp_max",
        "engine.cht_max",
        "engine.egt_max",
    ]
    summaries: dict[str, Any] = {}
    for sid in sensor_ids:
        log_traversal(f"Sensor:latest:{sid}")
        try:
            dp = client.time_series.data.retrieve_latest(external_id=sid)
            if dp and len(dp) > 0:
                summaries[sid] = {
                    "timestamp": int(dp[0].timestamp),
                    "value": float(dp[0].value),
                }
        except Exception:
            pass
    return summaries


def get_component_events(asset_id: str, asset_db_id: int) -> dict[str, list[Any]]:
    """
    Pull all event types for a given component: maintenance, squawks, inspections.
    Returns them separated by type for easier agent consumption.
    """
    log_traversal(f"ComponentEvents:{asset_id}")
    maintenance: list[Any] = []
    squawks: list[Any] = []
    inspections: list[Any] = []

    try:
        events = client.events.list(asset_ids=[asset_db_id], limit=500)
        for e in events:
            meta = e.metadata or {}
            record = {
                "externalId": e.external_id,
                "type": e.type,
                "subtype": e.subtype,
                "description": e.description,
                "startTime": e.start_time,
                "metadata": meta,
            }
            if e.type == "MaintenanceRecord":
                maintenance.append(record)
            elif e.type == "Squawk":
                squawks.append(record)
            elif e.type == "Inspection":
                inspections.append(record)
    except Exception:
        pass

    return {
        "maintenance": sorted(maintenance, key=lambda x: x.get("startTime") or 0, reverse=True),
        "squawks": squawks,
        "inspections": sorted(inspections, key=lambda x: x.get("startTime") or 0, reverse=True),
    }


def derive_upcoming_maintenance(
    all_events: list[dict[str, Any]],
    current_hobbs: float,
    window_hours: float = 250.0,
    overdue_lookback: float = 500.0,
) -> list[dict[str, Any]]:
    """
    Find maintenance items due within the next `window_hours` hobbs hours,
    plus items that are overdue (past due within `overdue_lookback` hours).
    Derived from next_due_hobbs metadata on event records — the most recent
    record per component:maintenance_type pair wins.
    """
    # For each component+type pair, keep the most recent record by startTime.
    # Using most-recent rather than highest next_due_hobbs avoids picking up
    # stale historical records with inconsistent Hobbs baselines.
    best: dict[str, tuple[int, dict[str, Any]]] = {}

    for event in all_events:
        meta = event.get("metadata", {})
        component = meta.get("component_id", "")
        maint_type = meta.get("maintenance_type", event.get("subtype", ""))
        key = f"{component}:{maint_type}"
        next_due_str = meta.get("next_due_hobbs", "")
        if not next_due_str:
            continue
        try:
            float(next_due_str)  # validate it's a number
        except ValueError:
            continue
        start_time = event.get("startTime") or 0
        existing = best.get(key)
        if existing is None or start_time > existing[0]:
            best[key] = (start_time, event)

    upcoming = []
    for key, (_, event) in best.items():
        meta = event.get("metadata", {})
        next_due = float(meta.get("next_due_hobbs", 0))
        component = meta.get("component_id", "")
        maint_type = meta.get("maintenance_type", event.get("subtype", ""))
        hours_until = next_due - current_hobbs
        # Include overdue items (negative hours) up to overdue_lookback ago,
        # and upcoming items within window_hours
        if -overdue_lookback <= hours_until <= window_hours:
            upcoming.append({
                "component": component,
                "description": event.get("description", maint_type),
                "maintenanceType": maint_type,
                "nextDueHobbs": next_due,
                "hoursUntilDue": round(hours_until, 1),
                "isOverdue": hours_until < 0,
                "nextDueDate": meta.get("next_due_date", ""),
                "daysUntilDue": _days_until(meta.get("next_due_date", "")),
            })

    return sorted(upcoming, key=lambda x: x["hoursUntilDue"])


def build_ad_compliance_map(all_events: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Derive AD compliance status from maintenance records that reference ADs.
    Returns a map of AD number → last compliance date and method.
    """
    compliance: dict[str, dict[str, Any]] = {}
    for event in all_events:
        meta = event.get("metadata", {})
        ad_ref = meta.get("ad_reference", "")
        if not ad_ref:
            continue
        for ad_num in ad_ref.split(";"):
            ad_num = ad_num.strip()
            if not ad_num:
                continue
            existing = compliance.get(ad_num)
            event_time = event.get("startTime") or 0
            if not existing or event_time > (existing.get("timestamp") or 0):
                compliance[ad_num] = {
                    "adNumber": ad_num,
                    "lastComplianceDate": meta.get("date", ""),
                    "timestamp": event_time,
                    "description": event.get("description", ""),
                    "method": meta.get("description", ""),
                }
    return compliance


def assemble_aircraft_context() -> dict[str, Any]:
    """
    Full CAG context assembly — traverses the complete knowledge graph for N4798E.

    This function is what the /api/status and /api/squawks endpoints call
    (without the agent), and it's also what the assemble_aircraft_context tool
    calls when the agent needs full context.

    Returns a structured AircraftContext dict that the agent uses to answer
    questions about airworthiness, maintenance history, and operational status.
    """
    clear_traversal_log()
    log_traversal("Context:N4798E(start)")

    # 1. Root asset
    log_traversal("Asset:N4798E")
    try:
        root = client.assets.retrieve(external_id="N4798E")
        root_dict = {
            "id": root.id,
            "externalId": root.external_id,
            "name": root.name,
            "description": root.description,
            "metadata": root.metadata or {},
        }
    except Exception as e:
        return {"error": f"Could not retrieve root asset N4798E: {e}"}

    # 2. Full component hierarchy
    log_traversal("AssetSubtree:N4798E")
    try:
        subtree = client.assets.retrieve_subtree(external_id="N4798E")
        all_components = [
            {
                "id": a.id,
                "externalId": a.external_id,
                "name": a.name,
                "description": a.description,
                "parentExternalId": a.parent_external_id,
                "metadata": a.metadata or {},
            }
            for a in subtree
        ]
    except Exception:
        all_components = []

    # 3. OT sensor layer — current readings
    sensors = get_sensor_summaries()
    current_hobbs = _safe_float(sensors.get("aircraft.hobbs", {}).get("value"))
    current_tach = _safe_float(sensors.get("aircraft.tach", {}).get("value"))

    # Compute SMOH from current hobbs and known overhaul baseline.
    # The second (current) engine overhaul was performed at Hobbs=3350.0.
    # This derivation is state-aware: current_hobbs reflects the active demo state's
    # datapoints, so SMOH automatically reflects clean/caution/grounded scenarios.
    SECOND_OVERHAUL_HOBBS = 3350.0
    engine_smoh = round(current_hobbs - SECOND_OVERHAUL_HOBBS, 1) if current_hobbs > 0 else 1540.0

    # 4. IT event layer — maintenance, squawks, inspections
    all_events_flat: list[dict[str, Any]] = []
    component_event_map: dict[str, dict[str, list[Any]]] = {}

    key_components = ["N4798E", "ENGINE-1", "AIRFRAME-1", "AVIONICS-1", "PROP-1"]
    for comp_ext_id in key_components:
        comp = next(
            (c for c in all_components if c["externalId"] == comp_ext_id), None
        )
        if not comp:
            continue
        comp_events = get_component_events(comp_ext_id, comp["id"])
        component_event_map[comp_ext_id] = comp_events
        all_events_flat.extend(comp_events["maintenance"])
        all_events_flat.extend(comp_events["squawks"])
        all_events_flat.extend(comp_events["inspections"])

    # Deduplicate by externalId
    seen_ids: set[str] = set()
    unique_events: list[dict[str, Any]] = []
    for e in all_events_flat:
        eid = e.get("externalId", "")
        if eid not in seen_ids:
            seen_ids.add(eid)
            unique_events.append(e)

    # 5. Open squawks
    all_squawks = [e for e in unique_events if e.get("type") == "Squawk"]
    open_squawks = [e for e in all_squawks if e.get("metadata", {}).get("status") == "open"]
    grounding_squawks = [
        e for e in open_squawks
        if e.get("metadata", {}).get("severity") == "grounding"
    ]

    # 6. Most recent annual inspection
    all_inspections = [e for e in unique_events if e.get("type") == "Inspection"]
    annual_inspections = [
        e for e in all_inspections
        if (e.get("subtype") or "").lower() == "annual"
    ]
    last_annual: Optional[dict[str, Any]] = None
    if annual_inspections:
        last_annual = max(annual_inspections, key=lambda x: x.get("startTime") or 0)

    annual_due_date = ""
    annual_days_remaining: Optional[int] = None
    if last_annual:
        annual_due_date = last_annual.get("metadata", {}).get("next_due_date", "")
        annual_days_remaining = _days_until(annual_due_date)

    # 7. Upcoming maintenance
    upcoming = derive_upcoming_maintenance(unique_events, current_hobbs)

    # 8. AD compliance map
    ad_compliance = build_ad_compliance_map(unique_events)

    # 9. ET document layer — key linked documents
    aircraft_docs = get_linked_documents("N4798E")
    engine_docs = get_linked_documents("ENGINE-1")

    log_traversal("Context:N4798E(complete)")

    return {
        "aircraft": root_dict,
        "totalComponents": len(all_components),
        "components": all_components,
        "sensors": sensors,
        "currentHobbs": current_hobbs,
        "currentTach": current_tach,
        "engineSMOH": engine_smoh,
        "engineTBO": 2000,
        "engineSMOHPercent": round((engine_smoh / 2000.0) * 100, 1),
        "componentEvents": component_event_map,
        "allMaintenance": [e for e in unique_events if e.get("type") == "MaintenanceRecord"],
        "allInspections": all_inspections,
        "openSquawks": open_squawks,
        "groundingSquawks": grounding_squawks,
        "allSquawks": all_squawks,
        "lastAnnual": last_annual,
        "annualDueDate": annual_due_date,
        "annualDaysRemaining": annual_days_remaining,
        "upcomingMaintenance": upcoming,
        "adCompliance": ad_compliance,
        "documents": (
            aircraft_docs.get("documents", []) + engine_docs.get("documents", [])
        ),
        "isAirworthy": (
            len(grounding_squawks) == 0
            and (annual_days_remaining is None or annual_days_remaining > 0)
        ),
    }
