"""
Ingestion Orchestrator — mirrors src/ingest/index.ts.

Runs all ingestion stages in order:
  1. Assets      — build the component hierarchy (shared, once)
  2. Documents   — ET documents (POH, ADs, SBs) from data/documents/ (shared, once)
  3. Flights     — OT sensor data — three passes, one per demo state
  4. Maintenance — IT maintenance records — three passes, one per demo state

Shared resources (assets, documents) are ingested once since they are identical
across all demo states. State-specific resources (flights/datapoints and
maintenance/events) are ingested three times, writing to state-specific store files.

After ingestion, signals the mock CDF server to reload its in-memory store.

Usage:
  cd backend
  python -m src.ingest.index
"""

from __future__ import annotations

import sys
import time


def run_ingestion() -> None:
    start = time.time()
    print("\n✈  N4798E Ingestion Pipeline (three-state CAG demo)\n")

    print("Stage 1/4: Assets (shared across all states)")
    from .ingest_assets import ingest_assets
    ingest_assets()

    print("\nStage 2/4: Documents — ET layer (shared across all states)")
    from .ingest_documents import ingest_documents
    ingest_documents()

    print("\nStage 3/4: Flight Data (OT) — three state passes")
    from .ingest_flights import ingest_flights
    for i, state in enumerate(("clean", "caution", "grounded")):
        # Only ingest TimeSeries definitions on the first pass (they're shared)
        ingest_flights(state=state, ingest_timeseries=(i == 0))

    print("\nStage 4/4: Maintenance Log (IT) — three state passes")
    from .ingest_maintenance import ingest_maintenance
    for i, state in enumerate(("clean", "caution", "grounded")):
        # Only ingest Relationships on the first pass (they reference shared assets)
        ingest_maintenance(state=state, ingest_relationships=(i == 0))

    elapsed = time.time() - start
    print(f"\n✓ Ingestion complete in {elapsed:.1f}s")

    # Signal the mock CDF server to reload its in-memory store from disk.
    # After reload, the server will have all three state stores loaded.
    import urllib.request
    mock_cdf_url = "http://localhost:4000/admin/reload"
    try:
        req = urllib.request.Request(mock_cdf_url, method="POST", data=b"")
        with urllib.request.urlopen(req, timeout=3) as resp:
            print(f"  Mock CDF store reloaded: {resp.read().decode()[:80]}")
    except Exception:
        print("  (mock CDF server not running — start it and re-run ingest if needed)")
    print()


if __name__ == "__main__":
    run_ingestion()
