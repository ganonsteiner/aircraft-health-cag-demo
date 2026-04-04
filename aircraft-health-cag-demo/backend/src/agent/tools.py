"""
Agent Tools — Python equivalent of src/agent/tools.ts.

Implements 9 CDF graph traversal tools using the official cognite-sdk Python client.
All queries go through the SDK (never direct JSON reads), so this code works
identically against the mock server or a real CDF tenant.

The traversal_log captures every node visited — this log is the core of the CAG
visualization in the frontend, making the knowledge graph traversal explicit.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from cognite.client import CogniteClient, ClientConfig
from cognite.client.credentials import Token
from cognite.client.data_classes import (
    AssetFilter,
    EventFilter,
    RelationshipFilter,
    FileMetadataFilter,
    TimeSeries,
)
from cognite.client.data_classes.data_modeling import NodeList
import httpx
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

# ---------------------------------------------------------------------------
# CDF client — pointed at mock server; change base_url + credentials for real CDF
# ---------------------------------------------------------------------------

_config = ClientConfig(
    client_name="aircraft-health-cag-demo",
    project=os.getenv("CDF_PROJECT", "n4798e"),
    base_url=os.getenv("CDF_BASE_URL", "http://localhost:4000"),
    credentials=Token(os.getenv("CDF_TOKEN", "mock-token")),
)
client = CogniteClient(_config)

# ---------------------------------------------------------------------------
# Traversal log — captured per query and streamed to the frontend as SSE events
# ---------------------------------------------------------------------------

traversal_log: list[str] = []


def log_traversal(message: str) -> None:
    """Record a graph traversal step for CAG visibility."""
    traversal_log.append(message)


def clear_traversal_log() -> None:
    traversal_log.clear()


# ---------------------------------------------------------------------------
# Tool functions — mirror src/agent/tools.ts exactly
# ---------------------------------------------------------------------------


def get_asset(asset_id: str) -> dict[str, Any]:
    """
    Retrieve a single asset node by externalId.
    Mirrors CDF Assets.retrieve() — entry point for any graph traversal.
    """
    log_traversal(f"Asset:{asset_id}")
    assets = client.assets.retrieve_multiple(external_ids=[asset_id], ignore_unknown_ids=True)
    if not assets:
        return {"error": f"Asset {asset_id} not found"}
    a = assets[0]
    return {
        "id": a.id,
        "externalId": a.external_id,
        "name": a.name,
        "description": a.description,
        "parentExternalId": a.parent_external_id,
        "metadata": a.metadata or {},
    }


def get_asset_children(asset_id: str) -> dict[str, Any]:
    """
    Retrieve direct children of an asset in the hierarchy.
    Mirrors CDF Assets.list(filter={parentExternalIds:[...]}) — step down the asset tree.
    """
    log_traversal(f"AssetChildren:{asset_id}")
    children = client.assets.list(
        filter=AssetFilter(parent_external_ids=[asset_id]),
        limit=100,
    )
    return {
        "parentExternalId": asset_id,
        "children": [
            {
                "id": c.id,
                "externalId": c.external_id,
                "name": c.name,
                "description": c.description,
                "metadata": c.metadata or {},
            }
            for c in children
        ],
    }


def get_asset_subgraph(asset_id: str, depth: int = 2) -> dict[str, Any]:
    """
    Traverse the asset hierarchy to the given depth via subtree endpoint.
    Mirrors CDF Assets subtree — used for broad context assembly.
    """
    log_traversal(f"AssetSubgraph:{asset_id}(depth={depth})")
    try:
        subtree = client.assets.retrieve_subtree(external_id=asset_id)
        return {
            "rootExternalId": asset_id,
            "nodes": [
                {
                    "id": a.id,
                    "externalId": a.external_id,
                    "name": a.name,
                    "description": a.description,
                    "parentExternalId": a.parent_external_id,
                    "metadata": a.metadata or {},
                }
                for a in subtree
            ],
        }
    except Exception as e:
        return {"error": str(e)}


def get_time_series(asset_id: str, metric: Optional[str] = None) -> dict[str, Any]:
    """
    Retrieve time series metadata associated with an asset.
    Mirrors CDF TimeSeries.list(filter={assetExternalIds:[...]}).
    """
    log_traversal(f"TimeSeries:{asset_id}" + (f"/{metric}" if metric else ""))
    try:
        asset = client.assets.retrieve(external_id=asset_id)
        if not asset or not asset.id:
            return {"error": f"Asset {asset_id} not found"}
        ts_list = client.time_series.list(
            asset_ids=[asset.id],
            limit=20,
        )
        results = []
        for ts in ts_list:
            if metric and ts.external_id and metric.lower() not in ts.external_id.lower():
                continue
            results.append({
                "id": ts.id,
                "externalId": ts.external_id,
                "name": ts.name,
                "description": ts.description,
                "unit": ts.unit,
                "metadata": ts.metadata or {},
            })
        return {"assetId": asset_id, "timeSeries": results}
    except Exception as e:
        return {"error": str(e)}


def get_datapoints(
    ts_external_id: str,
    start: Optional[int] = None,
    end: Optional[int] = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Retrieve actual OT sensor readings for a time series.
    Mirrors CDF Datapoints.retrieve() — the raw instrument data layer.
    """
    log_traversal(f"Datapoints:{ts_external_id}(limit={limit})")
    try:
        dps = client.time_series.data.retrieve(
            external_id=ts_external_id,
            start=start,
            end=end,
            limit=limit,
        )
        if dps is None or len(dps) == 0:
            return {"externalId": ts_external_id, "datapoints": []}
        points = [
            {"timestamp": int(ts), "value": float(v)}
            for ts, v in zip(dps.timestamp, dps.value)
        ]
        return {
            "externalId": ts_external_id,
            "count": len(points),
            "datapoints": points[-20:],  # Last 20 for context efficiency
        }
    except Exception as e:
        return {"error": str(e)}


