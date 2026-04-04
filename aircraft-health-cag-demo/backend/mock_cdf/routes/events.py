"""
Events route — mirrors CDF Events API.

Events represent IT data: maintenance records, squawks, and inspections.
This is the primary source for maintenance history queries.
"""

from typing import Any, Optional
from fastapi import APIRouter
from pydantic import BaseModel

from ..store.store import store, CdfEvent

router = APIRouter()


class EventFilter(BaseModel):
    type: Optional[str] = None
    subtype: Optional[str] = None
    assetIds: Optional[list[int]] = None
    assetExternalIds: Optional[list[str]] = None
    metadata: Optional[dict[str, str]] = None
    startTime: Optional[dict[str, int]] = None
    endTime: Optional[dict[str, int]] = None
    source: Optional[str] = None


class EventListRequest(BaseModel):
    filter: Optional[EventFilter] = None
    limit: int = 1000
    cursor: Optional[str] = None
    sort: Optional[dict[str, str]] = None
    
    model_config = {"extra": "ignore"}


class EventByIdsRequest(BaseModel):
    items: list[dict[str, Any]]


def _resolve_asset_ids(asset_external_ids: list[str]) -> list[int]:
    """Look up asset IDs from external IDs to support assetExternalIds filter."""
    result = []
    for ext_id in asset_external_ids:
        asset = store.get_asset(ext_id)
        if asset:
            result.append(asset.id)
    return result


def _apply_filter(events: list[CdfEvent], f: Optional[EventFilter]) -> list[CdfEvent]:
    if not f:
        return events
    result = events
    if f.type:
        result = [e for e in result if e.type == f.type]
    if f.subtype:
        result = [e for e in result if e.subtype == f.subtype]

    asset_ids: set[int] = set()
    if f.assetIds:
        asset_ids.update(f.assetIds)
    if f.assetExternalIds:
        asset_ids.update(_resolve_asset_ids(f.assetExternalIds))

    if asset_ids:
        result = [e for e in result if any(aid in asset_ids for aid in e.assetIds)]

    if f.metadata:
        result = [
            e for e in result
            if all(e.metadata.get(k) == v for k, v in f.metadata.items())
        ]
    if f.startTime:
        if "min" in f.startTime:
            result = [e for e in result if e.startTime and e.startTime >= f.startTime["min"]]
        if "max" in f.startTime:
            result = [e for e in result if e.startTime and e.startTime <= f.startTime["max"]]
    if f.source:
        result = [e for e in result if e.source == f.source]
    return result


@router.post("/events/list")
def list_events(body: EventListRequest) -> dict[str, Any]:
    """POST /events/list — mirrors CDF Events.list()."""
    all_events = store.get_events()
    filtered = _apply_filter(all_events, body.filter)

    # Sort by startTime descending by default (most recent first)
    sort_order = body.sort.get("order", "desc").lower() if body.sort else "desc"
    reverse = sort_order == "desc"
    filtered.sort(key=lambda e: e.startTime or 0, reverse=reverse)

    offset = 0
    if body.cursor:
        try:
            offset = int(body.cursor)
        except ValueError:
            offset = 0
    limit = body.limit if body.limit > 0 else len(filtered)
    page = filtered[offset: offset + limit]
    next_cursor = str(offset + limit) if offset + limit < len(filtered) else None
    return {"items": [e.model_dump() for e in page], "nextCursor": next_cursor}


@router.post("/events/byids")
def get_events_by_ids(body: EventByIdsRequest) -> dict[str, Any]:
    """POST /events/byids — mirrors CDF Events.retrieve()."""
    result = []
    for item in body.items:
        ext_id = item.get("externalId")
        if ext_id:
            event = store.get_event(str(ext_id))
            if event:
                result.append(event.model_dump())
    return {"items": result}
