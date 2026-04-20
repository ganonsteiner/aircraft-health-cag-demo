"""
Asset Ingestion — Southwest Airlines 737 Fleet.

Seeds the asset hierarchy for all 47 aircraft (N287WN, N246WN fully instrumented;
N231WN–N244WN with maintenance records) plus the fleet owner node and shared engine model.

All aircraft (instrumented and placeholder) each have:
  {TAIL}                  — root aircraft asset (Boeing 737-800)
  {TAIL}-ENGINE-1         — CFM56-7B engine #1
  {TAIL}-ENGINE-2         — CFM56-7B engine #2
  {TAIL}-APU              — auxiliary power unit (APS3200)
  {TAIL}-AIRFRAME         — fuselage, wings, empennage, flight controls
  {TAIL}-AVIONICS         — flight management + nav + comm suite
  {TAIL}-LANDING-GEAR     — main and nose gear assembly
  {TAIL}-HYDRAULICS       — hydraulic system A/B/standby
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from dataset import (  # noqa: E402
    INSTRUMENTED_TAILS,
    PLACEHOLDER_TAILS,
    PLACEHOLDER_SPECS,
    ENGINE_EFH_AT_SHOP_VISIT,
    ENGINE2_EFH_AT_SHOP,
    ENGINE_TBO,
    CURRENT_HOBBS_SNAPSHOT,
    FIRST_HOBBS,
    FLEET_OWNER_ID,
    ENGINE_MODEL_EXT_ID,
)

from mock_cdf.store.store import store, Asset  # noqa: E402

NOW_MS = int(time.time() * 1000)

# Instrumented aircraft specs
INSTRUMENTED_SPECS: dict[str, dict[str, Any]] = {
    "N287WN": {
        "model": "Boeing 737-800",
        "serial": "28789",
        "efh": CURRENT_HOBBS_SNAPSHOT["N287WN"],
        "efh_shop": ENGINE_EFH_AT_SHOP_VISIT["N287WN"],
        "base": "PHX",
        "status_note": "NOT_AIRWORTHY — Engine #1 failure, grounded for engine replacement",
    },
    "N246WN": {
        "model": "Boeing 737-800",
        "serial": "28246",
        "efh": CURRENT_HOBBS_SNAPSHOT["N246WN"],
        "efh_shop": ENGINE_EFH_AT_SHOP_VISIT["N246WN"],
        "base": "PHX",
        "status_note": "CAUTION — Engine #1 EGT deviation +14°C, N1 vibration 1.9 units, enhanced monitoring",
    },
    "N220WN": {
        "model": "Boeing 737-800",
        "serial": "28220",
        "efh": CURRENT_HOBBS_SNAPSHOT["N220WN"],
        "efh_shop": 12400.0,
        "base": "PHX",
        "status_note": "AIRWORTHY — All parameters nominal",
    },
    "N235WN": {
        "model": "Boeing 737-800",
        "serial": "28235",
        "efh": CURRENT_HOBBS_SNAPSHOT["N235WN"],
        "efh_shop": 16800.0,
        "base": "PHX",
        "status_note": "AIRWORTHY — All parameters nominal",
    },
}


def _build_fleet_assets() -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []

    # Instrumented aircraft — full component hierarchy
    for i, tail in enumerate(INSTRUMENTED_TAILS):
        spec = INSTRUMENTED_SPECS[tail]
        base_id = i * 10 + 1
        efh = spec["efh"]
        efh_shop = spec["efh_shop"]
        smoh = round(efh - efh_shop, 0)

        # Root aircraft asset
        assets.append({
            "id": base_id,
            "externalId": tail,
            "name": f"{tail} — {spec['model']}",
            "description": f"{spec['model']}, S/N {spec['serial']}. {int(smoh)} EFH SMOH. Based {spec['base']}.",
            "parentExternalId": None,
            "metadata": {
                "aircraft_type": spec["model"],
                "serial_number": spec["serial"],
                "tail_number": tail,
                "base_airport": spec["base"],
                "engine_type": "CFM International CFM56-7B",
                "engine_tbo_efh": str(ENGINE_TBO),
                "engine_smoh": str(int(smoh)),
                "efh_at_shop_visit": str(efh_shop),
                "operator": "Southwest Airlines",
                "status_note": spec["status_note"],
                "max_gross_weight_lbs": "174200",
            },
        })

        # Engine #1 (primary tracked engine)
        eng1_meta: dict[str, str] = {
            "model": "CFM56-7B27E",
            "thrust_lbf": "27300",
            "tbo_efh": str(ENGINE_TBO),
            "smoh_efh": str(int(smoh)),
            "efh_at_shop_visit": str(efh_shop),
            "position": "left_wing",
        }
        if tail == "N287WN":
            eng1_meta["component_status"] = "failed"
        assets.append({
            "id": base_id + 1,
            "externalId": f"{tail}-ENGINE-1",
            "name": f"{tail} — Engine #1 (CFM56-7B)",
            "description": f"CFM56-7B27E, rated 27,300 lbf. {int(smoh)} EFH since last shop visit.",
            "parentExternalId": tail,
            "metadata": eng1_meta,
        })

        # Engine #2
        efh2_shop = ENGINE2_EFH_AT_SHOP[tail]
        smoh2 = round(efh - efh2_shop, 0)
        assets.append({
            "id": base_id + 2,
            "externalId": f"{tail}-ENGINE-2",
            "name": f"{tail} — Engine #2 (CFM56-7B)",
            "description": f"CFM56-7B27E, rated 27,300 lbf. {int(smoh2)} EFH since last shop visit.",
            "parentExternalId": tail,
            "metadata": {
                "model": "CFM56-7B27E",
                "thrust_lbf": "27300",
                "tbo_efh": str(ENGINE_TBO),
                "smoh_efh": str(int(smoh2)),
                "efh_at_shop_visit": str(efh2_shop),
                "position": "right_wing",
            },
        })

        # APU
        assets.append({
            "id": base_id + 3,
            "externalId": f"{tail}-APU",
            "name": f"{tail} — APU (Honeywell APS3200)",
            "description": "Honeywell APS3200 auxiliary power unit, shaft power + bleed air",
            "parentExternalId": tail,
            "metadata": {"model": "APS3200", "manufacturer": "Honeywell"},
        })

        # Airframe
        assets.append({
            "id": base_id + 4,
            "externalId": f"{tail}-AIRFRAME",
            "name": f"{tail} — Airframe",
            "description": "Fuselage, wings, empennage, flight controls, nacelle struts",
            "parentExternalId": tail,
            "metadata": {
                "max_gross_weight_lbs": "174200",
                "wingspan_ft": "117.5",
                "fuselage_stations": "full",
            },
        })

        # Avionics
        assets.append({
            "id": base_id + 5,
            "externalId": f"{tail}-AVIONICS",
            "name": f"{tail} — Avionics Suite",
            "description": "FMC/FMS, dual VHF comm, ILS/VOR, TCAS II, GPWS, ACARS",
            "parentExternalId": tail,
            "metadata": {"fms": "Honeywell FMC-700", "acars": "ARINC 618"},
        })

        # Landing gear
        assets.append({
            "id": base_id + 6,
            "externalId": f"{tail}-LANDING-GEAR",
            "name": f"{tail} — Landing Gear",
            "description": "Main gear (2 × 2-wheel bogies) + nose gear, hydraulic actuation",
            "parentExternalId": tail,
            "metadata": {"configuration": "tricycle", "actuation": "hydraulic"},
        })

        # Hydraulics
        assets.append({
            "id": base_id + 7,
            "externalId": f"{tail}-HYDRAULICS",
            "name": f"{tail} — Hydraulic System",
            "description": "System A (engine #1 + elec pump), System B (engine #2 + elec pump), standby system",
            "parentExternalId": tail,
            "metadata": {"systems": "A; B; standby", "fluid_spec": "Skydrol LD-4"},
        })

    # Placeholder aircraft — full 8-node component hierarchy (same structure as instrumented)
    placeholder_id_base = len(INSTRUMENTED_TAILS) * 10 + 1
    for j, tail in enumerate(PLACEHOLDER_TAILS):
        spec = PLACEHOLDER_SPECS[tail]
        base_id = placeholder_id_base + j * 8
        afh = spec["afh"]
        efh = spec["efh"]

        # Root aircraft asset
        assets.append({
            "id": base_id,
            "externalId": tail,
            "name": f"{tail} — {spec['model']}",
            "description": f"{spec['model']}, based PHX. {afh:,} total airframe hours.",
            "parentExternalId": None,
            "metadata": {
                "aircraft_type": spec["model"],
                "tail_number": tail,
                "base_airport": "PHX",
                "engine_type": "CFM International CFM56-7B",
                "engine_tbo_efh": str(ENGINE_TBO),
                "operator": "Southwest Airlines",
                "total_afh": str(afh),
                "total_efh": str(efh),
            },
        })

        # Root asset engine_smoh so context.py fallback can find it without subtree traversal
        smoh_eng1 = int(efh * 0.35)
        assets[-1]["metadata"]["engine_smoh"] = str(smoh_eng1)

        # Engine #1
        assets.append({
            "id": base_id + 1,
            "externalId": f"{tail}-ENGINE-1",
            "name": f"{tail} — Engine #1 (CFM56-7B)",
            "description": f"CFM56-7B27E, rated 27,300 lbf. {efh:,} total EFH.",
            "parentExternalId": tail,
            "metadata": {
                "model": "CFM56-7B27E",
                "thrust_lbf": "27300",
                "tbo_efh": str(ENGINE_TBO),
                "engine_smoh": str(smoh_eng1),
                "total_efh": str(efh),
                "position": "left_wing",
            },
        })

        # Engine #2
        smoh_eng2 = int(efh * 0.28)
        assets.append({
            "id": base_id + 2,
            "externalId": f"{tail}-ENGINE-2",
            "name": f"{tail} — Engine #2 (CFM56-7B)",
            "description": "CFM56-7B27E, rated 27,300 lbf.",
            "parentExternalId": tail,
            "metadata": {
                "model": "CFM56-7B27E",
                "thrust_lbf": "27300",
                "tbo_efh": str(ENGINE_TBO),
                "smoh_efh": str(smoh_eng2),
                "total_efh": str(efh),
                "position": "right_wing",
            },
        })

        # APU
        assets.append({
            "id": base_id + 3,
            "externalId": f"{tail}-APU",
            "name": f"{tail} — APU (Honeywell APS3200)",
            "description": "Honeywell APS3200 auxiliary power unit, shaft power + bleed air",
            "parentExternalId": tail,
            "metadata": {"model": "APS3200", "manufacturer": "Honeywell"},
        })

        # Airframe
        assets.append({
            "id": base_id + 4,
            "externalId": f"{tail}-AIRFRAME",
            "name": f"{tail} — Airframe",
            "description": "Fuselage, wings, empennage, flight controls, nacelle struts",
            "parentExternalId": tail,
            "metadata": {"max_gross_weight_lbs": "174200", "wingspan_ft": "117.5"},
        })

        # Avionics
        assets.append({
            "id": base_id + 5,
            "externalId": f"{tail}-AVIONICS",
            "name": f"{tail} — Avionics Suite",
            "description": "FMC/FMS, dual VHF comm, ILS/VOR, TCAS II, GPWS, ACARS",
            "parentExternalId": tail,
            "metadata": {"fms": "Honeywell FMC-700", "acars": "ARINC 618"},
        })

        # Landing gear
        assets.append({
            "id": base_id + 6,
            "externalId": f"{tail}-LANDING-GEAR",
            "name": f"{tail} — Landing Gear",
            "description": "Main gear (2 × 2-wheel bogies) + nose gear, hydraulic actuation",
            "parentExternalId": tail,
            "metadata": {"configuration": "tricycle", "actuation": "hydraulic"},
        })

        # Hydraulics
        assets.append({
            "id": base_id + 7,
            "externalId": f"{tail}-HYDRAULICS",
            "name": f"{tail} — Hydraulic System",
            "description": "System A (engine #1 + elec pump), System B (engine #2 + elec pump), standby system",
            "parentExternalId": tail,
            "metadata": {"systems": "A; B; standby", "fluid_spec": "Skydrol LD-4"},
        })

    # Shared engine model node (ID 901, beyond all aircraft IDs)
    assets.append({
        "id": 901,
        "externalId": ENGINE_MODEL_EXT_ID,
        "name": "CFM International CFM56-7B",
        "description": "High-bypass turbofan engine, 22,700–27,300 lbf thrust. Powers Boeing 737 Classic and NG variants.",
        "parentExternalId": None,
        "metadata": {
            "type": "EngineModel",
            "manufacturer": "CFM International",
            "thrust_range_lbf": "22700-27300",
            "bypass_ratio": "5.1",
            "tbo_efh": str(ENGINE_TBO),
        },
    })

    # Fleet owner node (ID 900)
    assets.append({
        "id": 900,
        "externalId": FLEET_OWNER_ID,
        "name": "Southwest Airlines",
        "description": "Major US low-cost carrier. Operates the world's largest Boeing 737 fleet.",
        "parentExternalId": None,
        "metadata": {
            "location": "Dallas Love Field (DAL), Texas",
            "contact": "maintenance@southwestairlines.com",
            "type": "FleetOperator",
            "fleet_size": "47",
        },
    })

    return assets


def ingest_assets() -> None:
    """Seed all fleet asset nodes into the mock CDF store."""
    asset_defs = _build_fleet_assets()
    assets = [
        Asset(
            id=a["id"],
            externalId=a["externalId"],
            name=a["name"],
            description=a.get("description"),
            parentExternalId=a.get("parentExternalId"),
            metadata=a.get("metadata", {}),
            createdTime=NOW_MS,
            lastUpdatedTime=NOW_MS,
        )
        for a in asset_defs
    ]
    store.upsert_assets(assets)
    n_instrumented = len(INSTRUMENTED_TAILS) * 8  # 8 nodes each
    n_placeholder = len(PLACEHOLDER_TAILS) * 8    # full hierarchy for all
    print(f"  Upserted {len(assets)} assets ({n_instrumented} instrumented + {n_placeholder} placeholder × 8 nodes + engine model + fleet owner)")


if __name__ == "__main__":
    ingest_assets()
