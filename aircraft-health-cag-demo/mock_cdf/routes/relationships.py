"""
Relationships route — mirrors CDF Relationships API.

Relationships are directed graph edges: PERFORMED_ON, REFERENCES_AD, RESOLVED_BY,
IDENTIFIED_ON, LINKED_TO. The agent traverses these to assemble connected context.
"""

from typing import Any, Optional
from fastapi import APIRouter
from pydantic import BaseModel

from ..store.store import store, Relationship

router = APIRouter()


class RelationshipFilter(BaseModel):
    sourceExternalIds: Optional[list[str]] = None
    targetExternalIds: Optional[list[str]] = None
    relationshipTypes: Optional[list[str]] = None
    sourceTypes: Optional[list[str]] = None
    targetTypes: Optional[list[str]] = None


class RelationshipListRequest(BaseModel):
    filter: Optional[RelationshipFilter] = None
    limit: int = 1000
    cursor: Optional[str] = None
    fetchResources: bool = False


class RelationshipByIdsRequest(BaseModel):
    items: list[dict[str, Any]]
    fetchResources: bool = False


def _apply_filter(rels: list[Relationship], f: Optional[RelationshipFilter]) -> list[Relationship]:
    if not f:
        return rels
    result = rels
    if f.sourceExternalIds:
        result = [r for r in result if r.sourceExternalId in f.sourceExternalIds]
    if f.targetExternalIds:
        result = [r for r in result if r.targetExternalId in f.targetExternalIds]
    if f.relationshipTypes:
        result = [r for r in result if r.relationshipType in f.relationshipTypes]
    if f.sourceTypes:
        result = [r for r in result if r.sourceType in f.sourceTypes]
    if f.targetTypes:
        result = [r for r in result if r.targetType in f.targetTypes]
    return result


def _enrich_with_resources(rels: list[Relationship]) -> list[dict[str, Any]]:
    """Fetch the source and target resources and embed them in the relationship."""
    enriched = []
    for rel in rels:
        item: dict[str, Any] = rel.model_dump()
        source = _fetch_resource(rel.sourceExternalId, rel.sourceType)
        target = _fetch_resource(rel.targetExternalId, rel.targetType)
        if source:
            item["source"] = source
        if target:
            item["target"] = target
        enriched.append(item)
    return enriched


def _fetch_resource(ext_id: str, resource_type: str) -> Optional[dict[str, Any]]:
    """Resolve a resource by external ID for the fetchResources enrichment."""
    rt = resource_type.lower()
    if rt == "asset":
        obj = store.get_asset(ext_id)
    elif rt == "event":
        obj = store.get_event(ext_id)
    elif rt == "file":
        obj = store.get_file(ext_id)
    elif rt == "timeseries":
        obj = store.get_time_series_by_id(ext_id)
    else:
        return None
    return obj.model_dump() if obj else None


@router.post("/relationships/list")
def list_relationships(body: RelationshipListRequest) -> dict[str, Any]:
    """POST /relationships/list — mirrors CDF Relationships.list()."""
    all_rels = store.get_relationships()
    filtered = _apply_filter(all_rels, body.filter)
    offset = 0
    if body.cursor:
        try:
            offset = int(body.cursor)
        except ValueError:
            offset = 0
    page = filtered[offset: offset + body.limit]
    next_cursor = str(offset + body.limit) if offset + body.limit < len(filtered) else None
    if body.fetchResources:
        items = _enrich_with_resources(page)
    else:
        items = [r.model_dump() for r in page]
    return {"items": items, "nextCursor": next_cursor}


@router.post("/relationships/byids")
def get_relationships_by_ids(body: RelationshipByIdsRequest) -> dict[str, Any]:
    """POST /relationships/byids — mirrors CDF Relationships.retrieve()."""
    all_rels = store.get_relationships()
    result = []
    for item in body.items:
        ext_id = item.get("externalId")
        if ext_id:
            rel = next((r for r in all_rels if r.externalId == ext_id), None)
            if rel:
                result.append(rel.model_dump())
    if body.fetchResources:
        result = _enrich_with_resources([Relationship(**r) for r in result])
    return {"items": result}
