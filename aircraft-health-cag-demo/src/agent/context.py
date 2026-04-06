"""
CAG Context Assembly — Desert Sky Aviation Fleet.

assemble_aircraft_context(aircraft_id) builds structured context for one
aircraft by traversing the knowledge graph. Used by /api/status and the
agent's assemble_aircraft_context tool.

Context is assembled by graph traversal only — no vector store, no embeddings.
This mirrors exactly how Cognite's Atlas AI works.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

from .tools import (  # noqa: E402
    client,
    log_traversal,
    clear_traversal_log,
    get_linked_documents,
    symptom_fleet_deep_dive,
    fetch_aircraft_symptoms_payload,
)
from ..aircraft_times import (  # noqa: E402
    current_hobbs_from_sdk,
    current_tach_from_sdk,
    next_due_tach_from_meta,
)

_NOW = datetime.now(timezone.utc)

TAILS = ("N4798E", "N2251K", "N8834Q", "N1156P")


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _days_until(date_str: str) -> Optional[int]:
    if not date_str:
        return None
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return (target - _NOW).days
    except ValueError:
        return None


def _maintenance_type_label(maint_type: str) -> str:
    t = (maint_type or "").strip().lower().replace(" ", "_")
    labels = {
        "oil_change": "Oil change",
        "annual": "Annual inspection",
        "100hr": "100-hour inspection",
        "progressive": "Progressive inspection",
        "squawk": "Squawk",
        "post_accident_inspection": "Post-accident inspection",
    }
    return labels.get(t, maint_type.replace("_", " ").title() if maint_type else "Maintenance")


def _build_tach_maintenance_summary(
    maint_type: str,
    hours_until: float,
    next_due_date: str,
    days_until: Optional[int],
) -> str:
    label = _maintenance_type_label(maint_type)
    parts: list[str] = []
    if hours_until < 0:
        parts.append(f"{label} overdue by {abs(hours_until):.1f} hr")
    else:
        parts.append(f"{label} due in {hours_until:.1f} hr")
    if next_due_date:
        if days_until is not None:
            if days_until < 0:
                parts.append(f"calendar target {next_due_date} ({abs(days_until)} days ago)")
            else:
                parts.append(f"or by {next_due_date} ({days_until} days)")
        else:
            parts.append(f"or by {next_due_date}")
    return " · ".join(parts)


def derive_upcoming_maintenance(
    all_events: list[dict[str, Any]],
    current_tach: float,
    aircraft_root_id: str,
    window_tach_hours: float = 250.0,
    overdue_lookback: float = 500.0,
) -> list[dict[str, Any]]:
    """
    Find maintenance items due within a tach-hour window (oil, etc.) plus annual
    inspections by calendar. Uses most-recent record per component:maintenance_type.
    """
    best: dict[str, tuple[int, dict[str, Any]]] = {}
    for event in all_events:
        if event.get("type") not in ("MaintenanceRecord", "Inspection"):
            continue
        meta = event.get("metadata", {})
        component = meta.get("component_id", "")
        maint_type = meta.get("maintenance_type", event.get("subtype", ""))
        key = f"{component}:{maint_type}"
        next_due = next_due_tach_from_meta(meta)
        if next_due is None:
            continue
        start_time = event.get("startTime") or 0
        existing = best.get(key)
        if existing is None or start_time > existing[0]:
            best[key] = (start_time, event)

    upcoming: list[dict[str, Any]] = []
    for _, (_, event) in best.items():
        meta = event.get("metadata", {})
        next_due = next_due_tach_from_meta(meta)
        if next_due is None:
            continue
        component = meta.get("component_id", "")
        maint_type = meta.get("maintenance_type", event.get("subtype", ""))
        hours_until = next_due - current_tach
        if not (-overdue_lookback <= hours_until <= window_tach_hours):
            continue
        nd_date = meta.get("next_due_date", "") or ""
        days_until = _days_until(nd_date) if nd_date else None
        upcoming.append({
            "component": component,
            "summary": _build_tach_maintenance_summary(maint_type, hours_until, nd_date, days_until),
            "description": event.get("description", maint_type),
            "maintenanceType": maint_type,
            "nextDueTach": round(next_due, 1),
            "nextDueHobbs": round(next_due, 1),
            "hoursUntilDue": round(hours_until, 1),
            "isOverdue": hours_until < 0,
            "nextDueDate": nd_date,
            "daysUntilDue": days_until,
        })

    # Annual inspections (calendar-driven) for the airframe root
    annuals = [
        e for e in all_events
        if e.get("type") == "Inspection" and (e.get("subtype") or "").lower() == "annual"
    ]
    last_annual: Optional[dict[str, Any]] = None
    for e in annuals:
        meta = e.get("metadata", {})
        if meta.get("component_id", "") != aircraft_root_id:
            continue
        if last_annual is None or (e.get("startTime") or 0) > (last_annual.get("startTime") or 0):
            last_annual = e
    if last_annual:
        meta = last_annual.get("metadata", {})
        nd_date = meta.get("next_due_date", "") or ""
        if nd_date:
            days_until = _days_until(nd_date)
            if days_until is not None and -120 <= days_until <= 400:
                component = meta.get("component_id", aircraft_root_id)
                maint_type = "annual"
                upcoming.append({
                    "component": component,
                    "summary": (
                        f"Annual inspection due in {days_until} days ({nd_date})"
                        if days_until >= 0
                        else f"Annual inspection overdue by {abs(days_until)} days ({nd_date})"
                    ),
                    "description": last_annual.get("description", ""),
                    "maintenanceType": maint_type,
                    "nextDueTach": None,
                    "nextDueHobbs": None,
                    "hoursUntilDue": None,
                    "isOverdue": days_until < 0,
                    "nextDueDate": nd_date,
                    "daysUntilDue": days_until,
                })

    def _sort_key(x: dict[str, Any]) -> tuple[float, float]:
        hu = x.get("hoursUntilDue")
        dd = x.get("daysUntilDue")
        h_key = float(hu) if hu is not None else 1e6
        d_key = float(dd) if dd is not None else 1e6
        return (h_key, d_key)

    return sorted(upcoming, key=_sort_key)


def assemble_aircraft_context(aircraft_id: str) -> dict[str, Any]:
    """
    Full CAG context assembly for one aircraft by traversing the knowledge graph.

    Used by /api/status?aircraft={tail} and the agent's assemble_aircraft_context tool.
    """
    clear_traversal_log()
    log_traversal(f"Context:{aircraft_id}(start)")

    # 1. Root asset (retrieve returns None if not found — does not raise)
    log_traversal(f"Asset:{aircraft_id}")
    try:
        root = client.assets.retrieve(external_id=aircraft_id)
        if root is None:
            return {
                "error": (
                    f"Aircraft asset {aircraft_id} not found in CDF. "
                    "If npm run dev shows mock-cdf exiting with 'Address already in use', "
                    "another process is bound to port 4000 — stop it so this project's mock "
                    "CDF can start, then restart the stack."
                ),
            }
        root_dict = {
            "id": root.id,
            "externalId": root.external_id,
            "name": root.name,
            "description": root.description,
            "metadata": root.metadata or {},
        }
    except Exception as e:
        return {"error": f"Could not retrieve root asset {aircraft_id}: {e}"}

    meta = root_dict.get("metadata", {})
    overhaul_hobbs_str = meta.get("overhaul_hobbs", "")

    # 2. Full component hierarchy
    log_traversal(f"AssetSubtree:{aircraft_id}")
    try:
        subtree = client.assets.retrieve_subtree(external_id=aircraft_id)
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

    # 3. OT sensors — per-tail time series IDs
    sensor_suffixes = [
        "aircraft.hobbs", "aircraft.tach", "aircraft.cycles", "aircraft.fuel_used",
        "engine.oil_pressure_min", "engine.oil_pressure_max",
        "engine.oil_temp_max", "engine.cht_max", "engine.egt_max",
    ]
    sensors: dict[str, Any] = {}
    for suffix in sensor_suffixes:
        ts_ext_id = f"{aircraft_id}.{suffix}"
        log_traversal(f"Sensor:latest:{ts_ext_id}")
        try:
            dp = client.time_series.data.retrieve_latest(external_id=ts_ext_id)
            if dp and len(dp) > 0:
                sensors[suffix] = {
                    "timestamp": int(dp[0].timestamp),
                    "value": float(dp[0].value),
                }
        except Exception:
            pass

    current_hobbs = current_hobbs_from_sdk(client, aircraft_id)
    current_tach = current_tach_from_sdk(client, aircraft_id)
    if current_hobbs <= 0.0:
        current_hobbs = _safe_float(sensors.get("aircraft.hobbs", {}).get("value"))
    if current_tach <= 0.0:
        current_tach = _safe_float(sensors.get("aircraft.tach", {}).get("value"))

    # SMOH from tach since overhaul (maintenance clock)
    overhaul_tach = _safe_float(meta.get("overhaul_tach", ""), default=-1.0)
    if overhaul_tach < 0:
        engine_smoh_str = meta.get("engine_smoh", "")
        try:
            engine_smoh = float(engine_smoh_str)
        except (ValueError, TypeError):
            engine_smoh = 0.0
    else:
        engine_smoh = max(0.0, round(current_tach - overhaul_tach, 1))

    # 4. IT event layer
    all_events_flat: list[dict[str, Any]] = []
    try:
        events = client.events.list(asset_ids=[root.id], limit=1000)
        for e in events:
            all_events_flat.append({
                "id": e.id,
                "externalId": e.external_id,
                "type": e.type,
                "subtype": e.subtype,
                "description": e.description,
                "startTime": e.start_time,
                "metadata": e.metadata or {},
                "source": e.source,
            })
    except Exception:
        pass

    # 5. Open squawks
    all_squawks = [e for e in all_events_flat if e.get("type") == "Squawk"]
    open_squawks = [e for e in all_squawks if e.get("metadata", {}).get("status") == "open"]
    grounding_squawks = [e for e in open_squawks if e.get("metadata", {}).get("severity") == "grounding"]

    # 6. Annual inspection currency
    annual_inspections = [
        e for e in all_events_flat
        if e.get("type") == "Inspection" and (e.get("subtype") or "").lower() == "annual"
    ]
    last_annual: Optional[dict[str, Any]] = None
    if annual_inspections:
        last_annual = max(annual_inspections, key=lambda x: x.get("startTime") or 0)

    annual_due_date = ""
    annual_days_remaining: Optional[int] = None
    if last_annual:
        annual_due_date = last_annual.get("metadata", {}).get("next_due_date", "")
        annual_days_remaining = _days_until(annual_due_date)

    # 7. Oil change status
    oil_changes = [
        e for e in all_events_flat
        if e.get("type") == "MaintenanceRecord" and "oil_change" in (e.get("subtype") or "").lower()
    ]
    last_oil_change = max(oil_changes, key=lambda x: x.get("startTime") or 0) if oil_changes else None
    oil_next_due_tach = 0.0
    oil_next_due_date = ""
    if last_oil_change:
        om = last_oil_change.get("metadata", {})
        ndt = next_due_tach_from_meta(om)
        if ndt is not None:
            oil_next_due_tach = ndt
        oil_next_due_date = str(om.get("next_due_date", "") or "")
    oil_tach_hours_overdue = (
        max(0.0, round(current_tach - oil_next_due_tach, 1)) if oil_next_due_tach > 0 else 0.0
    )
    oil_tach_hours_until_due = (
        round(oil_next_due_tach - current_tach, 1) if oil_next_due_tach > 0 else 0.0
    )
    oil_days_until_due = _days_until(oil_next_due_date) if oil_next_due_date else None

    # 8. Upcoming maintenance (tach + annual calendar)
    maint_events = [e for e in all_events_flat if e.get("type") in ("MaintenanceRecord", "Inspection")]
    upcoming = derive_upcoming_maintenance(maint_events, current_tach, aircraft_id)

    # 9. Symptoms for this aircraft (Observation/Symptom CDF events via SDK)
    symptoms_payload = fetch_aircraft_symptoms_payload(aircraft_id)
    sym_items = symptoms_payload.get("symptoms") or []
    symptom_deep_dive = symptom_fleet_deep_dive(aircraft_id, symptoms_payload)

    # 10. ET documents
    aircraft_docs = get_linked_documents(aircraft_id)
    engine_docs = get_linked_documents(f"{aircraft_id}-ENGINE")

    # 11. Airworthiness determination
    annual_expired = annual_days_remaining is not None and annual_days_remaining < 0
    has_grounding_squawk = len(grounding_squawks) > 0
    oil_5hr_overdue = oil_tach_hours_overdue > 5.0
    oil_1hr_overdue = oil_tach_hours_overdue >= 1.0

    if has_grounding_squawk or annual_expired or oil_5hr_overdue:
        airworthiness = "NOT_AIRWORTHY"
    elif oil_1hr_overdue:
        airworthiness = "FERRY_ONLY"
    elif len(open_squawks) > 0 and len(sym_items) > 0:
        airworthiness = "CAUTION"
    else:
        airworthiness = "AIRWORTHY"

    log_traversal(f"Context:{aircraft_id}(complete)")

    out: dict[str, Any] = {
        "aircraft": root_dict,
        "totalComponents": len(all_components),
        "components": all_components,
        "sensors": sensors,
        "currentHobbs": current_hobbs,
        "currentTach": current_tach,
        "engineSMOH": engine_smoh,
        "engineTBO": 2000,
        "engineSMOHPercent": round((engine_smoh / 2000.0) * 100, 1) if engine_smoh > 0 else 0.0,
        "allMaintenance": [e for e in all_events_flat if e.get("type") == "MaintenanceRecord"],
        "allInspections": annual_inspections,
        "openSquawks": open_squawks,
        "groundingSquawks": grounding_squawks,
        "allSquawks": all_squawks,
        "lastAnnual": last_annual,
        "annualDueDate": annual_due_date,
        "annualDaysRemaining": annual_days_remaining,
        "oilNextDueTach": oil_next_due_tach,
        "oilNextDueDate": oil_next_due_date,
        "oilTachHoursUntilDue": oil_tach_hours_until_due,
        "oilDaysUntilDue": oil_days_until_due,
        "oilNextDueHobbs": oil_next_due_tach,
        "oilHoursOverdue": oil_tach_hours_overdue,
        "oilTachHoursOverdue": oil_tach_hours_overdue,
        "upcomingMaintenance": upcoming,
        "symptoms": sym_items,
        "conditions": [],
        "documents": aircraft_docs.get("documents", []) + engine_docs.get("documents", []),
        "airworthiness": airworthiness,
        "isAirworthy": airworthiness == "AIRWORTHY",
    }
    if symptom_deep_dive is not None:
        out["symptomDeepDive"] = symptom_deep_dive
    return out
