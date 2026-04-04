"""
TimeSeries route — mirrors CDF TimeSeries API.

TimeSeries nodes represent OT sensor streams: hobbs, CHT, EGT, oil pressure, etc.
"""

from typing import Any, Optional
from fastapi import APIRouter
from pydantic import BaseModel

from ..store.store import store, TimeSeries

router = APIRouter()


class TimeSeriesFilter(BaseModel):
    assetIds: Optional[list[int]] = None
    externalIdPrefix: Optional[str] = None
    metadata: Optional[dict[str, str]] = None


class TimeSeriesListRequest(BaseModel):
    filter: Optional[TimeSeriesFilter] = None
    limit: int = 1000
    cursor: Optional[str] = None


class TimeSeriesByIdsRequest(BaseModel):
    items: list[dict[str, Any]]


def _apply_filter(ts_list: list[TimeSeries], f: Optional[TimeSeriesFilter]) -> list[TimeSeries]:
    if not f:
        return ts_list
    result = ts_list
    if f.assetIds:
        result = [ts for ts in result if ts.assetId in f.assetIds]
    if f.externalIdPrefix:
        result = [ts for ts in result if ts.externalId.startswith(f.externalIdPrefix)]
    if f.metadata:
        result = [
            ts for ts in result
            if all(ts.metadata.get(k) == v for k, v in f.metadata.items())
        ]
    return result


@router.post("/timeseries/list")
def list_timeseries(body: TimeSeriesListRequest) -> dict[str, Any]:
    """POST /timeseries/list — mirrors CDF TimeSeries.list()."""
    all_ts = store.get_timeseries()
    filtered = _apply_filter(all_ts, body.filter)
    offset = 0
    if body.cursor:
        try:
            offset = int(body.cursor)
        except ValueError:
            offset = 0
    page = filtered[offset: offset + body.limit]
    next_cursor = str(offset + body.limit) if offset + body.limit < len(filtered) else None
    return {"items": [ts.model_dump() for ts in page], "nextCursor": next_cursor}


@router.post("/timeseries/byids")
def get_timeseries_by_ids(body: TimeSeriesByIdsRequest) -> dict[str, Any]:
    """POST /timeseries/byids — mirrors CDF TimeSeries.retrieve()."""
    result = []
    for item in body.items:
        ext_id = item.get("externalId")
        if ext_id:
            ts = store.get_time_series_by_id(str(ext_id))
            if ts:
                result.append(ts.model_dump())
    return {"items": result}
