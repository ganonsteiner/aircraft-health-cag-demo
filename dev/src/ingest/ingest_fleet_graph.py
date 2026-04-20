"""
Fleet Graph Ingestion — extended knowledge graph nodes and relationships.

Creates the fleet-level knowledge graph structure:
  - FleetOwner node (Southwest_Airlines)
  - OperationalPolicy nodes (borescope, EGT monitoring, N1 vibration, A-check, AD compliance, MEL)
  - GOVERNED_BY: all 47 aircraft → FleetOwner
  - HAS_POLICY: FleetOwner → each policy
  - IS_TYPE: every {TAIL}-ENGINE-1 → ENGINE_MODEL_CFM56_7B (all 47 aircraft)
  - HAS_COMPONENT: explicit hierarchy edges for all 47 aircraft
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from mock_cdf.store.store import (  # type: ignore[import]
    store,
    Relationship,
    OperationalPolicy,
    FleetOwner,
)
from dataset import (  # type: ignore[import]
    TAILS,
    INSTRUMENTED_TAILS,
    PLACEHOLDER_TAILS,
    OPERATIONAL_POLICIES,
    FLEET_OWNER,
    FLEET_OWNER_ID,
    ENGINE_MODEL_EXT_ID,
)

NOW_MS = int(time.time() * 1000)


def ingest_fleet_graph() -> None:
    """Ingest all fleet-level graph nodes and relationships."""

    fleet_owners = [FleetOwner(**FLEET_OWNER)]
    store.upsert_fleet_owners(fleet_owners)
    print(f"  Upserted {len(fleet_owners)} fleet owner nodes")

    policies = [OperationalPolicy(**p) for p in OPERATIONAL_POLICIES]
    store.upsert_policies(policies)
    print(f"  Upserted {len(policies)} operational policy nodes")

    rels: list[Relationship] = []

    # All 12 aircraft GOVERNED_BY Southwest_Airlines
    for tail in TAILS:
        rels.append(Relationship(
            externalId=f"REL-{tail}-GOVERNED_BY-{FLEET_OWNER_ID}",
            sourceExternalId=tail,
            sourceType="asset",
            targetExternalId=FLEET_OWNER_ID,
            targetType="asset",
            relationshipType="GOVERNED_BY",
            createdTime=NOW_MS,
            lastUpdatedTime=NOW_MS,
        ))

    # FleetOwner HAS_POLICY for each policy
    for policy in OPERATIONAL_POLICIES:
        pol_id = policy["externalId"]
        rels.append(Relationship(
            externalId=f"REL-{FLEET_OWNER_ID}-HAS_POLICY-{pol_id}",
            sourceExternalId=FLEET_OWNER_ID,
            sourceType="asset",
            targetExternalId=pol_id,
            targetType="asset",
            relationshipType="HAS_POLICY",
            createdTime=NOW_MS,
            lastUpdatedTime=NOW_MS,
        ))

    # All aircraft ENGINE-1 IS_TYPE CFM56-7B
    for tail in TAILS:
        eng1 = f"{tail}-ENGINE-1"
        rels.append(Relationship(
            externalId=f"REL-{eng1}-IS_TYPE-{ENGINE_MODEL_EXT_ID}",
            sourceExternalId=eng1,
            sourceType="asset",
            targetExternalId=ENGINE_MODEL_EXT_ID,
            targetType="asset",
            relationshipType="IS_TYPE",
            createdTime=NOW_MS,
            lastUpdatedTime=NOW_MS,
        ))

    # HAS_COMPONENT hierarchy for all 47 aircraft
    component_suffixes = [
        "-ENGINE-1", "-ENGINE-2", "-APU",
        "-AIRFRAME", "-AVIONICS", "-LANDING-GEAR", "-HYDRAULICS",
    ]
    for tail in TAILS:
        for suffix in component_suffixes:
            comp_id = f"{tail}{suffix}"
            rels.append(Relationship(
                externalId=f"REL-{tail}-HAS_COMPONENT-{comp_id}",
                sourceExternalId=tail,
                sourceType="asset",
                targetExternalId=comp_id,
                targetType="asset",
                relationshipType="HAS_COMPONENT",
                createdTime=NOW_MS,
                lastUpdatedTime=NOW_MS,
            ))

    store.upsert_relationships(rels)
    print(f"  Upserted {len(rels)} fleet graph relationships")
    print(f"    GOVERNED_BY: {len(TAILS)} edges (all aircraft → FleetOwner)")
    print(f"    HAS_POLICY: {len(OPERATIONAL_POLICIES)} edges (FleetOwner → policy)")
    print(f"    IS_TYPE: {len(TAILS)} edges (engine-1 → {ENGINE_MODEL_EXT_ID})")
    has_component_count = sum(1 for r in rels if r.relationshipType == "HAS_COMPONENT")
    print(f"    HAS_COMPONENT: {has_component_count} edges (all aircraft → components)")
