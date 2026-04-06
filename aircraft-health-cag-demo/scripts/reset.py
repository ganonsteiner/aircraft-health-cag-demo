"""
Reset script — clears the mock CDF store and re-runs ingestion.

Usage:
  python -m scripts.reset
  (from project root)
"""

from __future__ import annotations



def reset() -> None:
    print("\n✈  Resetting mock CDF store...\n")
    from mock_cdf.store.store import store  # type: ignore[import]
    store.clear()
    print("  ✓ Store cleared\n")

    from src.ingest.index import run_ingestion  # type: ignore[import]
    run_ingestion()


if __name__ == "__main__":
    reset()
