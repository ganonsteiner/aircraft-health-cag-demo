"""
CDF Store — Python equivalent of mock-cdf/store/index.ts.

Mirrors the Cognite Data Fusion resource model with JSON file persistence.
Each resource type corresponds to a CDF resource: Assets, TimeSeries, Datapoints,
Events, Relationships, and Files. Thread-safe via threading.Lock for concurrent
FastAPI request handling.

State routing: Events and Datapoints are stored in three state-specific files
(events_clean.json, events_caution.json, events_grounded.json) to support the
demo mode selector. Assets, TimeSeries, Relationships, and Files are shared
across all states and stored in single files.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

STORE_DIR = Path(__file__).parent


# ---------------------------------------------------------------------------
# Pydantic models — mirror TypeScript interfaces in mock-cdf/store/index.ts
# ---------------------------------------------------------------------------

class Asset(BaseModel):
    """Mirrors CDF Asset resource type — node in the asset hierarchy."""

    id: int
    externalId: str
    name: str
    description: Optional[str] = None
    parentId: Optional[int] = None
    parentExternalId: Optional[str] = None
    metadata: dict[str, str] = Field(default_factory=dict)
    createdTime: int = 0
    lastUpdatedTime: int = 0


class TimeSeries(BaseModel):
    """Mirrors CDF TimeSeries resource — sensor/metric metadata."""

    id: int
    externalId: str
    name: str
    description: Optional[str] = None
    assetId: Optional[int] = None
    unit: Optional[str] = None
    isString: bool = False
    metadata: dict[str, str] = Field(default_factory=dict)
    createdTime: int = 0
    lastUpdatedTime: int = 0


class Datapoint(BaseModel):
    """Single time series data point — OT sensor reading."""

    timestamp: int
    value: float


class CdfEvent(BaseModel):
    """Mirrors CDF Event resource — maintenance records, squawks, inspections."""

    id: int
    externalId: str
    type: str
    subtype: Optional[str] = None
    description: Optional[str] = None
    startTime: Optional[int] = None
    endTime: Optional[int] = None
    assetIds: list[int] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    source: Optional[str] = None
    createdTime: int = 0
    lastUpdatedTime: int = 0


class Relationship(BaseModel):
    """Mirrors CDF Relationship resource — directed graph edge between resources."""

    externalId: str
    sourceExternalId: str
    sourceType: str
    targetExternalId: str
    targetType: str
    relationshipType: Optional[str] = None
    confidence: float = 1.0
    createdTime: int = 0
    lastUpdatedTime: int = 0


class CdfFile(BaseModel):
    """Mirrors CDF File resource — linked documents (POH, ADs, SBs)."""

    id: int
    externalId: str
    name: str
    mimeType: Optional[str] = None
    assetIds: list[int] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)
    uploaded: bool = True
    createdTime: int = 0
    lastUpdatedTime: int = 0


# ---------------------------------------------------------------------------
# Store singleton
# ---------------------------------------------------------------------------

class CdfStore:
    """
    Thread-safe JSON persistence layer for all CDF resource types.

    State routing: Events and Datapoints are stored in three state-specific
    JSON files. Assets, TimeSeries, Relationships, and Files are shared
    across all states (single files). Calling set_state() switches which
    event/datapoint store is active — used by the demo mode selector.
    """

    STATES = ("clean", "caution", "grounded")

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._assets: dict[str, Asset] = {}
        self._timeseries: dict[str, TimeSeries] = {}
        # Active state's data (switches on set_state)
        self._datapoints: dict[str, list[Datapoint]] = {}
        self._events: dict[str, CdfEvent] = {}
        self._relationships: dict[str, Relationship] = {}
        self._files: dict[str, CdfFile] = {}
        # Multi-state stores — loaded at startup
        self._events_stores: dict[str, dict[str, CdfEvent]] = {}
        self._datapoints_stores: dict[str, dict[str, list[Datapoint]]] = {}
        self._active_state: str = "clean"
        self.init()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _read_json(self, filename: str) -> list[dict[str, Any]]:
        path = STORE_DIR / filename
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text())
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _write_json(self, filename: str, data: list[Any]) -> None:
        path = STORE_DIR / filename
        path.write_text(json.dumps(data, indent=2, default=str))

    def init(self) -> None:
        """
        Load all resource stores from disk into memory.

        Shared stores (assets, timeseries, relationships, files) are loaded
        from single files. State-specific stores (events, datapoints) are
        loaded from {resource}_{state}.json files, falling back to the legacy
        {resource}.json if state files don't exist yet.
        """
        with self._lock:
            self._assets = {
                a["externalId"]: Asset(**a)
                for a in self._read_json("assets.json")
            }
            self._timeseries = {
                ts["externalId"]: TimeSeries(**ts)
                for ts in self._read_json("timeseries.json")
            }
            self._relationships = {
                r["externalId"]: Relationship(**r)
                for r in self._read_json("relationships.json")
            }
            self._files = {
                f["externalId"]: CdfFile(**f)
                for f in self._read_json("files.json")
            }

            # Load state-specific event/datapoint stores
            for state in self.STATES:
                events_file = f"events_{state}.json"
                # Fall back to legacy events.json if state file not present
                events_raw = self._read_json(events_file) or self._read_json("events.json")
                self._events_stores[state] = {
                    e["externalId"]: CdfEvent(**e) for e in events_raw
                }

                dp_file = f"datapoints_{state}.json"
                dp_raw = self._read_json(dp_file) or self._read_json("datapoints.json")
                dp_map: dict[str, list[Datapoint]] = {}
                for entry in dp_raw:
                    ext_id = entry.get("externalId", "")
                    points = [Datapoint(**p) for p in entry.get("datapoints", [])]
                    dp_map[ext_id] = points
                self._datapoints_stores[state] = dp_map

            # Activate the current state
            self._events = self._events_stores.get(self._active_state, {})
            self._datapoints = self._datapoints_stores.get(self._active_state, {})

    def set_state(self, state: str) -> None:
        """
        Switch the active demo state. All subsequent event/datapoint reads
        will use the selected state's data. Thread-safe.
        """
        if state not in self.STATES:
            raise ValueError(f"Invalid state '{state}'. Must be one of: {self.STATES}")
        with self._lock:
            self._active_state = state
            self._events = self._events_stores.get(state, {})
            self._datapoints = self._datapoints_stores.get(state, {})

    def get_active_state(self) -> str:
        return self._active_state

    def _flush_assets(self) -> None:
        self._write_json("assets.json", [a.model_dump() for a in self._assets.values()])

    def _flush_timeseries(self) -> None:
        self._write_json("timeseries.json", [ts.model_dump() for ts in self._timeseries.values()])

    def _flush_datapoints(self) -> None:
        """Flush active state's datapoints to its state-specific file."""
        records = [
            {"externalId": ext_id, "datapoints": [dp.model_dump() for dp in dps]}
            for ext_id, dps in self._datapoints.items()
        ]
        self._write_json(f"datapoints_{self._active_state}.json", records)
        # Keep legacy file in sync for backward compatibility
        if self._active_state == "clean":
            self._write_json("datapoints.json", records)

    def _flush_events(self) -> None:
        """Flush active state's events to its state-specific file."""
        data = [e.model_dump() for e in self._events.values()]
        self._write_json(f"events_{self._active_state}.json", data)
        if self._active_state == "clean":
            self._write_json("events.json", data)

    def _flush_relationships(self) -> None:
        self._write_json("relationships.json", [r.model_dump() for r in self._relationships.values()])

    def _flush_files(self) -> None:
        self._write_json("files.json", [f.model_dump() for f in self._files.values()])

    # ------------------------------------------------------------------
    # Asset methods
    # ------------------------------------------------------------------

    def get_assets(self) -> list[Asset]:
        with self._lock:
            return list(self._assets.values())

    def get_asset(self, external_id: str) -> Optional[Asset]:
        with self._lock:
            return self._assets.get(external_id)

    def get_asset_by_id(self, asset_id: int) -> Optional[Asset]:
        with self._lock:
            return next((a for a in self._assets.values() if a.id == asset_id), None)

    def upsert_asset(self, asset: Asset) -> Asset:
        with self._lock:
            self._assets[asset.externalId] = asset
            self._flush_assets()
            return asset

    def upsert_assets(self, assets: list[Asset]) -> None:
        with self._lock:
            for asset in assets:
                self._assets[asset.externalId] = asset
            self._flush_assets()

    def get_asset_subtree(self, external_id: str) -> list[Asset]:
        """Breadth-first traversal of the asset hierarchy from the given root."""
        with self._lock:
            root = self._assets.get(external_id)
            if not root:
                return []
            result: list[Asset] = []
            queue = [root]
            while queue:
                current = queue.pop(0)
                result.append(current)
                children = [
                    a for a in self._assets.values()
                    if a.parentExternalId == current.externalId
                ]
                queue.extend(children)
            return result

    # ------------------------------------------------------------------
    # TimeSeries methods
    # ------------------------------------------------------------------

    def get_timeseries(self) -> list[TimeSeries]:
        with self._lock:
            return list(self._timeseries.values())

    def get_time_series_by_id(self, external_id: str) -> Optional[TimeSeries]:
        with self._lock:
            return self._timeseries.get(external_id)

    def upsert_time_series(self, ts: TimeSeries) -> TimeSeries:
        with self._lock:
            self._timeseries[ts.externalId] = ts
            self._flush_timeseries()
            return ts

    def upsert_timeseries(self, items: list[TimeSeries]) -> None:
        with self._lock:
            for ts in items:
                self._timeseries[ts.externalId] = ts
            self._flush_timeseries()

    # ------------------------------------------------------------------
    # Datapoint methods
    # ------------------------------------------------------------------

    def get_datapoints(
        self,
        external_id: str,
        start: Optional[int] = None,
        end: Optional[int] = None,
        limit: int = 1000,
    ) -> list[Datapoint]:
        with self._lock:
            points = self._datapoints.get(external_id, [])
            if start is not None:
                points = [p for p in points if p.timestamp >= start]
            if end is not None:
                points = [p for p in points if p.timestamp <= end]
            return points[:limit]

    def get_latest_datapoint(self, external_id: str) -> Optional[Datapoint]:
        with self._lock:
            points = self._datapoints.get(external_id, [])
            if not points:
                return None
            return max(points, key=lambda p: p.timestamp)

    def append_datapoints(self, external_id: str, points: list[Datapoint]) -> None:
        with self._lock:
            if external_id not in self._datapoints:
                self._datapoints[external_id] = []
            self._datapoints[external_id].extend(points)
            self._datapoints_stores[self._active_state] = self._datapoints
            self._flush_datapoints()

    def set_datapoints(self, external_id: str, points: list[Datapoint]) -> None:
        with self._lock:
            self._datapoints[external_id] = points
            self._datapoints_stores[self._active_state] = self._datapoints
            self._flush_datapoints()

    # ------------------------------------------------------------------
    # Event methods
    # ------------------------------------------------------------------

    def get_events(self) -> list[CdfEvent]:
        with self._lock:
            return list(self._events.values())

    def get_event(self, external_id: str) -> Optional[CdfEvent]:
        with self._lock:
            return self._events.get(external_id)

    def upsert_event(self, event: CdfEvent) -> CdfEvent:
        with self._lock:
            self._events[event.externalId] = event
            self._events_stores[self._active_state] = self._events
            self._flush_events()
            return event

    def upsert_events(self, events: list[CdfEvent]) -> None:
        with self._lock:
            for event in events:
                self._events[event.externalId] = event
            self._events_stores[self._active_state] = self._events
            self._flush_events()

    # ------------------------------------------------------------------
    # Relationship methods
    # ------------------------------------------------------------------

    def get_relationships(self) -> list[Relationship]:
        with self._lock:
            return list(self._relationships.values())

    def upsert_relationship(self, rel: Relationship) -> Relationship:
        with self._lock:
            self._relationships[rel.externalId] = rel
            self._flush_relationships()
            return rel

    def upsert_relationships(self, rels: list[Relationship]) -> None:
        with self._lock:
            for rel in rels:
                self._relationships[rel.externalId] = rel
            self._flush_relationships()

    # ------------------------------------------------------------------
    # File methods
    # ------------------------------------------------------------------

    def get_files(self) -> list[CdfFile]:
        with self._lock:
            return list(self._files.values())

    def get_file(self, external_id: str) -> Optional[CdfFile]:
        with self._lock:
            return self._files.get(external_id)

    def upsert_file(self, file: CdfFile) -> CdfFile:
        with self._lock:
            self._files[file.externalId] = file
            self._flush_files()
            return file

    def upsert_files(self, files: list[CdfFile]) -> None:
        with self._lock:
            for f in files:
                self._files[f.externalId] = f
            self._flush_files()

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Wipe all in-memory and on-disk data. Used by reset script."""
        with self._lock:
            self._assets = {}
            self._timeseries = {}
            self._datapoints = {}
            self._events = {}
            self._relationships = {}
            self._files = {}
            self._events_stores = {s: {} for s in self.STATES}
            self._datapoints_stores = {s: {} for s in self.STATES}
            for filename in ["assets.json", "timeseries.json", "relationships.json", "files.json"]:
                self._write_json(filename, [])
            for state in self.STATES:
                self._write_json(f"events_{state}.json", [])
                self._write_json(f"datapoints_{state}.json", [])
            self._write_json("events.json", [])
            self._write_json("datapoints.json", [])

    def get_counts(self) -> dict[str, int]:
        """Return record counts for all resource types (active state)."""
        with self._lock:
            return {
                "assets": len(self._assets),
                "timeseries": len(self._timeseries),
                "datapoints": sum(len(v) for v in self._datapoints.values()),
                "events": len(self._events),
                "relationships": len(self._relationships),
                "files": len(self._files),
            }


# Module-level singleton — imported by all route handlers and the agent
store = CdfStore()
