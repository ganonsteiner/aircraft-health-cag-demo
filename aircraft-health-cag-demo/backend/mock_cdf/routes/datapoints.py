"""
Datapoints route — mirrors CDF Datapoints API.

Datapoints represent actual OT sensor readings: instrument values recorded per flight.
The CDF SDK posts to /timeseries/data/list to retrieve time-windowed datapoints.
"""

from typing import Any, Optional
from fastapi import APIRouter
from pydantic import BaseModel

from ..store.store import store

router = APIRouter()


class DatapointQuery(BaseModel):
    externalId: Optional[str] = None
    id: Optional[int] = None
    start: Optional[int] = None
    end: Optional[int] = None
    limit: int = 1000
    aggregates: Optional[list[str]] = None
    granularity: Optional[str] = None


class DatapointsListRequest(BaseModel):
    items: list[DatapointQuery]
    start: Optional[int] = None
    end: Optional[int] = None
    limit: int = 1000


class DatapointsLatestRequest(BaseModel):
    items: list[dict[str, Any]]


@router.post("/timeseries/data/list")
def list_datapoints(body: DatapointsListRequest) -> dict[str, Any]:
    """
    POST /timeseries/data/list — mirrors CDF Datapoints.retrieve().

    Returns one result entry per requested time series with its data points
    in the requested time window.
    """
    results = []
    for query in body.items:
        ext_id = query.externalId
        if not ext_id and query.id:
            ts = next(
                (ts for ts in store.get_timeseries() if ts.id == query.id), None
            )
            ext_id = ts.externalId if ts else None
        if not ext_id:
            continue
        start = query.start or body.start
        end = query.end or body.end
        limit = query.limit or body.limit
        points = store.get_datapoints(ext_id, start, end, limit)
        results.append({
            "externalId": ext_id,
            "id": next(
                (ts.id for ts in store.get_timeseries() if ts.externalId == ext_id), 0
            ),
            "datapoints": [{"timestamp": p.timestamp, "value": p.value} for p in points],
            "isString": False,
        })
    return {"items": results}


@router.post("/timeseries/data/latest")
def latest_datapoints(body: DatapointsLatestRequest) -> dict[str, Any]:
    """POST /timeseries/data/latest — returns most recent datapoint per time series."""
    results = []
    for item in body.items:
        ext_id = item.get("externalId")
        if not ext_id:
            continue
        point = store.get_latest_datapoint(ext_id)
        results.append({
            "externalId": ext_id,
            "datapoints": [{"timestamp": point.timestamp, "value": point.value}] if point else [],
        })
    return {"items": results}
