"""
Per-aircraft Hobbs (display) and tach (maintenance clock) from CDF time series.

Hobbs comes from {tail}.aircraft.hobbs; tach from {tail}.aircraft.tach.
Maintenance intervals and oil overdue math use tach only.
"""

from __future__ import annotations

from typing import Any, Optional


def current_hobbs_from_cdf_store(store: Any, tail: str) -> float:
    """Latest Hobbs from mock CDF store (max timestamp wins)."""
    hobbs_ts_id = f"{tail}.aircraft.hobbs"
    dp = store.get_latest_datapoint(hobbs_ts_id)
    return float(dp.value) if dp is not None else 0.0


def current_tach_from_cdf_store(store: Any, tail: str) -> float:
    """Latest tach from mock CDF store (max timestamp wins)."""
    tach_ts_id = f"{tail}.aircraft.tach"
    dp = store.get_latest_datapoint(tach_ts_id)
    return float(dp.value) if dp is not None else 0.0


def current_hobbs_from_sdk(client: Any, tail: str) -> float:
    """Retrieve latest Hobbs via CogniteClient (same TS external ID as ingest)."""
    ts_ext_id = f"{tail}.aircraft.hobbs"
    try:
        dp = client.time_series.data.retrieve_latest(external_id=ts_ext_id)
        if dp and len(dp) > 0:
            return float(dp[0].value)
    except Exception:
        pass
    return 0.0


def current_tach_from_sdk(client: Any, tail: str) -> float:
    """Retrieve latest tach via CogniteClient."""
    ts_ext_id = f"{tail}.aircraft.tach"
    try:
        dp = client.time_series.data.retrieve_latest(external_id=ts_ext_id)
        if dp and len(dp) > 0:
            return float(dp[0].value)
    except Exception:
        pass
    return 0.0


def next_due_tach_from_meta(meta: dict[str, Any]) -> Optional[float]:
    """
    Next maintenance due tach reading from event metadata.

    Prefers next_due_tach; falls back to legacy next_due_hobbs when tach column
    was not populated (older stores).
    """
    raw = meta.get("next_due_tach") or meta.get("next_due_hobbs") or ""
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None
