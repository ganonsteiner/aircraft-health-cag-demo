"""
Document Ingestion — mirrors src/ingest/ingestDocuments.ts.

Walks data/documents/ and creates:
  - CdfFile nodes for each document (POH sections, ADs, SBs)
  - LINKED_TO Relationships connecting documents to relevant asset nodes

This is the ET (Engineering Technology) layer: the authoritative engineering
and regulatory documents. In a real industrial context, these would be CAD
models, P&IDs, technical specifications, and compliance records.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

DATA_DIR = Path(__file__).parent.parent.parent / "data"
NOW_MS = int(time.time() * 1000)


# Document definitions — which documents link to which assets
DOCUMENT_DEFS: list[dict[str, Any]] = [
    {
        "id": 500,
        "externalId": "DOC-POH-LIMITATIONS",
        "name": "FCOM — Chapter 2: Limitations (B737-800 / CFM56-7B)",
        "filename": "poh_limitations.txt",
        "mimeType": "text/plain",
        "linkedAssets": ["ALL_AIRCRAFT"],
        "metadata": {"type": "fcom", "section": "limitations"},
    },
    {
        "id": 501,
        "externalId": "DOC-POH-EMERGENCY",
        "name": "FCOM — Chapter 3: Emergency Procedures (B737-800 / CFM56-7B)",
        "filename": "poh_emergency.txt",
        "mimeType": "text/plain",
        "linkedAssets": ["ALL_AIRCRAFT"],
        "metadata": {"type": "fcom", "section": "emergency"},
    },
    {
        "id": 502,
        "externalId": "DOC-POH-SYSTEMS",
        "name": "FCOM — Chapter 7: Aircraft and Systems Description (B737-800 / CFM56-7B)",
        "filename": "poh_systems.txt",
        "mimeType": "text/plain",
        "linkedAssets": ["ALL_AIRCRAFT", "ENGINE-1"],
        "metadata": {"type": "fcom", "section": "systems"},
    },
    {
        "id": 503,
        "externalId": "DOC-POH-PERFORMANCE",
        "name": "FCOM — Chapter 5: Performance (B737-800 / CFM56-7B)",
        "filename": "poh_performance.txt",
        "mimeType": "text/plain",
        "linkedAssets": ["ALL_AIRCRAFT"],
        "metadata": {"type": "fcom", "section": "performance"},
    },
    {
        "id": 504,
        "externalId": "DOC-AD-2020-14-06",
        "name": "AD 2020-14-06 — CFM56-7B HPT Stage 1 Blade Inspection",
        "filename": "ad_2020-14-06_cfm56_hpt_blade.txt",
        "mimeType": "text/plain",
        "linkedAssets": ["ALL_AIRCRAFT"],
        "metadata": {"type": "ad", "ad_number": "2020-14-06", "aircraft": "Boeing 737-800 / CFM56-7B"},
    },
    {
        "id": 505,
        "externalId": "DOC-AD-2018-23-09",
        "name": "AD 2018-23-09 — CFM56-7B Fan Blade Root Fatigue Inspection",
        "filename": "ad_2018-23-09_cfm56_fan_blade.txt",
        "mimeType": "text/plain",
        "linkedAssets": ["ALL_AIRCRAFT"],
        "metadata": {"type": "ad", "ad_number": "2018-23-09", "aircraft": "Boeing 737-800 / CFM56-7B"},
    },
    {
        "id": 506,
        "externalId": "DOC-AD-2015-08-12",
        "name": "AD 2015-08-12 — Boeing 737-800 Emergency Exit Row Floor Track",
        "filename": "ad_2015-08-12_737_exit_floor_track.txt",
        "mimeType": "text/plain",
        "linkedAssets": ["ALL_AIRCRAFT"],
        "metadata": {"type": "ad", "ad_number": "2015-08-12", "aircraft": "Boeing 737-800"},
    },
]


def _expand_template_assets_to_fleet(linked_templates: list[str]) -> list[str]:
    """
    Expand symbolic asset IDs to all fleet tails.
    ALL_AIRCRAFT → every aircraft root asset.
    ENGINE-1     → each tail's Engine #1 sub-asset.
    """
    from dataset import TAILS  # type: ignore[import]

    expanded: list[str] = []
    for tmpl in linked_templates:
        if tmpl == "ALL_AIRCRAFT":
            expanded.extend(TAILS)
        elif tmpl == "ENGINE-1":
            expanded.extend(f"{t}-ENGINE-1" for t in TAILS)
        else:
            expanded.append(tmpl)
    seen: set[str] = set()
    out: list[str] = []
    for x in expanded:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def ingest_documents() -> None:
    """
    Create File nodes and LINKED_TO Relationships for all ET documents.
    Idempotent — files and relationships are overwritten by externalId.
    """
    from mock_cdf.store.store import store, CdfFile, Relationship  # type: ignore[import]

    docs_dir = DATA_DIR / "documents"
    if not docs_dir.exists():
        print("  [documents] ✗ data/documents/ not found")
        return

    files: list[CdfFile] = []
    relationships: list[Relationship] = []

    for doc in DOCUMENT_DEFS:
        filename = doc["filename"]
        filepath = docs_dir / filename
        if not filepath.exists():
            print(f"  [documents]   skipping {filename} — not found")
            continue

        expanded_assets = _expand_template_assets_to_fleet(list(doc["linkedAssets"]))
        asset_numeric_ids: list[int] = []
        for ext in expanded_assets:
            a = store.get_asset(ext)
            if a:
                asset_numeric_ids.append(a.id)

        meta = {**doc["metadata"], "filename": filename}

        files.append(CdfFile(
            id=doc["id"],
            externalId=doc["externalId"],
            name=doc["name"],
            mimeType=doc.get("mimeType", "text/plain"),
            assetIds=sorted(set(asset_numeric_ids)),
            metadata=meta,
            uploaded=True,
            createdTime=NOW_MS,
            lastUpdatedTime=NOW_MS,
        ))

        for asset_ext_id in expanded_assets:
            if not store.get_asset(asset_ext_id):
                continue
            relationships.append(Relationship(
                externalId=f"REL-LINKED-{doc['externalId']}-{asset_ext_id}",
                sourceExternalId=asset_ext_id,
                sourceType="asset",
                targetExternalId=doc["externalId"],
                targetType="file",
                relationshipType="LINKED_TO",
                createdTime=NOW_MS,
                lastUpdatedTime=NOW_MS,
            ))

    store.upsert_files(files)
    store.upsert_relationships(relationships)
    print(f"  [documents] ✓ {len(files)} File nodes and {len(relationships)} LINKED_TO relationships ingested")


if __name__ == "__main__":
    ingest_documents()
