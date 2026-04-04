"""
Transform Flight Data to CAG-Ready CSVs.

Reads from dataset.py (single source of truth) and writes three state-specific
CSV files for the ingestion pipeline:
  data/flight_data_clean.csv
  data/flight_data_caution.csv
  data/flight_data_grounded.csv

Each CSV uses FLIGHTS_SHARED as the common base, with state-specific recent
flights appended for the post-divergence period (after Nov 1, 2025).

Usage:
  cd aircraft-health-cag-demo
  python backend/scripts/transform_flights_to_cag.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

# Allow importing from the scripts directory
sys.path.insert(0, str(Path(__file__).parent))
from dataset import (  # noqa: E402
    FLIGHTS_SHARED,
    FLIGHTS_CLEAN_RECENT,
    FLIGHTS_CAUTION_RECENT,
    FLIGHTS_GROUNDED_RECENT,
)

DATA_DIR = Path(__file__).parent.parent.parent / "data"


def write_flights(rows: list[dict], state: str) -> None:
    """Write assembled flight records to data/flight_data_{state}.csv."""
    df = pd.DataFrame(rows)
    out = DATA_DIR / f"flight_data_{state}.csv"
    df.to_csv(out, index=False)
    print(f"  [{state}] ✓ {len(df)} flight records → {out.name}")
    h_start = df["hobbs_start"].min()
    h_end = df["hobbs_end"].max()
    print(f"           Hobbs range: {h_start:.1f} → {h_end:.1f}")


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("\n✈  Transforming flight data for N4798E (three demo states)...\n")

    FLIGHTS_CLEAN    = FLIGHTS_SHARED + FLIGHTS_CLEAN_RECENT
    FLIGHTS_CAUTION  = FLIGHTS_SHARED + FLIGHTS_CAUTION_RECENT
    FLIGHTS_GROUNDED = FLIGHTS_SHARED + FLIGHTS_GROUNDED_RECENT

    write_flights(FLIGHTS_CLEAN,    "clean")
    write_flights(FLIGHTS_CAUTION,  "caution")
    write_flights(FLIGHTS_GROUNDED, "grounded")

    print(f"\n✓ Three flight CSV files written to {DATA_DIR}\n")