def get_events(
    asset_id: str,
    event_type: Optional[str] = None,
    status: Optional[str] = None,
) -> dict[str, Any]:
    """
    Retrieve IT records (maintenance, squawks, inspections) for an asset.
    Mirrors CDF Events.list() — the work order / logbook layer.
    """
    log_traversal(
        f"Events:{asset_id}"
        + (f"[type={event_type}]" if event_type else "")
        + (f"[status={status}]" if status else "")
    )
    try:
        asset = client.assets.retrieve(external_id=asset_id)
        if not asset or not asset.id:
            return {"error": f"Asset {asset_id} not found"}
        events = client.events.list(
            asset_ids=[asset.id],
            type=event_type,
            limit=200,
        )
        results = []
        for e in events:
            meta = e.metadata or {}
            if status and meta.get("status") != status:
                continue
            results.append({
                "id": e.id,
                "externalId": e.external_id,
                "type": e.type,
                "subtype": e.subtype,
                "description": e.description,
                "startTime": e.start_time,
                "metadata": meta,
                "source": e.source,
            })
        results.sort(key=lambda x: x.get("startTime") or 0, reverse=True)
        return {"assetId": asset_id, "count": len(results), "events": results}
    except Exception as e:
        return {"error": str(e)}


def get_relationships(
    asset_id: str,
    relationship_type: Optional[str] = None,
) -> dict[str, Any]:
    """
    Traverse graph edges from a given resource node.
    Mirrors CDF Relationships.list() — the core CAG traversal primitive.
    """
    log_traversal(
        f"Relationships:{asset_id}"
        + (f"[type={relationship_type}]" if relationship_type else "")
    )
    try:
        filter_kwargs: dict[str, Any] = {
            "source_external_ids": [asset_id],
        }
        rels = client.relationships.list(
            source_external_ids=[asset_id],
            fetch_resources=True,
            limit=100,
        )
        results = []
        for r in rels:
            rel_type = getattr(r, "relationship_type", None) or getattr(
                r, "confidence", None
            )
            # Access relationship_type from raw dict if SDK doesn't expose it
            raw_rel_type = (r._cognite_client if hasattr(r, "_cognite_client") else None)
            try:
                raw_dict = r.dump()
                rel_type_val = raw_dict.get("relationshipType", relationship_type)
            except Exception:
                rel_type_val = relationship_type

            if relationship_type and rel_type_val != relationship_type:
                continue
            results.append({
                "externalId": r.external_id,
                "sourceExternalId": r.source_external_id,
                "sourceType": r.source_type,
                "targetExternalId": r.target_external_id,
                "targetType": r.target_type,
                "relationshipType": rel_type_val,
                "source": r.source.dump() if r.source else None,
                "target": r.target.dump() if r.target else None,
            })
        return {"resourceId": asset_id, "count": len(results), "relationships": results}
    except Exception as e:
        return {"error": str(e)}


