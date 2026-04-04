"""
Asset Ingestion — mirrors src/ingest/ingestAssets.ts.

Seeds 29 asset nodes representing the full N4798E aircraft hierarchy into
the mock CDF store. Each asset mirrors a CDF Asset resource — a node in
the Industrial Knowledge Graph with parent/child relationships.

This is the IT/OT/ET convergence point: all sensor data, maintenance events,
and documents will be linked to nodes in this hierarchy.
"""

from __future__ import annotations

import time
from typing import Any

NOW_MS = int(time.time() * 1000)


# Asset definitions — ordered parent-first so IDs resolve correctly
ASSETS: list[dict[str, Any]] = [
    # Root
    {
        "id": 1, "externalId": "N4798E",
        "name": "N4798E — 1978 Cessna 172N Skyhawk",
        "description": "1978 Cessna 172N, S/N 17270798, 28V electrical, based KPHX",
        "metadata": {
            "aircraft_type": "Cessna 172N",
            "year": "1978",
            "serial_number": "17270798",
            "tail_number": "N4798E",
            "base_airport": "KPHX",
            "max_gross_weight_lbs": "2300",
            "engine_smoh": "1450",
        },
    },
    # Engine subsystem
    {
        "id": 2, "externalId": "ENGINE-1",
        "name": "ENGINE-1 — Lycoming O-320-H2AD",
        "description": "Lycoming O-320-H2AD, 160hp, 2000hr TBO, ~1450 SMOH",
        "parentExternalId": "N4798E",
        "metadata": {
            "model": "O-320-H2AD",
            "hp": "160",
            "tbo_hours": "2000",
            "smoh": "1450",
            "fuel_type": "100LL",
        },
    },
    {
        "id": 3, "externalId": "ENGINE-1-CAM-LIFTERS",
        "name": "ENGINE-1-CAM-LIFTERS — Camshaft & Barrel Lifters",
        "description": "H2AD-specific barrel lifters — AD 80-04-03 R2 recurring inspection",
        "parentExternalId": "ENGINE-1",
        "metadata": {"ad_applicable": "80-04-03 R2"},
    },
    {
        "id": 4, "externalId": "ENGINE-1-MAGS",
        "name": "ENGINE-1-MAGS — Slick 4370 Magnetos",
        "description": "Left and right magnetos, 500hr inspection interval",
        "parentExternalId": "ENGINE-1",
        "metadata": {"model": "Slick 4370", "inspection_interval_hrs": "500"},
    },
    {
        "id": 5, "externalId": "ENGINE-1-CARB",
        "name": "ENGINE-1-CARB — Marvel-Schebler MA-4SPA Carburetor",
        "description": "Marvel-Schebler MA-4SPA float carburetor",
        "parentExternalId": "ENGINE-1",
        "metadata": {"model": "Marvel-Schebler MA-4SPA"},
    },
    {
        "id": 6, "externalId": "ENGINE-1-STARTER",
        "name": "ENGINE-1-STARTER — Starter Motor",
        "description": "Gear-driven starter motor",
        "parentExternalId": "ENGINE-1",
        "metadata": {},
    },
    {
        "id": 7, "externalId": "ENGINE-1-ALTERNATOR",
        "name": "ENGINE-1-ALTERNATOR — 28V Alternator",
        "description": "Engine-driven 28V DC alternator",
        "parentExternalId": "ENGINE-1",
        "metadata": {"voltage": "28"},
    },
    {
        "id": 8, "externalId": "ENGINE-1-OIL-FILTER",
        "name": "ENGINE-1-OIL-FILTER — Spin-on Oil Filter",
        "description": "Champion spin-on oil filter, 50hr/4mo change interval per SB 480F",
        "parentExternalId": "ENGINE-1",
        "metadata": {"change_interval_hrs": "50", "sb_reference": "480F"},
    },
    {
        "id": 9, "externalId": "ENGINE-1-SPARK-PLUGS",
        "name": "ENGINE-1-SPARK-PLUGS — Champion REM40E (×8)",
        "description": "8 Champion REM40E spark plugs, rotation at each oil change",
        "parentExternalId": "ENGINE-1",
        "metadata": {"model": "Champion REM40E", "count": "8"},
    },
    {
        "id": 10, "externalId": "ENGINE-1-EXHAUST",
        "name": "ENGINE-1-EXHAUST — Exhaust System & Muffler/Heat Exchanger",
        "description": "AD 90-06-03 R1 recurring inspection for cracks",
        "parentExternalId": "ENGINE-1",
        "metadata": {"ad_applicable": "90-06-03 R1"},
    },
    # Propeller
    {
        "id": 11, "externalId": "PROP-1",
        "name": "PROP-1 — McCauley 1C235/DTM7557 Fixed-Pitch Propeller",
        "description": "McCauley 2-blade fixed-pitch, 2000hr/6yr TBO",
        "parentExternalId": "N4798E",
        "metadata": {"model": "McCauley 1C235/DTM7557", "tbo_hours": "2000", "tbo_years": "6"},
    },
    # Airframe
    {
        "id": 12, "externalId": "AIRFRAME-1",
        "name": "AIRFRAME-1 — Fuselage, Wings, Empennage",
        "description": "1978 Cessna 172N airframe",
        "parentExternalId": "N4798E",
        "metadata": {},
    },
    {
        "id": 13, "externalId": "AIRFRAME-1-FUEL-SYSTEM",
        "name": "AIRFRAME-1-FUEL-SYSTEM — Fuel System",
        "description": "Gravity-feed, two wing tanks, 43 gal usable",
        "parentExternalId": "AIRFRAME-1",
        "metadata": {"capacity_gal": "43", "feed": "gravity"},
    },
    {
        "id": 14, "externalId": "AIRFRAME-1-FUEL-CAPS",
        "name": "AIRFRAME-1-FUEL-CAPS — Fuel Caps (L+R)",
        "description": "Left and right wing tank fuel caps with sealing gaskets",
        "parentExternalId": "AIRFRAME-1-FUEL-SYSTEM",
        "metadata": {},
    },
    {
        "id": 15, "externalId": "AIRFRAME-1-FUEL-SELECTOR",
        "name": "AIRFRAME-1-FUEL-SELECTOR — Fuel Selector Valve",
        "description": "Left/Right/Both/Off selector valve",
        "parentExternalId": "AIRFRAME-1-FUEL-SYSTEM",
        "metadata": {},
    },
    {
        "id": 16, "externalId": "AIRFRAME-1-FUEL-STRAINER",
        "name": "AIRFRAME-1-FUEL-STRAINER — Gascolator (Fuel Strainer)",
        "description": "Main fuel strainer / gascolator, sumped at preflight",
        "parentExternalId": "AIRFRAME-1-FUEL-SYSTEM",
        "metadata": {},
    },
    {
        "id": 17, "externalId": "AIRFRAME-1-LANDING-GEAR",
        "name": "AIRFRAME-1-LANDING-GEAR — Tricycle Fixed Gear",
        "description": "Fixed tricycle gear — nose, left main, right main",
        "parentExternalId": "AIRFRAME-1",
        "metadata": {"type": "fixed tricycle"},
    },
    {
        "id": 18, "externalId": "AIRFRAME-1-NOSE-STRUT",
        "name": "AIRFRAME-1-NOSE-STRUT — Nose Gear Oleo Strut",
        "description": "Nose gear oleo strut, serviced with MIL-H-5606",
        "parentExternalId": "AIRFRAME-1-LANDING-GEAR",
        "metadata": {"fluid": "MIL-H-5606"},
    },
    {
        "id": 19, "externalId": "AIRFRAME-1-BRAKE-SYSTEM",
        "name": "AIRFRAME-1-BRAKE-SYSTEM — Hydraulic Disc Brakes",
        "description": "Hydraulic toe brakes, left and right Cleveland assemblies",
        "parentExternalId": "AIRFRAME-1-LANDING-GEAR",
        "metadata": {"type": "hydraulic disc"},
    },
    {
        "id": 20, "externalId": "AIRFRAME-1-FLIGHT-CONTROLS",
        "name": "AIRFRAME-1-FLIGHT-CONTROLS — Flight Controls",
        "description": "Cable-actuated ailerons, elevator, rudder, manual flaps (Johnson bar), trim",
        "parentExternalId": "AIRFRAME-1",
        "metadata": {"actuation": "cable"},
    },
    {
        "id": 21, "externalId": "AIRFRAME-1-SEATS-BELTS",
        "name": "AIRFRAME-1-SEATS-BELTS — Seats & Harnesses",
        "description": "Front and rear seat belts/harnesses; seat rails per AD 2011-10-09",
        "parentExternalId": "AIRFRAME-1",
        "metadata": {"ad_applicable": "2011-10-09"},
    },
    # Avionics
    {
        "id": 22, "externalId": "AVIONICS-1",
        "name": "AVIONICS-1 — Avionics Stack",
        "description": "Comm, Nav, transponder, ELT, encoder",
        "parentExternalId": "N4798E",
        "metadata": {},
    },
    {
        "id": 23, "externalId": "AVIONICS-1-COMM",
        "name": "AVIONICS-1-COMM — Comm Radio",
        "description": "VHF comm radio",
        "parentExternalId": "AVIONICS-1",
        "metadata": {},
    },
    {
        "id": 24, "externalId": "AVIONICS-1-NAV",
        "name": "AVIONICS-1-NAV — NAV/VOR Radio",
        "description": "VHF navigation radio / VOR receiver",
        "parentExternalId": "AVIONICS-1",
        "metadata": {},
    },
    {
        "id": 25, "externalId": "AVIONICS-1-XPDR",
        "name": "AVIONICS-1-XPDR — Transponder",
        "description": "Mode C transponder — 24-month inspection per 14 CFR 91.413",
        "parentExternalId": "AVIONICS-1",
        "metadata": {"inspection_interval_months": "24", "regulation": "14 CFR 91.413"},
    },
    {
        "id": 26, "externalId": "AVIONICS-1-ELT",
        "name": "AVIONICS-1-ELT — Emergency Locator Transmitter",
        "description": "ELT — 12-month battery/inspection per 14 CFR 91.207",
        "parentExternalId": "AVIONICS-1",
        "metadata": {"inspection_interval_months": "12", "regulation": "14 CFR 91.207"},
    },
    {
        "id": 27, "externalId": "AVIONICS-1-ENCODER",
        "name": "AVIONICS-1-ENCODER — Altitude Encoder",
        "description": "Gray code altitude encoder for Mode C transponder",
        "parentExternalId": "AVIONICS-1",
        "metadata": {},
    },
    # Pitot-static
    {
        "id": 28, "externalId": "PITOT-STATIC-1",
        "name": "PITOT-STATIC-1 — Pitot-Static System",
        "description": "24-month IFR certification per 14 CFR 91.411",
        "parentExternalId": "N4798E",
        "metadata": {"inspection_interval_months": "24", "regulation": "14 CFR 91.411"},
    },
    # Vacuum
    {
        "id": 29, "externalId": "VACUUM-1",
        "name": "VACUUM-1 — Vacuum Pump & Gyro Instruments",
        "description": "Engine-driven vacuum pump, AI and HI. ~500-1000hr pump life.",
        "parentExternalId": "N4798E",
        "metadata": {"typical_life_hrs": "500-1000"},
    },
]


