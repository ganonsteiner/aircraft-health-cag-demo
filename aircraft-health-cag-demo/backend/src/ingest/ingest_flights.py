"""
Flight Data Ingestion — mirrors src/ingest/ingestFlights.ts.

Parses data/flight_data_{state}.csv (OT source) and creates:
  - 9 TimeSeries nodes (one per sensor metric) — shared across states, ingested once
  - Datapoints for each reading — state-specific (written to datapoints_{state}.json)

This is the OT (Operational Technology) layer: actual instrument readings
from the aircraft, recorded per flight. In a real industrial context, this
data would stream in from PLCs or SCADA systems.

The state parameter controls which CSV to read and which store file to write.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
NOW_MS = int(time.time() * 1000)


TIME_SERIES_DEFS: list[dict[str, Any]] = [
    {"id": 101, "externalId": "aircraft.hobbs",          "name": "Aircraft Hobbs Time",          "unit": "hours",  "assetExternalId": "N4798E"},
    {"id": 102, "externalId": "aircraft.tach",           "name": "Aircraft Tach Time",           "unit": "hours",  "assetExternalId": "N4798E"},
    {"id": 103, "externalId": "aircraft.cycles",         "name": "Aircraft Landing Cycles",      "unit": "cycles", "assetExternalId": "N4798E"},
    {"id": 104, "externalId": "aircraft.fuel_used",      "name": "Fuel Used Per Flight",         "unit": "gal",    "assetExternalId": "N4798E"},
    {"id": 105, "externalId": "engine.oil_pressure_min", "name": "Engine Oil Pressure Min",      "unit": "psi",    "assetExternalId": "ENGINE-1"},
    {"id": 106, "externalId": "engine.oil_pressure_max", "name": "Engine Oil Pressure Max",      "unit": "psi",    "assetExternalId": "ENGINE-1"},
    {"id": 107, "externalId": "engine.oil_temp_max",     "name": "Engine Oil Temp Max",          "unit": "°F",     "assetExternalId": "ENGINE-1"},
    {"id": 108, "externalId": "engine.cht_max",          "name": "Engine CHT Max",               "unit": "°F",     "assetExternalId": "ENGINE-1"},
    {"id": 109, "externalId": "engine.egt_max",          "name": "Engine EGT Max",               "unit": "°F",     "assetExternalId": "ENGINE-1"},
]

# CSV column → time series externalId mapping
COLUMN_TO_TS: dict[str, str] = {
    "hobbs_end":          "aircraft.hobbs",
    "tach_end":           "aircraft.tach",
    "cycles":             "aircraft.cycles",
    "fuel_used_gal":      "aircraft.fuel_used",
    "oil_pressure_min":   "engine.oil_pressure_min",
    "oil_pressure_max":   "engine.oil_pressure_max",
    "oil_temp_max":       "engine.oil_temp_max",
    "cht_max":            "engine.cht_max",
    "egt_max":            "engine.egt_max",
}


def _resolve_asset_id(external_id: str) -> int:
    """Look up numeric asset ID for TimeSeries assetId field."""
    asset_ids = {
        "N4798E": 1,
        "ENGINE-1": 2,
    }
    return asset_ids.get(external_id, 1)


def ingest_flights(state: str = "clean", ingest_timeseries: bool = True) -> None:
    """
    Parse flight_data_{state}.csv and upsert TimeSeries + Datapoints.

    TimeSeries definitions are shared across all states and only need to be
    ingested once. Set ingest_timeseries=False for subsequent state passes.
    Datapoints are state-specific and always re-ingested.
    """
    from mock_cdf.store.store import store, TimeSeries, Datapoint  # type: ignore[import]

    csv_path = DATA_DIR / f"flight_data_{state}.csv"
    if not csv_path.exists():
        print(f"  [flights:{state}] ✗ {csv_path.name} not found — run 'npm run generate' first")
        return

    # Switch store to the target state before writing
    store.set_state(state)

    df = pd.read_csv(csv_path, parse_dates=["timestamp"])
    print(f"  [flights:{state}] Loaded {len(df)} flight records from {csv_path.name}")

    # Upsert TimeSeries nodes (shared — only needed once)
    if ingest_timeseries:
        ts_objects = []
        for ts_def in TIME_SERIES_DEFS:
            ts_objects.append(TimeSeries(
                id=ts_def["id"],
                externalId=ts_def["externalId"],
                name=ts_def["name"],
                unit=ts_def.get("unit"),
                assetId=_resolve_asset_id(ts_def["assetExternalId"]),
                metadata={"assetExternalId": ts_def["assetExternalId"]},
                createdTime=NOW_MS,
                lastUpdatedTime=NOW_MS,
            ))
        store.upsert_timeseries(ts_objects)
        print(f"  [flights:{state}] ✓ {len(ts_objects)} TimeSeries upserted")

    # Build datapoints per time series
    datapoints_by_ts: dict[str, list[Datapoint]] = {ts_def["externalId"]: [] for ts_def in TIME_SERIES_DEFS}

    for _, row in df.iterrows():
        ts_ms = int(pd.Timestamp(row["timestamp"]).timestamp() * 1000)
        for col, ts_id in COLUMN_TO_TS.items():
            val = row.get(col)
            if pd.notna(val):
                try:
                    datapoints_by_ts[ts_id].append(
                        Datapoint(timestamp=ts_ms, value=float(val))
                    )
                except (ValueError, TypeError):
                    pass

    total_points = 0
    for ts_ext_id, points in datapoints_by_ts.items():
        if points:
            store.set_datapoints(ts_ext_id, points)
            total_points += len(points)

    print(f"  [flights:{state}] ✓ {total_points} datapoints ingested")


if __name__ == "__main__":
    ingest_flights()
