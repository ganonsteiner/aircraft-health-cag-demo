"""
Assets route — mirrors CDF Assets API.

Endpoints follow the real CDF REST API shape so @cognite/sdk and cognite-sdk
work without modification when pointed at this mock server.
"""

from typing import Any, Optional
from fastapi import APIRouter
from pydantic import BaseModel

from ..store.store import store, Asset

router = APIRouter()


class AssetFilter(BaseModel):
    externalIdPrefix: Optional[str] = None
    parentExternalIds: Optional[list[str]] = None
    parentIds: Optional[list[int]] = None
    assetSubtreeIds: Optional[list[dict[str, str]]] = None
    metadata: Optional[dict[str, str]] = None


class AssetListRequest(BaseModel):
    filter: Optional[AssetFilter] = None
    limit: int = 1000
    cursor: Optional[str] = None
    aggregatedProperties: Optional[list[str]] = None
    
    model_config = {"extra": "ignore"}


class AssetByIdsRequest(BaseModel):
    items: list[dict[str, Any]]


class AssetSearchRequest(BaseModel):
    search: Optional[dict[str, str]] = None
    filter: Optional[AssetFilter] = None
    limit: int = 1000


def _apply_filter(assets: list[Asset], f: Optional[AssetFilter]) -> list[Asset]:
    if not f:
        return assets
    result = assets
    if f.externalIdPrefix:
        result = [a for a in result if a.externalId.startswith(f.externalIdPrefix)]
    if f.parentExternalIds:
        result = [a for a in result if a.parentExternalId in f.parentExternalIds]
    if f.parentIds:
        result = [a for a in result if a.parentId in f.parentIds]
    if f.assetSubtreeIds:
        roots = {entry.get("externalId") for entry in f.assetSubtreeIds if "externalId" in entry}
        all_in_subtree: set[str] = set()
        for root_ext_id in roots:
            subtree = store.get_asset_subtree(root_ext_id)
            all_in_subtree.update(a.externalId for a in subtree)
        result = [a for a in result if a.externalId in all_in_subtree]
    if f.metadata:
        def matches_meta(a: Asset) -> bool:
            return all(a.metadata.get(k) == v for k, v in f.metadata.items())  # type: ignore[union-attr]
        result = [a for a in result if matches_meta(a)]
    return result


@router.post("/assets/list")
def list_assets(body: AssetListRequest) -> dict[str, Any]:
    """POST /assets/list — mirrors CDF Assets.list()."""
    all_assets = store.get_assets()
    filtered = _apply_filter(all_assets, body.filter)
    offset = 0
    if body.cursor:
        try:
            offset = int(body.cursor)
        except ValueError:
            offset = 0
    limit = body.limit if body.limit > 0 else len(filtered)
    page = filtered[offset: offset + limit]
    next_cursor = str(offset + limit) if offset + limit < len(filtered) else None
    return {"items": [a.model_dump() for a in page], "nextCursor": next_cursor}


@router.post("/assets/byids")
def get_assets_by_ids(body: AssetByIdsRequest) -> dict[str, Any]:
    """POST /assets/byids — mirrors CDF Assets.retrieve()."""
    result: list[dict[str, Any]] = []
    for item in body.items:
        ext_id = item.get("externalId") or item.get("external_id")
        asset_id = item.get("id")
        if ext_id:
            asset = store.get_asset(str(ext_id))
        elif asset_id:
            asset = store.get_asset_by_id(int(asset_id))
        else:
            asset = None
        if asset:
            result.append(asset.model_dump())
    return {"items": result}


@router.get("/assets/{asset_id}/subtree")
def get_subtree(asset_id: str) -> dict[str, Any]:
    """GET /assets/{id}/subtree — mirrors CDF Assets subtree traversal."""
    subtree = store.get_asset_subtree(asset_id)
    return {"items": [a.model_dump() for a in subtree]}


@router.post("/assets/search")
def search_assets(body: AssetSearchRequest) -> dict[str, Any]:
    """POST /assets/search — simple name/description text search."""
    all_assets = store.get_assets()
    filtered = _apply_filter(all_assets, body.filter)
    if body.search:
        query = body.search.get("name", "").lower()
        if query:
            filtered = [a for a in filtered if query in a.name.lower()]
    return {"items": [a.model_dump() for a in filtered[: body.limit]]}