def ingest_assets() -> None:
    """
    Upsert all 29 asset nodes into the mock CDF store via the Assets API.
    Idempotent — safe to run multiple times.
    """
    print("  [assets] Ingesting 29 asset nodes...")

    # Build externalId → numeric id map for parentId resolution
    ext_id_to_int: dict[str, int] = {a["externalId"]: a["id"] for a in ASSETS}

    from mock_cdf.store.store import store as cdf_store  # type: ignore[import]
    from mock_cdf.store.store import Asset as StoreAsset  # type: ignore[import]

    store_assets = []
    for asset in ASSETS:
        parent_ext_id = asset.get("parentExternalId")
        parent_id = ext_id_to_int.get(parent_ext_id) if parent_ext_id else None
        store_assets.append(StoreAsset(
            id=asset["id"],
            externalId=asset["externalId"],
            name=asset["name"],
            description=asset.get("description"),
            parentId=parent_id,
            parentExternalId=parent_ext_id,
            metadata=asset.get("metadata", {}),
            createdTime=NOW_MS,
            lastUpdatedTime=NOW_MS,
        ))
    cdf_store.upsert_assets(store_assets)

    print(f"  [assets] ✓ {len(ASSETS)} assets ingested")


if __name__ == "__main__":
    ingest_assets()
