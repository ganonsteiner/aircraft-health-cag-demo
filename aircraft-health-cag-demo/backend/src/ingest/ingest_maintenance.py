"""
Maintenance Log Ingestion — mirrors src/ingest/ingestMaintenance.ts.

Parses data/maintenance_log_{state}.csv (IT source) and creates:
  - CdfEvent records for each maintenance entry (MaintenanceRecord, Squawk, Inspection)
  - Relationships: PERFORMED_ON, REFERENCES_AD, RESOLVED_BY, IDENTIFIED_ON

These are state-specific: each demo state has different post-divergence records.
Relationships are derived from events and re-ingested per state (they share the
same relationship store since they reference the same asset externalIds).

This is the IT (Information Technology) layer: structured records from the
aircraft logbook — equivalent to work orders in an SAP/ERP system.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
NOW_MS = int(time.time() * 1000)


# Mapping from component_id in CSV to CDF asset externalId
COMPONENT_TO_ASSET: dict[str, str] = {
    "AIRCRAFT": "N4798E",
    "ENGINE-1": "ENGINE-1",
    "ENGINE-1-CAM-LIFTERS": "ENGINE-1-CAM-LIFTERS",
    "ENGINE-1-MAGS": "ENGINE-1-MAGS",
    "ENGINE-1-CARB": "ENGINE-1-CARB",
    "ENGINE-1-STARTER": "ENGINE-1-STARTER",
    "ENGINE-1-ALTERNATOR": "ENGINE-1-ALTERNATOR",
    "ENGINE-1-OIL-FILTER": "ENGINE-1-OIL-FILTER",
    "ENGINE-1-SPARK-PLUGS": "ENGINE-1-SPARK-PLUGS",
    "ENGINE-1-EXHAUST": "ENGINE-1-EXHAUST",
    "PROP-1": "PROP-1",
    "AIRFRAME-1": "AIRFRAME-1",
    "AIRFRAME-1-FUEL-SYSTEM": "AIRFRAME-1-FUEL-SYSTEM",
    "AIRFRAME-1-FUEL-CAPS": "AIRFRAME-1-FUEL-CAPS",
    "AIRFRAME-1-LANDING-GEAR": "AIRFRAME-1-LANDING-GEAR",
    "AIRFRAME-1-NOSE-STRUT": "AIRFRAME-1-NOSE-STRUT",
    "AIRFRAME-1-BRAKE-SYSTEM": "AIRFRAME-1-BRAKE-SYSTEM",
    "AIRFRAME-1-FLIGHT-CONTROLS": "AIRFRAME-1-FLIGHT-CONTROLS",
    "AIRFRAME-1-SEATS-BELTS": "AIRFRAME-1-SEATS-BELTS",
    "AVIONICS-1": "AVIONICS-1",
    "AVIONICS-1-COMM": "AVIONICS-1-COMM",
    "AVIONICS-1-NAV": "AVIONICS-1-NAV",
    "AVIONICS-1-XPDR": "AVIONICS-1-XPDR",
    "AVIONICS-1-ELT": "AVIONICS-1-ELT",
    "PITOT-STATIC-1": "PITOT-STATIC-1",
    "VACUUM-1": "VACUUM-1",
}

# Component externalId → CDF asset numeric ID
ASSET_IDS: dict[str, int] = {
    "N4798E": 1, "ENGINE-1": 2, "ENGINE-1-CAM-LIFTERS": 3, "ENGINE-1-MAGS": 4,
    "ENGINE-1-CARB": 5, "ENGINE-1-STARTER": 6, "ENGINE-1-ALTERNATOR": 7,
    "ENGINE-1-OIL-FILTER": 8, "ENGINE-1-SPARK-PLUGS": 9, "ENGINE-1-EXHAUST": 10,
    "PROP-1": 11, "AIRFRAME-1": 12, "AIRFRAME-1-FUEL-SYSTEM": 13,
    "AIRFRAME-1-FUEL-CAPS": 14, "AIRFRAME-1-FUEL-SELECTOR": 15,
    "AIRFRAME-1-FUEL-STRAINER": 16, "AIRFRAME-1-LANDING-GEAR": 17,
    "AIRFRAME-1-NOSE-STRUT": 18, "AIRFRAME-1-BRAKE-SYSTEM": 19,
    "AIRFRAME-1-FLIGHT-CONTROLS": 20, "AIRFRAME-1-SEATS-BELTS": 21,
    "AVIONICS-1": 22, "AVIONICS-1-COMM": 23, "AVIONICS-1-NAV": 24,
    "AVIONICS-1-XPDR": 25, "AVIONICS-1-ELT": 26, "AVIONICS-1-ENCODER": 27,
    "PITOT-STATIC-1": 28, "VACUUM-1": 29,
}


def _safe_str(val: Any) -> str:
    if pd.isna(val):
        return ""
    return str(val).strip()


def _date_to_ms(date_str: str) -> int:
    if not date_str:
        return NOW_MS
    try:
        return int(pd.Timestamp(date_str).timestamp() * 1000)
    except Exception:
        return NOW_MS


def ingest_maintenance(state: str = "clean", ingest_relationships: bool = True) -> None:
    """
    Parse maintenance_log_{state}.csv and upsert Events + Relationships.

    Events are state-specific (each state has different post-divergence records).
    Relationships are re-ingested with each state since they reference the same
    asset externalIds. Set ingest_relationships=False to skip relationship re-ingestion.
    """
    from mock_cdf.store.store import store, CdfEvent, Relationship  # type: ignore[import]

    csv_path = DATA_DIR / f"maintenance_log_{state}.csv"
    if not csv_path.exists():
        print(f"  [maintenance:{state}] ✗ {csv_path.name} not found — run 'npm run generate' first")
        return

    # Switch store to target state before writing
    store.set_state(state)

    df = pd.read_csv(csv_path)
    df = df.where(pd.notna(df), "")
    print(f"  [maintenance:{state}] Loaded {len(df)} maintenance records")

    events: list[CdfEvent] = []
    relationships: list[Relationship] = []
    event_id_counter = 200

    for idx, row in df.iterrows():
        component_id = _safe_str(row.get("component_id", "AIRCRAFT"))
        asset_ext_id = COMPONENT_TO_ASSET.get(component_id, "N4798E")
        asset_db_id = ASSET_IDS.get(asset_ext_id, 1)

        date_str = _safe_str(row.get("date", ""))
        start_time_ms = _date_to_ms(date_str)
        maint_type = _safe_str(row.get("maintenance_type", ""))
        description = _safe_str(row.get("description", ""))
        event_ext_id = f"MAINT-{idx:05d}"

        # Determine CDF event type
        if maint_type.lower() == "squawk":
            cdf_type = "Squawk"
            cdf_subtype = _safe_str(row.get("signoff_type", ""))
        elif maint_type.lower() in ("annual", "100hr", "progressive"):
            cdf_type = "Inspection"
            cdf_subtype = maint_type.lower()
        else:
            cdf_type = "MaintenanceRecord"
            cdf_subtype = maint_type

        metadata = {
            "date": date_str,
            "component_id": component_id,
            "maintenance_type": maint_type,
            "hobbs_at_service": _safe_str(row.get("hobbs_at_service", "")),
            "tach_at_service": _safe_str(row.get("tach_at_service", "")),
            "next_due_hobbs": _safe_str(row.get("next_due_hobbs", "")),
            "next_due_date": _safe_str(row.get("next_due_date", "")),
            "mechanic": _safe_str(row.get("mechanic", "")),
            "inspector": _safe_str(row.get("inspector", "")),
            "ad_reference": _safe_str(row.get("ad_reference", "")),
            "sb_reference": _safe_str(row.get("sb_reference", "")),
            "squawk_id": _safe_str(row.get("squawk_id", "")),
            "resolved_by": _safe_str(row.get("resolved_by", "")),
            "parts_replaced": _safe_str(row.get("parts_replaced", "")),
            "labor_hours": _safe_str(row.get("labor_hours", "")),
            "signoff_type": _safe_str(row.get("signoff_type", "")),
        }
        if cdf_type == "Squawk":
            metadata["severity"] = _safe_str(row.get("severity", "non-grounding"))
            metadata["status"] = _safe_str(row.get("status", "open"))
            metadata["date_identified"] = date_str

        event = CdfEvent(
            id=event_id_counter,
            externalId=event_ext_id,
            type=cdf_type,
            subtype=cdf_subtype or None,
            description=description,
            startTime=start_time_ms,
            assetIds=[asset_db_id, 1],
            metadata=metadata,
            source="maintenance_log",
            createdTime=NOW_MS,
            lastUpdatedTime=NOW_MS,
        )
        events.append(event)
        event_id_counter += 1

        if ingest_relationships:
            # PERFORMED_ON relationship: event → component asset
            relationships.append(Relationship(
                externalId=f"REL-PERFORMED-{idx:05d}",
                sourceExternalId=event_ext_id,
                sourceType="event",
                targetExternalId=asset_ext_id,
                targetType="asset",
                relationshipType="PERFORMED_ON",
                createdTime=NOW_MS,
                lastUpdatedTime=NOW_MS,
            ))

            # REFERENCES_AD relationship: event → AD document
            ad_ref = _safe_str(row.get("ad_reference", ""))
            if ad_ref:
                for ad in ad_ref.split(";"):
                    ad = ad.strip()
                    if ad:
                        ad_ext_id = f"AD-{ad.replace(' ', '-').replace('/', '-')}"
                        relationships.append(Relationship(
                            externalId=f"REL-AD-{idx:05d}-{ad_ext_id}",
                            sourceExternalId=event_ext_id,
                            sourceType="event",
                            targetExternalId=ad_ext_id,
                            targetType="file",
                            relationshipType="REFERENCES_AD",
                            createdTime=NOW_MS,
                            lastUpdatedTime=NOW_MS,
                        ))

            # RESOLVED_BY / IDENTIFIED_ON for squawks
            squawk_id = _safe_str(row.get("squawk_id", ""))
            if squawk_id and cdf_type != "Squawk":
                relationships.append(Relationship(
                    externalId=f"REL-RESOLVED-{idx:05d}",
                    sourceExternalId=squawk_id,
                    sourceType="event",
                    targetExternalId=event_ext_id,
                    targetType="event",
                    relationshipType="RESOLVED_BY",
                    createdTime=NOW_MS,
                    lastUpdatedTime=NOW_MS,
                ))
            if cdf_type == "Squawk":
                relationships.append(Relationship(
                    externalId=f"REL-IDENTIFIED-{idx:05d}",
                    sourceExternalId=event_ext_id,
                    sourceType="event",
                    targetExternalId=asset_ext_id,
                    targetType="asset",
                    relationshipType="IDENTIFIED_ON",
                    createdTime=NOW_MS,
                    lastUpdatedTime=NOW_MS,
                ))

    store.upsert_events(events)
    if ingest_relationships:
        store.upsert_relationships(relationships)
    print(f"  [maintenance:{state}] ✓ {len(events)} events, {len(relationships)} relationships ingested")


if __name__ == "__main__":
    ingest_maintenance()