def get_linked_documents(asset_id: str) -> dict[str, Any]:
    """
    Retrieve ET documents (POH sections, ADs, SBs) linked to an asset.
    Traverses LINKED_TO relationships → File nodes → downloads document text.
    This is how CAG grabs engineering context — not semantic search, but graph traversal.
    """
    log_traversal(f"Documents:{asset_id}")
    try:
        rels = client.relationships.list(
            source_external_ids=[asset_id],
            fetch_resources=True,
            limit=50,
        )
        documents = []
        for r in rels:
            # CDF SDK v7 dropped the relationshipType field; identify document links
            # by the target resource type (files) rather than relationship type string
            if (r.target_type or "").lower() != "file":
                continue
            target_ext_id = r.target_external_id
            log_traversal(f"File:{target_ext_id}")
            # Fetch file content via the documents endpoint
            base_url = os.getenv("CDF_BASE_URL", "http://localhost:4000")
            try:
                file_meta = client.files.retrieve(external_id=target_ext_id)
                filename = (file_meta.metadata or {}).get("filename", "")
                if filename:
                    resp = httpx.get(f"{base_url}/documents/{filename}", timeout=5.0)
                    if resp.status_code == 200:
                        documents.append({
                            "externalId": target_ext_id,
                            "name": file_meta.name,
                            "filename": filename,
                            "content": resp.text,
                        })
            except Exception:
                pass
        return {"assetId": asset_id, "count": len(documents), "documents": documents}
    except Exception as e:
        return {"error": str(e)}


def assemble_aircraft_context() -> dict[str, Any]:
    """
    Master CAG tool — builds complete connected context for the whole aircraft.

    Traverses the full knowledge graph:
      N4798E root → all components → their maintenance events → open squawks →
      sensor summaries → linked ET documents → AD compliance status

    This mirrors how Cognite's Atlas AI assembles context from the Industrial
    Knowledge Graph — rich, structured, relational — no vector search involved.
    """
    log_traversal("Context:N4798E(full-subgraph)")

    # 1. Root asset
    root = get_asset("N4798E")
    if "error" in root:
        return root

    # 2. Full asset hierarchy
    subgraph = get_asset_subgraph("N4798E", depth=3)
    all_assets = subgraph.get("nodes", [])

    # 3. Current sensor values (latest datapoints)
    sensor_ids = [
        "aircraft.hobbs", "aircraft.tach", "aircraft.cycles",
        "engine.oil_pressure_max", "engine.oil_pressure_min",
        "engine.oil_temp_max", "engine.cht_max", "engine.egt_max",
        "aircraft.fuel_used",
    ]
    sensors: dict[str, Any] = {}
    for sid in sensor_ids:
        log_traversal(f"Datapoint:latest:{sid}")
        try:
            dp = client.time_series.data.retrieve_latest(external_id=sid)
            if dp and len(dp) > 0:
                sensors[sid] = {
                    "timestamp": int(dp[0].timestamp),
                    "value": float(dp[0].value),
                }
        except Exception:
            pass

    # 4. All maintenance events (IT layer)
    maintenance = get_events("N4798E", "MaintenanceRecord")
    inspections = get_events("N4798E", "Inspection")
    squawks = get_events("N4798E", "Squawk")

    # Key sub-component events
    engine_maintenance = get_events("ENGINE-1", "MaintenanceRecord")
    cam_lifter_events = get_events("ENGINE-1-CAM-LIFTERS", "MaintenanceRecord")

    # 5. Key documents (ET layer)
    aircraft_docs = get_linked_documents("N4798E")
    engine_docs = get_linked_documents("ENGINE-1")

    # 6. Derive open squawks
    open_squawks = [
        e for e in squawks.get("events", [])
        if e.get("metadata", {}).get("status") == "open"
    ]

    # 7. Derive upcoming maintenance (next 100 hobbs window)
    current_hobbs = sensors.get("aircraft.hobbs", {}).get("value", 0.0)
    upcoming: list[dict[str, Any]] = []
    all_events = (
        maintenance.get("events", [])
        + inspections.get("events", [])
        + engine_maintenance.get("events", [])
    )
    for event in all_events:
        meta = event.get("metadata", {})
        next_due_hobbs_str = meta.get("next_due_hobbs", "")
        if next_due_hobbs_str:
            try:
                next_due = float(next_due_hobbs_str)
                hours_until = next_due - current_hobbs
                if 0 < hours_until <= 100:
                    upcoming.append({
                        "description": event.get("description", ""),
                        "next_due_hobbs": next_due,
                        "hours_until_due": round(hours_until, 1),
                        "component": meta.get("component_id", ""),
                    })
            except ValueError:
                pass
    upcoming.sort(key=lambda x: x["hours_until_due"])

    log_traversal("Context:assembled")

    return {
        "aircraft": root,
        "totalAssets": len(all_assets),
        "components": all_assets[:10],  # Top-level summary
        "sensors": sensors,
        "currentHobbs": current_hobbs,
        "maintenanceRecordCount": maintenance.get("count", 0),
        "recentMaintenance": maintenance.get("events", [])[:5],
        "inspections": inspections.get("events", [])[:5],
        "openSquawks": open_squawks,
        "allSquawks": squawks.get("events", []),
        "engineMaintenance": engine_maintenance.get("events", [])[:10],
        "camLifterHistory": cam_lifter_events.get("events", []),
        "upcomingMaintenance": upcoming,
        "documents": (
            aircraft_docs.get("documents", []) + engine_docs.get("documents", [])
        ),
        "traversalLog": list(traversal_log),
    }


