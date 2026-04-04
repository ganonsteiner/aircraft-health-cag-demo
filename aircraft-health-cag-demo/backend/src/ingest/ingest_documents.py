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

DATA_DIR = Path(__file__).parent.parent.parent.parent / "data"
NOW_MS = int(time.time() * 1000)


# Document definitions — which documents link to which assets
DOCUMENT_DEFS: list[dict[str, Any]] = [
    {
        "id": 500,
        "externalId": "DOC-POH-LIMITATIONS",
        "name": "POH — Section 2: Limitations",
        "filename": "poh_limitations.txt",
        "mimeType": "text/plain",
        "linkedAssets": ["N4798E"],
        "metadata": {"type": "poh", "section": "limitations"},
    },
    {
        "id": 501,
        "externalId": "DOC-POH-EMERGENCY",
        "name": "POH — Section 3: Emergency Procedures",
        "filename": "poh_emergency.txt",
        "mimeType": "text/plain",
        "linkedAssets": ["N4798E"],
        "metadata": {"type": "poh", "section": "emergency"},
    },
    {
        "id": 502,
        "externalId": "DOC-POH-SYSTEMS",
        "name": "POH — Section 7: Aircraft Systems",
        "filename": "poh_systems.txt",
        "mimeType": "text/plain",
        "linkedAssets": ["N4798E", "ENGINE-1"],
        "metadata": {"type": "poh", "section": "systems"},
    },
    {
        "id": 503,
        "externalId": "DOC-POH-PERFORMANCE",
        "name": "POH — Section 5: Performance",
        "filename": "poh_performance.txt",
        "mimeType": "text/plain",
        "linkedAssets": ["N4798E"],
        "metadata": {"type": "poh", "section": "performance"},
    },
    {
        "id": 504,
        "externalId": "DOC-AD-80-04-03-R2",
        "name": "AD 80-04-03 R2 — Lycoming Cam/Lifter Inspection",
        "filename": "ad_80-04-03-r2_cam_lifter.txt",
        "mimeType": "text/plain",
        "linkedAssets": ["ENGINE-1", "ENGINE-1-CAM-LIFTERS"],
        "metadata": {"type": "ad", "ad_number": "80-04-03 R2", "aircraft": "Lycoming O-320-H2AD"},
    },
    {
        "id": 505,
        "externalId": "DOC-AD-2001-23-03",
        "name": "AD 2001-23-03 — Cessna 172 Door Post Wiring Inspection",
        "filename": "ad_2001-23-03_doorpost.txt",
        "mimeType": "text/plain",
        "linkedAssets": ["AIRFRAME-1"],
        "metadata": {"type": "ad", "ad_number": "2001-23-03"},
    },
    {
        "id": 506,
        "externalId": "DOC-AD-2011-10-09",
        "name": "AD 2011-10-09 — Cessna Seat Rail/Lock Inspection",
        "filename": "ad_2011-10-09_seat_rail.txt",
        "mimeType": "text/plain",
        "linkedAssets": ["AIRFRAME-1-SEATS-BELTS"],
        "metadata": {"type": "ad", "ad_number": "2011-10-09"},
    },
    {
        "id": 507,
        "externalId": "DOC-AD-90-06-03-R1",
        "name": "AD 90-06-03 R1 — Cessna 172 Exhaust Muffler/Heat Exchanger Inspection",
        "filename": "ad_90-06-03-r1_exhaust.txt",
        "mimeType": "text/plain",
        "linkedAssets": ["ENGINE-1-EXHAUST"],
        "metadata": {"type": "ad", "ad_number": "90-06-03 R1"},
    },
    {
        "id": 508,
        "externalId": "DOC-SB-480F",
        "name": "Lycoming SB 480F — Oil Servicing Recommendations",
        "filename": "sb_480f_oil_service.txt",
        "mimeType": "text/plain",
        "linkedAssets": ["ENGINE-1", "ENGINE-1-OIL-FILTER"],
        "metadata": {"type": "sb", "sb_number": "480F", "manufacturer": "Lycoming"},
    },
]

# Asset externalId → numeric ID map
ASSET_IDS: dict[str, int] = {
    "N4798E": 1, "ENGINE-1": 2, "ENGINE-1-CAM-LIFTERS": 3, "ENGINE-1-MAGS": 4,
    "ENGINE-1-CARB": 5, "ENGINE-1-EXHAUST": 10, "ENGINE-1-OIL-FILTER": 8,
    "AIRFRAME-1": 12, "AIRFRAME-1-SEATS-BELTS": 21,
}


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
    rel_counter = 0

    for doc in DOCUMENT_DEFS:
        filename = doc["filename"]
        filepath = docs_dir / filename
        if not filepath.exists():
            print(f"  [documents]   skipping {filename} — not found")
            continue

        linked_asset_ids = [ASSET_IDS.get(a, 1) for a in doc["linkedAssets"]]
        meta = {**doc["metadata"], "filename": filename}

        files.append(CdfFile(
            id=doc["id"],
            externalId=doc["externalId"],
            name=doc["name"],
            mimeType=doc.get("mimeType", "text/plain"),
            assetIds=linked_asset_ids,
            metadata=meta,
            uploaded=True,
            createdTime=NOW_MS,
            lastUpdatedTime=NOW_MS,
        ))

        # Create LINKED_TO relationship from each linked asset to the document
        for asset_ext_id in doc["linkedAssets"]:
            rel_counter += 1
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
