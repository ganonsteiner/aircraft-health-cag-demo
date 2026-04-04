"""
Transform Maintenance Log to CAG-Ready CSVs.

Reads from dataset.py (single source of truth) and writes three state-specific
CSV files for the ingestion pipeline:
  data/maintenance_log_clean.csv
  data/maintenance_log_caution.csv
  data/maintenance_log_grounded.csv

Each CSV uses MAINTENANCE_SHARED as the common base (1978 – Nov 1 2025), with
state-specific recent records appended for the post-divergence period.

Usage:
  cd aircraft-health-cag-demo
  python backend/scripts/transform_maintenance_to_cag.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from dataset import (  # noqa: E402
    MAINTENANCE_SHARED,
    MAINTENANCE_CLEAN_RECENT,
    MAINTENANCE_CAUTION_RECENT,
    MAINTENANCE_GROUNDED_RECENT,
)

DATA_DIR = Path(__file__).parent.parent.parent / "data"


def write_maintenance(rows: list[dict], state: str) -> None:
    """Write assembled maintenance records to data/maintenance_log_{state}.csv."""
    df = pd.DataFrame(rows)
    out = DATA_DIR / f"maintenance_log_{state}.csv"
    df.to_csv(out, index=False)
    print(f"  [{state}] ✓ {len(df)} maintenance records → {out.name}")
    squawks = df[df["maintenance_type"] == "squawk"]
    open_sq = squawks[squawks["status"] == "open"] if "status" in squawks.columns else squawks.head(0)
    print(f"           Squawks: {len(squawks)} total, {len(open_sq)} open")


if __name__ == "__main__":
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("\n✈  Transforming maintenance log for N4798E (three demo states, 1978–2026)...\n")

    MAINTENANCE_CLEAN    = MAINTENANCE_SHARED + MAINTENANCE_CLEAN_RECENT
    MAINTENANCE_CAUTION  = MAINTENANCE_SHARED + MAINTENANCE_CAUTION_RECENT
    MAINTENANCE_GROUNDED = MAINTENANCE_SHARED + MAINTENANCE_GROUNDED_RECENT

    write_maintenance(MAINTENANCE_CLEAN,    "clean")
    write_maintenance(MAINTENANCE_CAUTION,  "caution")
    write_maintenance(MAINTENANCE_GROUNDED, "grounded")

    print(f"\n✓ Three maintenance CSV files written to {DATA_DIR}\n")