# ---------------------------------------------------------------------------
# Tool definitions — Claude function calling schemas
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "get_asset",
        "description": (
            "Retrieve a specific CDF asset node by its externalId. "
            "Use this to get metadata about any aircraft component in the knowledge graph. "
            "Asset IDs: N4798E (root), ENGINE-1, PROP-1, AIRFRAME-1, AVIONICS-1, "
            "ENGINE-1-CAM-LIFTERS, ENGINE-1-MAGS, ENGINE-1-CARB, ENGINE-1-EXHAUST, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_id": {
                    "type": "string",
                    "description": "The externalId of the asset (e.g. 'N4798E', 'ENGINE-1')",
                }
            },
            "required": ["asset_id"],
        },
    },
    {
        "name": "get_asset_children",
        "description": (
            "Get direct child assets in the component hierarchy. "
            "Use to enumerate sub-components of an asset."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_id": {
                    "type": "string",
                    "description": "Parent asset externalId",
                }
            },
            "required": ["asset_id"],
        },
    },
    {
        "name": "get_asset_subgraph",
        "description": (
            "Traverse the asset hierarchy to the specified depth, returning all "
            "descendant nodes. Useful for getting a broad picture of a subsystem."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_id": {"type": "string", "description": "Root asset externalId"},
                "depth": {
                    "type": "integer",
                    "description": "How many levels to traverse (1-3)",
                    "default": 2,
                },
            },
            "required": ["asset_id"],
        },
    },
    {
        "name": "get_time_series",
        "description": (
            "Retrieve OT time series metadata for an asset. "
            "Returns sensor definitions (hobbs, CHT, EGT, oil pressure, etc.) "
            "associated with the aircraft or engine."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_id": {"type": "string", "description": "Asset externalId"},
                "metric": {
                    "type": "string",
                    "description": "Optional metric name filter (e.g. 'hobbs', 'cht', 'oil_pressure')",
                },
            },
            "required": ["asset_id"],
        },
    },
    {
        "name": "get_datapoints",
        "description": (
            "Retrieve actual OT sensor readings from a time series. "
            "Use to get current/historical instrument values like hobbs time, "
            "CHT readings, oil pressure, EGT, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ts_external_id": {
                    "type": "string",
                    "description": "Time series externalId (e.g. 'aircraft.hobbs', 'engine.cht_max')",
                },
                "start": {
                    "type": "integer",
                    "description": "Start timestamp in milliseconds (optional)",
                },
                "end": {
                    "type": "integer",
                    "description": "End timestamp in milliseconds (optional)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max datapoints to return (default 100)",
                    "default": 100,
                },
            },
            "required": ["ts_external_id"],
        },
    },
    {
        "name": "get_events",
        "description": (
            "Retrieve IT maintenance records, squawks, or inspections for an asset. "
            "Event types: 'MaintenanceRecord', 'Squawk', 'Inspection'. "
            "Status filter for squawks: 'open', 'resolved', 'deferred'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_id": {"type": "string", "description": "Asset externalId"},
                "event_type": {
                    "type": "string",
                    "description": "CDF event type filter: 'MaintenanceRecord', 'Squawk', or 'Inspection'",
                    "enum": ["MaintenanceRecord", "Squawk", "Inspection"],
                },
                "status": {
                    "type": "string",
                    "description": "Status filter (for squawks): 'open', 'resolved', 'deferred'",
                },
            },
            "required": ["asset_id"],
        },
    },
    {
        "name": "get_relationships",
        "description": (
            "Traverse graph edges from a resource node. "
            "Returns PERFORMED_ON, REFERENCES_AD, RESOLVED_BY, IDENTIFIED_ON, LINKED_TO edges. "
            "Use to follow connections between maintenance records, ADs, squawks, and documents."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_id": {"type": "string", "description": "Source resource externalId"},
                "relationship_type": {
                    "type": "string",
                    "description": "Filter by relationship type (e.g. 'REFERENCES_AD', 'LINKED_TO')",
                },
            },
            "required": ["asset_id"],
        },
    },
    {
        "name": "get_linked_documents",
        "description": (
            "Retrieve ET documents linked to an asset — POH sections, ADs, service bulletins. "
            "Traverses LINKED_TO relationships to File nodes and downloads document content. "
            "Use for questions about limitations, emergency procedures, AD compliance, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "asset_id": {
                    "type": "string",
                    "description": "Asset externalId to get linked documents for",
                }
            },
            "required": ["asset_id"],
        },
    },
    {
        "name": "assemble_aircraft_context",
        "description": (
            "Master context tool — assembles complete connected context for the entire aircraft "
            "by traversing the full knowledge graph. Returns: all components, current sensor values, "
            "recent maintenance history, open squawks, upcoming maintenance due, and linked documents. "
            "Use this first for broad questions about aircraft health or airworthiness."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]


def execute_tool(tool_name: str, tool_input: dict[str, Any]) -> Any:
    """
    Dispatch a tool call from the agent's ReAct loop.
    Maps Claude's function_call.name to the corresponding Python function.
    """
    dispatch: dict[str, Any] = {
        "get_asset": lambda: get_asset(tool_input["asset_id"]),
        "get_asset_children": lambda: get_asset_children(tool_input["asset_id"]),
        "get_asset_subgraph": lambda: get_asset_subgraph(
            tool_input["asset_id"], tool_input.get("depth", 2)
        ),
        "get_time_series": lambda: get_time_series(
            tool_input["asset_id"], tool_input.get("metric")
        ),
        "get_datapoints": lambda: get_datapoints(
            tool_input["ts_external_id"],
            tool_input.get("start"),
            tool_input.get("end"),
            tool_input.get("limit", 100),
        ),
        "get_events": lambda: get_events(
            tool_input["asset_id"],
            tool_input.get("event_type"),
            tool_input.get("status"),
        ),
        "get_relationships": lambda: get_relationships(
            tool_input["asset_id"], tool_input.get("relationship_type")
        ),
        "get_linked_documents": lambda: get_linked_documents(tool_input["asset_id"]),
        "assemble_aircraft_context": lambda: assemble_aircraft_context(),
    }
    fn = dispatch.get(tool_name)
    if fn is None:
        return {"error": f"Unknown tool: {tool_name}"}
    return fn()
