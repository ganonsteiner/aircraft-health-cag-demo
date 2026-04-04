"""
N4798E Aircraft Health Demo — Master Story Dataset.

All maintenance history, flight data, and state definitions live here as pure
Python constants. Transform scripts read from this file to produce CSV inputs
for the ingestion pipeline.

Hobbs backbone (airframe cumulative hours):
  1978 delivery:        8.0
  1987 top overhaul:   1200.0 (engine had 1192 SMOH)
  1995 major OH #1:    2100.0 (engine had 2092 SMOH, ~90hr past TBO)
  2009 major OH #2:    3350.0 (engine SMOH resets — this is the baseline for
                                SMOH calculations in the current era)
  Oct 8 2025 annual:   4801.0 (last shared maintenance event)
  Oct 15 2025 oil chg: 4808.0 (next due: 4858.0)
  Divergence point:    ~4820  (November 1, 2025)

Three demo states diverge at Nov 1 2025 and lead to different April 3 2026 outcomes.
"""
from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Mechanic roster
# ---------------------------------------------------------------------------

_MECHS: dict[str, str] = {
    "torres":  "Cactus Aviation Services — Mike Torres, A&P/IA #3847291",
    "wheeler": "Desert Aero Maintenance — James Wheeler, A&P/IA #2918473",
    "martin":  "Sky Harbor Aircraft Services — Tom Martin, A&P/IA #2234719",
    "nguyen":  "Desert Sky Aviation — Kevin Nguyen, A&P #1987654",
    "romero":  "Phoenix Aire Maintenance — Carlos Romero, A&P/IA #1456789",
    "baker":   "Phoenix Aire Maintenance — Dave Baker, A&P/IA #0987321",
    "chen":    "AZ Aviation Overhaul — Linda Chen, A&P/IA #3561028",
}


def _M(year: int, *, overhaul: bool = False) -> tuple[str, str]:
    """Return (mechanic_name, inspector_name) for the given year."""
    if overhaul:
        return _MECHS["chen"], _MECHS["chen"]
    if year >= 2015:
        return _MECHS["torres"], _MECHS["torres"]
    if year >= 2005:
        return _MECHS["wheeler"], _MECHS["wheeler"]
    if year >= 1995:
        return _MECHS["martin"], _MECHS["martin"]
    if year >= 1988:
        return _MECHS["nguyen"], _MECHS["nguyen"]
    if year >= 1982:
        return _MECHS["romero"], _MECHS["romero"]
    return _MECHS["baker"], _MECHS["baker"]


# ---------------------------------------------------------------------------
# Maintenance record builder
# ---------------------------------------------------------------------------

def R(
    date: str,
    component_id: str,
    maintenance_type: str,
    description: str,
    hobbs: float,
    *,
    tach: float = 0.0,
    next_due_hobbs: str = "",
    next_due_date: str = "",
    mechanic: str = "",
    inspector: str = "",
    ad_reference: str = "",
    sb_reference: str = "",
    squawk_id: str = "",
    resolved_by: str = "",
    parts_replaced: str = "",
    labor_hours: float = 1.0,
    signoff_type: str = "return_to_service",
    severity: str = "",
    status: str = "",
) -> dict[str, Any]:
    """Build a maintenance record dict matching the CSV schema."""
    year = int(date[:4])
    m, ins = _M(year)
    if mechanic:
        m = mechanic
    if inspector:
        ins = inspector
    return {
        "date": date,
        "component_id": component_id,
        "maintenance_type": maintenance_type,
        "description": description,
        "hobbs_at_service": round(hobbs, 1),
        "tach_at_service": round(tach if tach else hobbs * 0.92, 1),
        "next_due_hobbs": next_due_hobbs,
        "next_due_date": next_due_date,
        "mechanic": m,
        "inspector": ins,
        "ad_reference": ad_reference,
        "sb_reference": sb_reference,
        "squawk_id": squawk_id,
        "resolved_by": resolved_by,
        "parts_replaced": parts_replaced,
        "labor_hours": labor_hours,
        "signoff_type": signoff_type,
        "severity": severity,
        "status": status,
    }


# ---------------------------------------------------------------------------
# Flight record builder
# ---------------------------------------------------------------------------

def F(
    date: str,
    route: str,
    hobbs_start: float,
    hobbs_end: float,
    *,
    oil_pressure_min: float = 68.0,
    oil_pressure_max: float = 80.0,
    oil_temp_max: float = 195.0,
    cht_max: float = 370.0,
    egt_max: float = 1320.0,
    pilot_notes: str = "",
) -> dict[str, Any]:
    """Build a flight record dict matching the CSV schema."""
    duration = round(hobbs_end - hobbs_start, 1)
    fuel = round(duration * 8.2, 1)          # ~8.2 gal/hr for O-320
    tach_start = round(hobbs_start * 0.92, 1)
    tach_end = round(hobbs_end * 0.92, 1)
    return {
        "timestamp": f"{date}T13:00:00",
        "hobbs_start": round(hobbs_start, 1),
        "hobbs_end": round(hobbs_end, 1),
        "tach_start": tach_start,
        "tach_end": tach_end,
        "cycles": 1,
        "oil_pressure_min": oil_pressure_min,
        "oil_pressure_max": oil_pressure_max,
        "oil_temp_max": oil_temp_max,
        "cht_max": cht_max,
        "egt_max": egt_max,
        "fuel_used_gal": fuel,
        "route": route,
        "pilot_notes": pilot_notes,
    }


# ===========================================================================
# MAINTENANCE_SHARED — full 1978 through Nov 1 2025
# All three demo states share this history identically.
# ===========================================================================

MAINTENANCE_SHARED: list[dict[str, Any]] = [

    # ── 1978 ─────────────────────────────────────────────────────────────────
    R("1978-11-15", "AIRCRAFT", "annual",
      "Initial annual inspection at delivery. Aircraft new — all systems serviceable. "
      "Altimeter, transponder, static system checked. Engine runup normal. Return to service.",
      hobbs=12.0, next_due_date="1979-11-15", labor_hours=8.0,
      signoff_type="inspection_approval"),

    R("1978-12-01", "ENGINE-1-OIL-FILTER", "oil_change",
      "Initial oil and filter change at 25hr break-in. Drained break-in oil (Aeroshell 100 "
      "straight weight), refilled with Aeroshell 15W-50. Champion filter cut and inspected — "
      "no abnormal metal. Normal break-in fines only.",
      hobbs=25.0, next_due_hobbs="75", next_due_date="1979-04-01",
      sb_reference="480F", labor_hours=0.8),

    # ── 1979 ─────────────────────────────────────────────────────────────────
    R("1979-05-01", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil and filter change. Aeroshell 15W-50. Filter cut — no abnormal metal.",
      hobbs=78.0, next_due_hobbs="128", next_due_date="1979-09-01",
      sb_reference="480F", labor_hours=0.8),

    R("1979-11-20", "AIRCRAFT", "annual",
      "Annual inspection. All ADs reviewed and complied. Compression check: 72/80, 74/80, "
      "70/80, 76/80. Magneto timing 25° BTC. Oil change and new filter. Return to service.",
      hobbs=155.0, next_due_date="1980-11-20", labor_hours=10.0,
      signoff_type="inspection_approval"),

    # ── 1980 ─────────────────────────────────────────────────────────────────
    R("1980-02-15", "ENGINE-1-CAM-LIFTERS", "ad_compliance",
      "AD 80-04-03 R2 initial compliance — Lycoming O-320-H2AD camshaft and barrel lifter "
      "inspection. Engine partially disassembled. Camshaft inspected for spalling, all 8 "
      "barrel-type lifters inspected and measured. No abnormal wear found. Recurring "
      "inspection required at 100hr intervals per AD.",
      hobbs=215.0, ad_reference="80-04-03 R2", next_due_hobbs="315",
      mechanic=_MECHS["baker"], inspector=_MECHS["baker"],
      parts_replaced="None (inspection only)", labor_hours=6.0,
      signoff_type="conformity_statement"),

    R("1980-11-10", "AIRCRAFT", "annual",
      "Annual inspection. AD 80-04-03 R2 cam/lifter recurring check — no abnormal wear. "
      "Compressions 70/80, 72/80, 74/80, 70/80. Spark plugs cleaned and rotated. "
      "Brakes serviceable. Return to service.",
      hobbs=295.0, next_due_date="1981-11-10", ad_reference="80-04-03 R2",
      labor_hours=10.0, signoff_type="inspection_approval"),

    # ── 1981 ─────────────────────────────────────────────────────────────────
    R("1981-04-01", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil and filter change. Aeroshell 15W-50. Filter cut — no abnormal metal. "
      "Oil analysis sent to Blackstone Labs — all parameters normal.",
      hobbs=365.0, next_due_hobbs="415", next_due_date="1981-08-01",
      sb_reference="480F", labor_hours=0.8),

    R("1981-11-15", "AIRCRAFT", "annual",
      "Annual inspection. AD 80-04-03 R2 cam/lifter recurring check — lifter #3 shows "
      "minor polishing but within Lycoming limits. Documented. All other systems serviceable.",
      hobbs=435.0, next_due_date="1982-11-15", ad_reference="80-04-03 R2",
      labor_hours=11.0, signoff_type="inspection_approval"),

    # ── 1982 ─────────────────────────────────────────────────────────────────
    R("1982-04-01", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil and filter change. Aeroshell 15W-50. Filter cut — no abnormal metal.",
      hobbs=502.0, next_due_hobbs="552", sb_reference="480F", labor_hours=0.8),

    R("1982-11-20", "AIRCRAFT", "annual",
      "Annual inspection. Compressions 68/80, 70/80, 72/80, 69/80 — slightly lower but "
      "within airworthy limits. Mag timing checked and adjusted to 25° BTC. Left brake "
      "caliper rebuilt, new pads installed.",
      hobbs=570.0, next_due_date="1983-11-20",
      parts_replaced="Left brake pads, caliper seal kit",
      labor_hours=12.0, signoff_type="inspection_approval"),

    # ── 1983 ─────────────────────────────────────────────────────────────────
    R("1983-05-20", "AIRFRAME-1-BRAKE-SYSTEM", "squawk",
      "Left brake dragging on rollout — taxiing requires right brake compensation. "
      "Caliper likely seized. Non-grounding (serviceable for flight). Filed for maintenance.",
      hobbs=618.0, squawk_id="SQ-1983-BRAKE",
      severity="non-grounding", status="resolved",
      signoff_type="return_to_service"),

    R("1983-06-05", "AIRFRAME-1-BRAKE-SYSTEM", "repair",
      "SQUAWK RESOLVED (SQ-1983-BRAKE): Left brake caliper disassembled — piston seized "
      "from corrosion. Piston freed, new O-ring seals, new brake pads installed. Both "
      "brakes bled and tested. Equal braking force confirmed.",
      hobbs=618.5, resolved_by="SQ-1983-BRAKE",
      parts_replaced="Brake caliper overhaul kit, left brake pads",
      labor_hours=2.5),

    R("1983-11-18", "AIRCRAFT", "annual",
      "Annual inspection. AD 80-04-03 R2 cam/lifter inspection — lifter #3 wear slightly "
      "increased, still within Lycoming limits. Will monitor at next annual. "
      "Compressions 68/80, 70/80, 70/80, 67/80.",
      hobbs=705.0, next_due_date="1984-11-18", ad_reference="80-04-03 R2",
      labor_hours=11.0, signoff_type="inspection_approval"),

    # ── 1984 ─────────────────────────────────────────────────────────────────
    R("1984-04-15", "ENGINE-1-MAGS", "inspection",
      "500hr magneto inspection. Left and right Slick 4370 magnetos removed, caps and "
      "rotors inspected, points replaced, timing reset to 25° BTC. Both magnetos test "
      "within manufacturer limits.",
      hobbs=760.0, next_due_hobbs="1260",
      parts_replaced="Magneto points (2 sets), condensers (2)", labor_hours=3.0),

    R("1984-11-22", "AIRCRAFT", "annual",
      "Annual inspection. Compressions 64/80, 70/80, 62/80, 66/80 — cylinder 3 notable "
      "decline. Borescoped — slight scoring on cylinder wall. Top overhaul discussed with "
      "owner. AD 80-04-03 R2 cam/lifter — lifter #3 wear documented, within limits.",
      hobbs=835.0, next_due_date="1985-11-22", ad_reference="80-04-03 R2",
      labor_hours=12.0, signoff_type="inspection_approval"),

    # ── 1985 ─────────────────────────────────────────────────────────────────
    R("1985-11-20", "AIRCRAFT", "annual",
      "Annual inspection. Compressions: 64/80, 70/80, 60/80, 68/80. Top overhaul "
      "required — cylinders 1 and 3 below limits. Referred to AZ Aviation Overhaul "
      "for cylinder work. Oil consumption 1 qt/8hr.",
      hobbs=965.0, next_due_date="1986-11-20",
      labor_hours=11.0, signoff_type="inspection_approval"),

    # ── 1986 ─────────────────────────────────────────────────────────────────
    R("1986-11-18", "AIRCRAFT", "annual",
      "Annual inspection. Top overhaul scheduled for Q1 1987. Compressions 62/80, "
      "70/80, 60/80, 66/80. Owner approved shop work to proceed.",
      hobbs=1085.0, next_due_date="1987-11-18",
      labor_hours=11.0, signoff_type="inspection_approval"),

    # ── 1987 — Top Overhaul ───────────────────────────────────────────────────
    R("1987-02-20", "ENGINE-1-CAM-LIFTERS", "top_overhaul",
      "TOP OVERHAUL — AZ Aviation Overhaul. Cylinders 1 and 3 removed and chrome bored, "
      "new rings, new valve guides and seats. All 8 O-320-H2AD barrel lifters replaced "
      "with current Lycoming-approved design. Camshaft reground. Cylinders 2 and 4 "
      "honed and new rings. All valve springs replaced. Crankshaft inspected per AD "
      "80-04-03 R2 — no cracks, no regrind required. Engine ground run 2 hours. "
      "Post-overhaul compressions: 76/80, 78/80, 76/80, 78/80.",
      hobbs=1200.0,
      mechanic=_MECHS["chen"], inspector=_MECHS["chen"],
      ad_reference="80-04-03 R2",
      parts_replaced="Cylinders 1 & 3 (chrome bore), 8 barrel lifters, camshaft regrind, "
                     "valve train components all cylinders",
      labor_hours=32.0, signoff_type="return_to_service"),

    R("1987-11-15", "AIRCRAFT", "annual",
      "Annual post-top-overhaul. Engine at 265hr SMOH since top OH. Compressions "
      "76/80, 78/80, 76/80, 78/80 — excellent. AD 80-04-03 R2 inspection — new lifters "
      "show normal break-in wear, all within limits.",
      hobbs=1210.0, next_due_date="1988-11-15", ad_reference="80-04-03 R2",
      labor_hours=10.0, signoff_type="inspection_approval"),

    # ── 1988 ─────────────────────────────────────────────────────────────────
    R("1988-11-10", "AIRCRAFT", "annual",
      "Annual inspection. Compressions 74/80, 76/80, 74/80, 76/80. Oil analysis sent — "
      "slightly elevated iron (18 ppm vs 12 baseline), Lycoming aware — H2AD pattern. "
      "Monitoring continues.",
      hobbs=1340.0, next_due_date="1989-11-10",
      labor_hours=10.0, signoff_type="inspection_approval"),

    # ── 1989 ─────────────────────────────────────────────────────────────────
    R("1989-05-01", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil and filter change. Aeroshell 15W-50. Filter cut — no abnormal metal. "
      "Oil normal color.",
      hobbs=1398.0, next_due_hobbs="1448", sb_reference="480F", labor_hours=0.8),

    R("1989-11-08", "AIRCRAFT", "annual",
      "Annual inspection. TT approaching 1500hr since top overhaul baseline. Engine "
      "planning for future major overhaul underway. Compressions acceptable. Vacuum "
      "pump replaced preventively at ~1450hr TT (original 1978 unit).",
      hobbs=1465.0, next_due_date="1990-11-08",
      parts_replaced="Vacuum pump (original 1978 unit)", labor_hours=10.0,
      signoff_type="inspection_approval"),

    # ── 1990 ─────────────────────────────────────────────────────────────────
    R("1990-11-05", "AIRCRAFT", "annual",
      "Annual inspection. Engine approaching 1970hr TT since delivery. Compressions: "
      "70/80, 72/80, 68/80, 70/80 — declining. Owner elected to continue with enhanced "
      "monitoring. Oil consumption 1 qt/6hr.",
      hobbs=1580.0, next_due_date="1991-11-05",
      labor_hours=10.0, signoff_type="inspection_approval"),

    R("1990-12-01", "ENGINE-1-EXHAUST", "ad_compliance",
      "AD 90-06-03 R1 initial compliance — exhaust muffler/heat exchanger inspection "
      "for cracks (CO poisoning prevention). Muffler removed, inspected internally with "
      "borescope and externally with dye penetrant. No cracks found. Heat exchanger "
      "baffles intact. Return to service.",
      hobbs=1595.0, ad_reference="90-06-03 R1", next_due_hobbs="1845",
      labor_hours=3.0, signoff_type="conformity_statement"),

    # ── 1991–1994 ─────────────────────────────────────────────────────────────
    R("1991-11-01", "AIRCRAFT", "annual",
      "Annual inspection. Engine at approximately 1990hr TT from delivery. Major overhaul "
      "planning underway — compressions 68/80, 70/80, 66/80, 68/80. Oil consumption "
      "1 qt/5hr. Referred to AZ Aviation Overhaul for pre-overhaul evaluation.",
      hobbs=1695.0, next_due_date="1992-11-01",
      labor_hours=11.0, signoff_type="inspection_approval"),

    R("1992-11-10", "AIRCRAFT", "annual",
      "Annual inspection. Engine ~2100hr TT from delivery, past TBO. Compressions "
      "declining but serviceable. AD 80-04-03 R2 cam/lifter — wear accelerating. "
      "Major overhaul now firm for early 1995 to allow budget planning.",
      hobbs=1805.0, next_due_date="1993-11-10", ad_reference="80-04-03 R2",
      labor_hours=10.0, signoff_type="inspection_approval"),

    R("1993-11-08", "AIRCRAFT", "annual",
      "Annual inspection. Engine ~2200hr from delivery. Owner confirmed overhaul timeline "
      "for spring 1995. Compressions 66/80, 68/80, 64/80, 66/80. Oil consumption 1 qt/4hr. "
      "AD 80-04-03 R2 cam/lifter check — increased wear documented.",
      hobbs=1905.0, next_due_date="1994-11-08", ad_reference="80-04-03 R2",
      labor_hours=10.0, signoff_type="inspection_approval"),

    R("1994-11-05", "AIRCRAFT", "annual",
      "Annual inspection. Engine at limit — major overhaul contracted with AZ Aviation "
      "Overhaul for April 1995. Compressions 64/80, 66/80, 62/80, 64/80. "
      "AD 80-04-03 R2 complied. All systems serviceable pending overhaul.",
      hobbs=2005.0, next_due_date="1995-11-05", ad_reference="80-04-03 R2",
      labor_hours=10.0, signoff_type="inspection_approval"),

    # ── 1995 — First Major Overhaul ───────────────────────────────────────────
    R("1995-04-15", "ENGINE-1", "major_overhaul",
      "MAJOR OVERHAUL #1 COMPLETE — AZ Aviation Overhaul. Engine overhauled to new limits "
      "per Lycoming Overhaul Manual. Engine had approximately 2092hr since new. New factory "
      "cylinders (4), all 8 O-320-H2AD barrel lifters replaced with latest approved design, "
      "camshaft replaced, crankshaft Magnafluxed and reground per AD 80-04-03 R2, new main "
      "bearings, new rod bearings, new rings, carburetor overhauled, both magnetos overhauled, "
      "starter overhauled, alternator bench tested. Engine SMOH reset to 0. Prop overhauled "
      "concurrently. Post-overhaul compressions 78/80 all cylinders. Ground run 2 hours.",
      hobbs=2100.0, mechanic=_MECHS["chen"], inspector=_MECHS["chen"],
      ad_reference="80-04-03 R2", sb_reference="480F",
      parts_replaced="4 factory-new cylinders, 8 O-320-H2AD barrel lifters, camshaft, "
                     "crankshaft regrind, main & rod bearings, rings, carb OH, magneto OH (both), "
                     "starter OH, prop OH",
      labor_hours=65.0, signoff_type="return_to_service"),

    R("1995-04-20", "PROP-1", "major_overhaul",
      "McCauley 1C235/DTM7557 propeller overhauled concurrent with engine major overhaul. "
      "Blades inspected and balanced, hub inspected and found serviceable, bushings replaced, "
      "new spinner. Return to service.",
      hobbs=2100.0, mechanic=_MECHS["chen"],
      parts_replaced="Prop hub bushings, spinner", labor_hours=8.0,
      signoff_type="return_to_service"),

    R("1995-11-10", "AIRCRAFT", "annual",
      "First annual post-major-overhaul #1. Engine SMOH 185hr. Compressions 78/80 all "
      "cylinders — excellent. AD 80-04-03 R2 complied at overhaul, recurring due at 2200hr "
      "TT (100hr from now). Clean annual.",
      hobbs=2185.0, next_due_date="1996-11-10", ad_reference="80-04-03 R2",
      next_due_hobbs="2285", labor_hours=8.0, signoff_type="inspection_approval"),

    # ── 1996–2008: Post-OH #1 flying ─────────────────────────────────────────
    R("1996-11-08", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 270hr. Compressions 76/80, 78/80, 76/80, 76/80. AD 80-04-03 R2 "
      "cam/lifter inspection — all lifters within limits. Clean annual.",
      hobbs=2270.0, next_due_date="1997-11-08", ad_reference="80-04-03 R2",
      labor_hours=8.0, signoff_type="inspection_approval"),

    R("1997-11-10", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 355hr. AD 90-06-03 R1 exhaust muffler inspection — minor surface "
      "rust on heat exchanger baffles, cleaned, no cracks. Serviceable. AD 80-04-03 R2 "
      "cam/lifter — within limits.",
      hobbs=2355.0, next_due_date="1998-11-10",
      ad_reference="80-04-03 R2; 90-06-03 R1",
      labor_hours=10.0, signoff_type="inspection_approval"),

    R("1998-11-12", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 435hr. Transponder and encoder checked per 14 CFR 91.413 — "
      "passed. Pitot-static check per 14 CFR 91.411 — passed. AD 80-04-03 R2 cam/lifter "
      "inspection — normal wear.",
      hobbs=2435.0, next_due_date="1999-11-12", ad_reference="80-04-03 R2",
      labor_hours=12.0, signoff_type="inspection_approval"),

    R("1999-11-09", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 510hr. Cam/lifter AD 80-04-03 R2 recurring check — no abnormal "
      "wear. Compressions 74/80, 76/80, 74/80, 76/80. New vacuum pump installed preventively "
      "at 510hr SMOH (prior pump at 510hr).",
      hobbs=2510.0, next_due_date="2000-11-09", ad_reference="80-04-03 R2",
      parts_replaced="Vacuum pump (Champion CA50-1512-50)", labor_hours=10.0,
      signoff_type="inspection_approval"),

    R("2000-11-07", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 585hr. Clean annual. All systems serviceable. ELT battery "
      "replaced per 14 CFR 91.207. AD 80-04-03 R2 complied.",
      hobbs=2585.0, next_due_date="2001-11-07", ad_reference="80-04-03 R2",
      parts_replaced="ELT battery", labor_hours=10.0, signoff_type="inspection_approval"),

    R("2001-09-15", "AIRFRAME-1", "ad_compliance",
      "AD 2001-23-03 initial compliance — Cessna 172N forward door post wiring inspection "
      "for chafing or arcing. Left forward door post area inspected. No chafing found. "
      "Wiring repositioned and secured with new cushion clamps as precautionary measure.",
      hobbs=2635.0, ad_reference="2001-23-03",
      labor_hours=2.0, signoff_type="conformity_statement"),

    R("2001-11-05", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 655hr. Major midpoint check. Compressions 74/80, 76/80, "
      "72/80, 74/80. Magneto internal inspection and overhaul at 1000hr SMOH — performed "
      "early per owner request. Carburetor overhauled. AD 2001-23-03 reviewed.",
      hobbs=2655.0, next_due_date="2002-11-05",
      ad_reference="80-04-03 R2; 2001-23-03",
      parts_replaced="Magneto overhaul kits (2), carburetor overhaul kit",
      labor_hours=14.0, signoff_type="inspection_approval"),

    R("2002-11-10", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 725hr. AD 80-04-03 R2 cam/lifter — wear within limits. "
      "AD 90-06-03 R1 exhaust — no cracks, heat exchanger serviceable. Clean annual.",
      hobbs=2725.0, next_due_date="2003-11-10",
      ad_reference="80-04-03 R2; 90-06-03 R1",
      labor_hours=10.0, signoff_type="inspection_approval"),

    # ── 2003 Exhaust squawk ───────────────────────────────────────────────────
    R("2003-04-10", "ENGINE-1-EXHAUST", "squawk",
      "Cracked exhaust riser at #2 cylinder discovered during AD 90-06-03 R1 "
      "inspection. Internal crack visible — CO contamination risk. GROUNDING SQUAWK.",
      hobbs=2763.0, squawk_id="SQ-2003-EXHAUST",
      severity="grounding", status="resolved",
      signoff_type="return_to_service"),

    R("2003-04-15", "ENGINE-1-EXHAUST", "repair",
      "SQUAWK RESOLVED (SQ-2003-EXHAUST): Exhaust riser #2 cylinder replaced with new "
      "Cessna 172N exhaust riser. Full exhaust system pressure tested — no additional "
      "leaks. Return to service per AD 90-06-03 R1 compliance.",
      hobbs=2763.5, resolved_by="SQ-2003-EXHAUST",
      ad_reference="90-06-03 R1",
      parts_replaced="Exhaust riser #2 cylinder (Cessna P/N 0550207-5)",
      labor_hours=4.0),

    R("2003-11-08", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 795hr. AD 80-04-03 R2 cam/lifter — wear within limits. "
      "Exhaust system fully reinspected post-repair per AD 90-06-03 R1 — serviceable. "
      "Transponder re-certified per 14 CFR 91.413.",
      hobbs=2795.0, next_due_date="2004-11-08",
      ad_reference="80-04-03 R2; 90-06-03 R1",
      labor_hours=12.0, signoff_type="inspection_approval"),

    R("2004-11-10", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 865hr. AD 80-04-03 R2 recurring check — within limits. "
      "Battery replaced (4 years old). Pitot-static check per 14 CFR 91.411 — passed.",
      hobbs=2865.0, next_due_date="2005-11-10", ad_reference="80-04-03 R2",
      parts_replaced="Battery (Concorde RG-24-15)",
      labor_hours=10.0, signoff_type="inspection_approval"),

    R("2005-11-09", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 930hr. Compressions: 70/80, 72/80, 70/80, 70/80 — "
      "declining. Oil consumption 1 qt/8hr. Begin planning second major overhaul. "
      "AD 80-04-03 R2 cam/lifter — wear accelerating.",
      hobbs=2930.0, next_due_date="2006-11-09", ad_reference="80-04-03 R2",
      mechanic=_MECHS["wheeler"], inspector=_MECHS["wheeler"],
      labor_hours=11.0, signoff_type="inspection_approval"),

    R("2006-11-07", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 1005hr. Owner evaluating O-320-D2J conversion to address "
      "H2AD lifter issues long-term. Decided to overhaul with current H2AD parts. "
      "Overhaul planned for 2009. AD 80-04-03 R2 cam/lifter documented.",
      hobbs=2995.0, next_due_date="2007-11-07", ad_reference="80-04-03 R2",
      mechanic=_MECHS["wheeler"], inspector=_MECHS["wheeler"],
      labor_hours=11.0, signoff_type="inspection_approval"),

    R("2007-11-05", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 1080hr. AD 80-04-03 R2 cam/lifter inspection — increased "
      "wear on lifters #3 and #6, still within Lycoming limits. Overhaul firm for 2009.",
      hobbs=3060.0, next_due_date="2008-11-05", ad_reference="80-04-03 R2",
      mechanic=_MECHS["wheeler"], inspector=_MECHS["wheeler"],
      labor_hours=11.0, signoff_type="inspection_approval"),

    R("2008-11-03", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 1165hr. Compressions 64/80, 66/80, 62/80, 64/80. "
      "Oil consumption 1 qt/5hr. Overhaul contracted with AZ Aviation Overhaul "
      "for May 2009.",
      hobbs=3165.0, next_due_date="2009-11-03", ad_reference="80-04-03 R2",
      mechanic=_MECHS["wheeler"], inspector=_MECHS["wheeler"],
      labor_hours=11.0, signoff_type="inspection_approval"),

    # ── 2009 — Second Major Overhaul ─────────────────────────────────────────
    R("2009-05-20", "ENGINE-1", "major_overhaul",
      "MAJOR OVERHAUL #2 COMPLETE — AZ Aviation Overhaul. Engine overhauled to new limits. "
      "Engine had approximately 1265hr SMOH since OH #1 (TT 3350hr). New factory cylinders "
      "(4), all 8 O-320-H2AD barrel lifters replaced with latest Lycoming-approved design "
      "(revised geometry), camshaft replaced, crankshaft Magnafluxed — found serviceable "
      "(no regrind required), new main and rod bearings, new rings. All accessories "
      "overhauled. AD 80-04-03 R2 fully complied. SB 480F oil service requirements "
      "reviewed and documented. Engine SMOH reset to 0. Post-overhaul compressions: "
      "78/80 all cylinders. 2-hour ground run complete.",
      hobbs=3350.0, mechanic=_MECHS["chen"], inspector=_MECHS["chen"],
      ad_reference="80-04-03 R2", sb_reference="480F",
      parts_replaced="4 factory-new cylinders, 8 O-320-H2AD barrel lifters, camshaft, "
                     "new main and rod bearings, rings, carb OH, magneto OH (both), "
                     "starter OH, alternator bench tested and certified",
      labor_hours=65.0, signoff_type="return_to_service"),

    R("2009-06-01", "PROP-1", "major_overhaul",
      "McCauley 1C235/DTM7557 propeller overhauled concurrent with engine major overhaul. "
      "Blades inspected, balanced, no damage. Hub inspected — serviceable. Spinner replaced. "
      "Return to service.",
      hobbs=3350.0, mechanic=_MECHS["chen"],
      parts_replaced="New spinner, hub bushings", labor_hours=6.0,
      signoff_type="return_to_service"),

    # ── Post-overhaul #2 oil changes (every ~50hr) ────────────────────────────
    R("2009-11-15", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr post-overhaul oil change. Hobbs 3400. Aeroshell 15W-50. Filter cut — "
      "very fine metallic fines (normal break-in). No chunks. Good break-in progress.",
      hobbs=3400.0, next_due_hobbs="3450", next_due_date="2010-04-01",
      sb_reference="480F", labor_hours=0.8),

    R("2010-06-15", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 3450. Aeroshell 15W-50. Filter cut — no abnormal metal. "
      "Break-in complete.",
      hobbs=3450.0, next_due_hobbs="3500", sb_reference="480F", labor_hours=0.8),

    R("2010-12-10", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 3500. Aeroshell 15W-50. Filter cut — no metal.",
      hobbs=3500.0, next_due_hobbs="3550", sb_reference="480F", labor_hours=0.8),

    R("2011-06-20", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 3550. Aeroshell 15W-50. Filter cut — no metal.",
      hobbs=3550.0, next_due_hobbs="3600", sb_reference="480F", labor_hours=0.8),

    R("2011-12-15", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 3600. Aeroshell 15W-50. Filter cut — no abnormal metal.",
      hobbs=3600.0, next_due_hobbs="3650", sb_reference="480F", labor_hours=0.8),

    R("2012-07-10", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 3650. Aeroshell 15W-50. Filter cut — clean.",
      hobbs=3650.0, next_due_hobbs="3700", sb_reference="480F", labor_hours=0.8),

    R("2013-01-20", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 3700. Aeroshell 15W-50. Filter cut — no metal.",
      hobbs=3700.0, next_due_hobbs="3750", sb_reference="480F", labor_hours=0.8),

    R("2013-08-15", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 3750. Aeroshell 15W-50. Filter cut — no metal. "
      "Oil analysis sent to Blackstone Labs — all parameters normal (iron 9 ppm).",
      hobbs=3750.0, next_due_hobbs="3800", sb_reference="480F", labor_hours=0.8),

    R("2014-03-10", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 3800. Aeroshell 15W-50. Filter cut — no metal.",
      hobbs=3800.0, next_due_hobbs="3850", sb_reference="480F", labor_hours=0.8),

    R("2014-10-25", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 3850. Aeroshell 15W-50. Filter cut — no metal.",
      hobbs=3850.0, next_due_hobbs="3900", sb_reference="480F", labor_hours=0.8),

    R("2015-06-05", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 3900. Aeroshell 15W-50. Filter cut — no metal.",
      hobbs=3900.0, next_due_hobbs="3950", sb_reference="480F",
      mechanic=_MECHS["torres"], labor_hours=0.8),

    R("2015-12-18", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 3950. Aeroshell 15W-50. Filter cut — no metal.",
      hobbs=3950.0, next_due_hobbs="4000", sb_reference="480F",
      mechanic=_MECHS["torres"], labor_hours=0.8),

    R("2016-08-08", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 4000. Aeroshell 15W-50. Filter cut — no abnormal metal. "
      "Oil analysis (Blackstone Labs): iron 12 ppm (baseline 10) — within normal range.",
      hobbs=4000.0, next_due_hobbs="4050", sb_reference="480F",
      mechanic=_MECHS["torres"], labor_hours=0.8),

    R("2017-02-22", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 4050. Aeroshell 15W-50. Filter cut — no metal.",
      hobbs=4050.0, next_due_hobbs="4100", sb_reference="480F",
      mechanic=_MECHS["torres"], labor_hours=0.8),

    R("2017-10-05", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 4100. Aeroshell 15W-50. Filter cut — no metal.",
      hobbs=4100.0, next_due_hobbs="4150", sb_reference="480F",
      mechanic=_MECHS["torres"], labor_hours=0.8),

    R("2018-04-28", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 4150. Aeroshell 15W-50. Filter cut — no metal.",
      hobbs=4150.0, next_due_hobbs="4200", sb_reference="480F",
      mechanic=_MECHS["torres"], labor_hours=0.8),

    R("2018-11-12", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 4200. Aeroshell 15W-50. Filter cut — no abnormal metal.",
      hobbs=4200.0, next_due_hobbs="4250", sb_reference="480F",
      mechanic=_MECHS["torres"], labor_hours=0.8),

    R("2019-06-03", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 4250. Aeroshell 15W-50. Filter cut — no metal.",
      hobbs=4250.0, next_due_hobbs="4300", sb_reference="480F",
      mechanic=_MECHS["torres"], labor_hours=0.8),

    R("2019-12-18", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 4300. Aeroshell 15W-50. Filter cut — no metal. "
      "Oil analysis (Blackstone): iron 13 ppm — normal, cam/lifter pattern consistent.",
      hobbs=4300.0, next_due_hobbs="4350", sb_reference="480F",
      mechanic=_MECHS["torres"], labor_hours=0.8),

    R("2020-07-15", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 4350. Aeroshell 15W-50. Filter cut — no metal. "
      "(Delayed slightly due to COVID — 4 months, within 4-month calendar limit.)",
      hobbs=4350.0, next_due_hobbs="4400", sb_reference="480F",
      mechanic=_MECHS["torres"], labor_hours=0.8),

    R("2021-02-08", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 4400. Aeroshell 15W-50. Filter cut — no metal.",
      hobbs=4400.0, next_due_hobbs="4450", sb_reference="480F",
      mechanic=_MECHS["torres"], labor_hours=0.8),

    R("2021-09-14", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 4450. Aeroshell 15W-50. Filter cut — no metal.",
      hobbs=4450.0, next_due_hobbs="4500", sb_reference="480F",
      mechanic=_MECHS["torres"], labor_hours=0.8),

    R("2022-04-20", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 4500. Aeroshell 15W-50. Filter cut — no metal.",
      hobbs=4500.0, next_due_hobbs="4550", sb_reference="480F",
      mechanic=_MECHS["torres"], labor_hours=0.8),

    R("2022-11-08", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 4550. Aeroshell 15W-50. Filter cut — no metal.",
      hobbs=4550.0, next_due_hobbs="4600", sb_reference="480F",
      mechanic=_MECHS["torres"], labor_hours=0.8),

    R("2023-06-05", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 4600. Aeroshell 15W-50. Filter cut — no metal.",
      hobbs=4600.0, next_due_hobbs="4650", sb_reference="480F",
      mechanic=_MECHS["torres"], labor_hours=0.8),

    # Blackstone elevated iron — important story beat
    R("2024-01-10", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 4650. Aeroshell 15W-50. Filter cut — no metal. "
      "Oil analysis sent to Blackstone Labs. Results received: iron slightly elevated "
      "(22 ppm vs 15 ppm baseline). Lycoming advises monitoring cam/lifter condition "
      "per AD 80-04-03 R2 — consistent with known H2AD wear pattern. Will inspect "
      "at next annual.",
      hobbs=4650.0, next_due_hobbs="4700", sb_reference="480F",
      ad_reference="80-04-03 R2",
      mechanic=_MECHS["torres"], labor_hours=0.8),

    # ── Post-2009 annual inspections ──────────────────────────────────────────
    R("2009-11-10", "AIRCRAFT", "annual",
      "Annual post-second-major-overhaul. Engine SMOH 100hr. Compressions 78/80 all "
      "cylinders. AD 80-04-03 R2 complied at overhaul — recurring due at 3450hr TT. "
      "All systems serviceable.",
      hobbs=3450.0, next_due_date="2010-11-10", ad_reference="80-04-03 R2",
      mechanic=_MECHS["wheeler"], inspector=_MECHS["wheeler"],
      labor_hours=8.0, signoff_type="inspection_approval"),

    R("2010-11-08", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 205hr. AD 80-04-03 R2 cam/lifter recurring check — all "
      "lifters within limits, camshaft in excellent condition. Compressions 76/80, "
      "78/80, 76/80, 78/80.",
      hobbs=3555.0, next_due_date="2011-11-08", ad_reference="80-04-03 R2",
      mechanic=_MECHS["wheeler"], inspector=_MECHS["wheeler"],
      labor_hours=10.0, signoff_type="inspection_approval"),

    R("2011-06-15", "AIRFRAME-1-SEATS-BELTS", "ad_compliance",
      "AD 2011-10-09 initial compliance — Cessna seat track and lock mechanism "
      "inspection. Both front seat tracks inspected for proper engagement of locking "
      "pins. Lock mechanisms cleaned and lubricated. Both seats engage correctly. "
      "No discrepancies found.",
      hobbs=3596.0, ad_reference="2011-10-09",
      mechanic=_MECHS["wheeler"], labor_hours=2.0, signoff_type="conformity_statement"),

    R("2011-11-07", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 290hr. AD 2011-10-09 seat track compliance reviewed and "
      "documented. AD 80-04-03 R2 cam/lifter — no abnormal wear. Clean annual.",
      hobbs=3640.0, next_due_date="2012-11-07",
      ad_reference="80-04-03 R2; 2011-10-09",
      mechanic=_MECHS["wheeler"], inspector=_MECHS["wheeler"],
      labor_hours=10.0, signoff_type="inspection_approval"),

    R("2012-11-05", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 375hr. AD 80-04-03 R2 cam/lifter recurring — within limits. "
      "AD 90-06-03 R1 exhaust — no cracks. AD 2011-10-09 seat track — complied. "
      "Transponder re-certified per 14 CFR 91.413.",
      hobbs=3725.0, next_due_date="2013-11-05",
      ad_reference="80-04-03 R2; 2011-10-09",
      mechanic=_MECHS["wheeler"], inspector=_MECHS["wheeler"],
      labor_hours=12.0, signoff_type="inspection_approval"),

    R("2013-11-03", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 460hr. AD 80-04-03 R2 recurring — all within limits. "
      "Pitot-static check per 14 CFR 91.411 — passed. Battery load tested — serviceable.",
      hobbs=3810.0, next_due_date="2014-11-03",
      ad_reference="80-04-03 R2; 2011-10-09",
      mechanic=_MECHS["wheeler"], inspector=_MECHS["wheeler"],
      labor_hours=10.0, signoff_type="inspection_approval"),

    R("2014-11-01", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 545hr. Vacuum pump replaced preventively at 545hr SMOH "
      "(prior pump original post-OH). AD 80-04-03 R2 cam/lifter — within limits. "
      "AD 2011-10-09 seat track complied.",
      hobbs=3895.0, next_due_date="2015-11-01",
      ad_reference="80-04-03 R2; 2011-10-09",
      parts_replaced="Vacuum pump (Champion CA50-1512-50)",
      mechanic=_MECHS["wheeler"], inspector=_MECHS["wheeler"],
      labor_hours=10.0, signoff_type="inspection_approval"),

    R("2015-03-15", "ENGINE-1-MAGS", "overhaul",
      "1000hr SMOH magneto overhaul. Both Slick 4370 magnetos removed and sent to "
      "authorized overhaul facility. New points, condensers, caps, rotors. Timing set "
      "to 25° BTC on reinstall. Run-up normal — both magnetos within mag drop limits.",
      hobbs=3920.0, next_due_hobbs="4420",
      parts_replaced="Slick 4370 magneto overhaul kits (2)",
      mechanic=_MECHS["torres"], labor_hours=4.0),

    R("2015-11-02", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 625hr. AD 80-04-03 R2 cam/lifter recurring — all within "
      "limits. Transponder re-certified per 14 CFR 91.413. ELT battery replaced per "
      "14 CFR 91.207. AD 2001-23-03 door post wiring — no chafing.",
      hobbs=3975.0, next_due_date="2016-11-02",
      ad_reference="80-04-03 R2; 2011-10-09; 2001-23-03",
      parts_replaced="ELT battery",
      mechanic=_MECHS["torres"], inspector=_MECHS["torres"],
      labor_hours=12.0, signoff_type="inspection_approval"),

    R("2016-05-20", "AVIONICS-1", "squawk",
      "Compass deviation exceeding limits — showing up to 15° error on some headings. "
      "Deviation card invalid. Non-grounding (VFR OK with updated card). Deferred for "
      "compass swing.",
      hobbs=4002.0, squawk_id="SQ-2016-COMPASS",
      severity="non-grounding", status="resolved"),

    R("2016-05-25", "AVIONICS-1", "repair",
      "SQUAWK RESOLVED (SQ-2016-COMPASS): Compass swung with certified compass rose. "
      "Deviation reduced to 2° maximum all headings. New deviation card created and "
      "installed on instrument panel. Serviceable.",
      hobbs=4003.0, resolved_by="SQ-2016-COMPASS",
      parts_replaced="Compass deviation card", labor_hours=1.5),

    R("2016-11-01", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 705hr. AD 80-04-03 R2 complied. Clean annual. New battery "
      "installed (prior battery 4 years old). AD 2011-10-09 seat track complied.",
      hobbs=4055.0, next_due_date="2017-11-01",
      ad_reference="80-04-03 R2; 2011-10-09",
      parts_replaced="Battery (Concorde RG-24-15)",
      mechanic=_MECHS["torres"], inspector=_MECHS["torres"],
      labor_hours=10.0, signoff_type="inspection_approval"),

    R("2017-11-05", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 790hr. Cam/lifter AD 80-04-03 R2 recurring. Compressions: "
      "74/80, 76/80, 74/80, 76/80. ELT battery replaced. Exhaust muffler AD 90-06-03 "
      "R1 — no cracks.",
      hobbs=4140.0, next_due_date="2018-11-05",
      ad_reference="80-04-03 R2; 90-06-03 R1",
      parts_replaced="ELT battery",
      mechanic=_MECHS["torres"], inspector=_MECHS["torres"],
      labor_hours=11.0, signoff_type="inspection_approval"),

    R("2018-11-03", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 875hr. AD 80-04-03 R2 cam/lifter check — slight wear increase "
      "noted on lifters #2 and #7 (barrel-type units), within Lycoming limits, documented. "
      "Recommend enhanced oil monitoring at each change.",
      hobbs=4225.0, next_due_date="2019-11-03",
      ad_reference="80-04-03 R2",
      mechanic=_MECHS["torres"], inspector=_MECHS["torres"],
      labor_hours=11.0, signoff_type="inspection_approval"),

    R("2019-11-01", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 955hr. AD 80-04-03 R2 cam/lifter — wear documented but within "
      "limits. Next overhaul at 2000hr SMOH. Compressions: 72/80, 74/80, 72/80, 72/80. "
      "Transponder re-certified per 14 CFR 91.413.",
      hobbs=4305.0, next_due_date="2020-11-01",
      ad_reference="80-04-03 R2",
      mechanic=_MECHS["torres"], inspector=_MECHS["torres"],
      labor_hours=11.0, signoff_type="inspection_approval"),

    R("2020-11-05", "AIRCRAFT", "annual",
      "Annual (COVID year — limited flying). Engine SMOH 1020hr. AD 80-04-03 R2 cam/lifter "
      "recurring check — within limits. Carburetor cleaned and adjusted idle mixture. "
      "AD 2011-10-09 seat track complied.",
      hobbs=4370.0, next_due_date="2021-11-05",
      ad_reference="80-04-03 R2; 2011-10-09",
      mechanic=_MECHS["torres"], inspector=_MECHS["torres"],
      labor_hours=10.0, signoff_type="inspection_approval"),

    R("2021-11-03", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 1110hr. AD 80-04-03 R2 cam/lifter — wear within limits, all "
      "lifters serviceable. Compressions 70/80, 72/80, 70/80, 70/80. Vacuum pump replaced "
      "at 1110hr SMOH (third unit, life expired). AD 2011-10-09 seat track complied. "
      "Pitot-static check per 14 CFR 91.411 — passed. ELT battery replaced.",
      hobbs=4460.0, next_due_date="2022-11-03",
      ad_reference="80-04-03 R2; 2011-10-09",
      parts_replaced="Vacuum pump (Champion CA50-1512-50), ELT battery",
      mechanic=_MECHS["torres"], inspector=_MECHS["torres"],
      labor_hours=12.0, signoff_type="inspection_approval"),

    R("2022-11-01", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 1200hr. Midpoint check. AD 80-04-03 R2 cam/lifter — within "
      "limits but wear trend noted. Next overhaul planning at 2000hr SMOH (~2029). "
      "Battery replaced (4 years). AD 2001-23-03 wiring — no issues.",
      hobbs=4550.0, next_due_date="2023-11-01",
      ad_reference="80-04-03 R2; 2001-23-03",
      parts_replaced="Battery (Concorde RG-24-15)",
      mechanic=_MECHS["torres"], inspector=_MECHS["torres"],
      labor_hours=11.0, signoff_type="inspection_approval"),

    # ── 2023 squawks ─────────────────────────────────────────────────────────
    R("2023-06-20", "AIRFRAME-1-NOSE-STRUT", "squawk",
      "Nose strut not holding pressure — drops to flat within 3 days of servicing. "
      "Taxi handling affected on rollout. Non-grounding. Deferred for seal replacement.",
      hobbs=4605.0, squawk_id="SQ-2023-STRUT",
      severity="non-grounding", status="resolved",
      signoff_type="return_to_service"),

    R("2023-06-25", "AIRFRAME-1-NOSE-STRUT", "repair",
      "SQUAWK RESOLVED (SQ-2023-STRUT): Nose gear oleo strut resealed. New O-ring and "
      "wiper seal kit installed. Serviced with MIL-H-5606 hydraulic fluid and nitrogen. "
      "Extension set per Cessna maintenance manual — 2.5 inches. Ground roll confirmed "
      "normal.",
      hobbs=4605.5, resolved_by="SQ-2023-STRUT",
      parts_replaced="Nose strut seal kit, MIL-H-5606 fluid, nitrogen charge",
      labor_hours=2.5),

    R("2023-09-12", "AVIONICS-1-COMM", "squawk",
      "Comm radio intermittent static on transmit — ATC reports broken up transmissions "
      "on multiple occasions. Antenna connection suspected.",
      hobbs=4618.0, squawk_id="SQ-2023-COMM",
      severity="non-grounding", status="resolved",
      signoff_type="return_to_service"),

    R("2023-09-16", "AVIONICS-1-COMM", "repair",
      "SQUAWK RESOLVED (SQ-2023-COMM): Comm antenna connection found loose at airframe "
      "connection point below instrument panel. Connector cleaned, re-torqued, "
      "Kopr-Shield anti-corrosion compound applied. Transmit tested on all comm "
      "channels — clear.",
      hobbs=4619.0, resolved_by="SQ-2023-COMM",
      parts_replaced="None (loose connection reseated)",
      labor_hours=0.8),

    R("2023-11-01", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 1290hr. AD 80-04-03 R2 cam/lifter — wear within limits, "
      "iron tracking consistent with Blackstone analysis. AD 90-06-03 R1 exhaust — "
      "no cracks. Transponder re-certified per 14 CFR 91.413. AD 2011-10-09 seat track "
      "complied. ELT battery replaced. All squawks resolved.",
      hobbs=4640.0, next_due_date="2024-11-01",
      ad_reference="80-04-03 R2; 90-06-03 R1; 2011-10-09",
      parts_replaced="ELT battery",
      mechanic=_MECHS["torres"], inspector=_MECHS["torres"],
      labor_hours=13.0, signoff_type="inspection_approval"),

    # ── 2024 squawks ─────────────────────────────────────────────────────────
    R("2024-02-08", "ENGINE-1-SPARK-PLUGS", "squawk",
      "#3 cylinder CHT running consistently ~30°F hotter than other cylinders in cruise "
      "(395°F vs 360°F others at 8500ft, 75% power). Noticed during routine cross-country. "
      "Non-grounding but abnormal. Deferred for inspection.",
      hobbs=4657.9, squawk_id="SQ-2024-CHT3",
      severity="non-grounding", status="resolved",
      signoff_type="return_to_service"),

    R("2024-02-12", "ENGINE-1-SPARK-PLUGS", "repair",
      "SQUAWK RESOLVED (SQ-2024-CHT3): #3 cylinder spark plugs inspected — bottom plug "
      "found partially fouled with lead deposits (bridged gap). All 8 Champion REM40E "
      "plugs cleaned, re-gapped at 0.016\", lead deposits removed with chemical cleaner. "
      "Rotated top-to-bottom per Lycoming recommendation. Ground run and test flight — "
      "CHT now equal (±5°F) across all cylinders.",
      hobbs=4658.5, resolved_by="SQ-2024-CHT3",
      parts_replaced="None (cleaned and rotated)",
      labor_hours=1.5),

    # Oil change at 4700 with trace filter sparkle
    R("2024-09-28", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 4700. Aeroshell 15W-50. Filter cut — trace amounts of very "
      "fine ferrous material (metallic sparkle in oil, no chunks or particles). Consistent "
      "with known H2AD cam/lifter wear pattern per AD 80-04-03 R2. Will notify owner and "
      "track at next change. AD inspection at next oil change.",
      hobbs=4700.0, next_due_hobbs="4750", next_due_date="2025-03-01",
      sb_reference="480F", ad_reference="80-04-03 R2",
      mechanic=_MECHS["torres"], labor_hours=0.8),

    R("2024-07-12", "AIRFRAME-1-FUEL-CAPS", "squawk",
      "Right fuel cap not sealing — fuel odor in cockpit on climbout. Cap appeared "
      "tightened but seal likely degraded. Non-grounding (smell, not leak). Deferred "
      "for cap replacement.",
      hobbs=4682.0, squawk_id="SQ-2024-FUELCAP",
      severity="non-grounding", status="resolved",
      signoff_type="return_to_service"),

    R("2024-07-15", "AIRFRAME-1-FUEL-CAPS", "repair",
      "SQUAWK RESOLVED (SQ-2024-FUELCAP): Right fuel cap replaced with new OEM Cessna "
      "cap assembly. Seal gasket on left cap also inspected — serviceable, no replacement "
      "needed. Right cap seating and venting verified. Test flight — no fuel odor. "
      "Serviceable.",
      hobbs=4682.5, resolved_by="SQ-2024-FUELCAP",
      parts_replaced="Right fuel cap assembly (Cessna P/N 0511012-1)",
      labor_hours=0.5),

    R("2024-11-01", "AIRCRAFT", "annual",
      "Annual. Engine SMOH 1400hr. AD 80-04-03 R2 cam/lifter recurring — filter sparkle "
      "noted at Sep oil change, lifters inspected directly — wear within limits, barrels "
      "show polishing consistent with H2AD wear pattern. Oil analysis (Blackstone) iron "
      "22 ppm — consistent with prior. Will continue monitoring. AD 90-06-03 R1 exhaust — "
      "no cracks. AD 2011-10-09 seat track complied. AD 2001-23-03 wiring — no issues. "
      "Compressions: 70/80, 72/80, 70/80, 70/80 — acceptable at 1400hr SMOH.",
      hobbs=4750.0, next_due_date="2025-11-01",
      ad_reference="80-04-03 R2; 90-06-03 R1; 2011-10-09; 2001-23-03",
      mechanic=_MECHS["torres"], inspector=_MECHS["torres"],
      labor_hours=14.0, signoff_type="inspection_approval"),

    R("2025-05-08", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 4758. Aeroshell 15W-50. Filter cut — trace metallic "
      "sparkle (consistent with prior, H2AD cam/lifter pattern). No chunks. "
      "Oil analysis (Blackstone) sent.",
      hobbs=4758.0, next_due_hobbs="4808", next_due_date="2025-09-08",
      sb_reference="480F", ad_reference="80-04-03 R2",
      mechanic=_MECHS["torres"], labor_hours=0.8),

    # ── Oct 8 2025 — Last shared annual ──────────────────────────────────────
    R("2025-10-08", "AIRCRAFT", "annual",
      "Annual inspection. Airframe TT 4801hr. Engine SMOH 1451hr. AD 80-04-03 R2 "
      "cam/lifter recurring inspection — lifter wear within limits, consistent with "
      "Blackstone iron trending. AD 90-06-03 R1 exhaust — no cracks, heat exchanger "
      "serviceable. AD 2011-10-09 seat track — both seats engage properly. AD 2001-23-03 "
      "door post wiring — no chafing, no discrepancies. Compressions: 70/80, 72/80, "
      "70/80, 72/80 — acceptable for current SMOH. Transponder re-certified per 14 CFR "
      "91.413 (Form 337 issued). ELT battery replaced per 14 CFR 91.207. Pitot-static "
      "test per 14 CFR 91.411 — passed. Battery load tested — serviceable. All placards "
      "in place. FINDING: Slight oil seep observed at #3 cylinder rocker cover gasket. "
      "Minor oil residue on lower cowling. Non-grounding per A&P assessment. Deferred to "
      "next annual. Squawk SQ-2026-OILSEEP opened. Return to service.",
      hobbs=4801.0, next_due_date="2026-10-08",
      ad_reference="80-04-03 R2; 90-06-03 R1; 2011-10-09; 2001-23-03",
      parts_replaced="ELT battery",
      mechanic=_MECHS["torres"], inspector=_MECHS["torres"],
      labor_hours=14.0, signoff_type="inspection_approval"),

    # SQ-2026-OILSEEP opened at annual
    R("2025-10-08", "ENGINE-1", "squawk",
      "OPEN: Slight oil seep at #3 cylinder rocker cover gasket. Minor oil residue on "
      "lower cowling — approximately quarter-size stain after flight. Non-grounding per "
      "A&P assessment (Mike Torres). Deferred to next annual inspection (due Oct 8 2026). "
      "Monitor before each flight.",
      hobbs=4801.0, squawk_id="SQ-2026-OILSEEP",
      severity="non-grounding", status="open",
      mechanic=_MECHS["torres"],
      signoff_type="return_to_service"),

    # ── Oct 15 2025 — Last shared oil change ─────────────────────────────────
    R("2025-10-15", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 4808. Aeroshell 15W-50. Filter cut — trace ferrous sparkle "
      "(same pattern as prior two changes, H2AD cam/lifter consistent). No chunks or "
      "significant particles. Informed owner of findings. Next oil change due at 4858.0 "
      "or by Feb 15 2026 (4-month calendar limit), whichever comes first. Will request "
      "AD 80-04-03 R2 cam/lifter direct inspection at next annual.",
      hobbs=4808.0, next_due_hobbs="4858", next_due_date="2026-02-15",
      sb_reference="480F", ad_reference="80-04-03 R2",
      mechanic=_MECHS["torres"], labor_hours=1.0),
]


# ===========================================================================
# Post-divergence maintenance variants
# Divergence point: November 1, 2025 (Hobbs ≈ 4820)
# ===========================================================================

MAINTENANCE_CLEAN_RECENT: list[dict[str, Any]] = [
    # Oil change performed on schedule at Hobbs=4858 (Dec 15, 2025)
    R("2025-12-15", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 4858. Aeroshell 15W-50. Filter cut — trace sparkle "
      "(very fine, same H2AD pattern). No change from prior. Note added to SQ-2026-OILSEEP: "
      "oil seep monitored — appearance unchanged from Oct annual, consistent with deferred "
      "status. Recommend addressing at Oct 2026 annual as planned. Next oil change due "
      "at 4908.0 or by Jun 15 2026.",
      hobbs=4858.0, next_due_hobbs="4908", next_due_date="2026-06-15",
      sb_reference="480F", ad_reference="80-04-03 R2",
      mechanic=_MECHS["torres"], labor_hours=1.0),
]

MAINTENANCE_CAUTION_RECENT: list[dict[str, Any]] = [
    # Oil change performed slightly late at Hobbs=4861 (Dec 20, 2025 — 3hr past due)
    R("2025-12-20", "ENGINE-1-OIL-FILTER", "oil_change",
      "50hr oil change. Hobbs 4861 (3hr past 4858 due — owner caught it quickly). "
      "Aeroshell 15W-50. Filter cut — trace sparkle, consistent with prior. "
      "Note on SQ-2026-OILSEEP: seep slightly increased since Oct annual. "
      "Quarter-size stain now half-dollar size. Still non-grounding. Recommend addressing "
      "at next annual (Oct 2026) or sooner if worsens. Next oil change due at 4911.0 or "
      "by Jun 20 2026.",
      hobbs=4861.0, next_due_hobbs="4911", next_due_date="2026-06-20",
      sb_reference="480F", ad_reference="80-04-03 R2",
      mechanic=_MECHS["torres"], labor_hours=1.0),
]

MAINTENANCE_GROUNDED_RECENT: list[dict[str, Any]] = [
    # No oil change performed Nov-Jan (owner traveling)
    # Squawk upgraded to grounding Feb 28 2026
    R("2026-02-28", "ENGINE-1", "squawk",
      "SQ-2026-OILSEEP STATUS UPGRADED TO GROUNDING. A&P Mike Torres (Torres Aviation) "
      "visited for unrelated logbook review. Inspected oil seep from Oct 2025 annual — "
      "significantly worsened. Heavy oil residue on lower cowling and fuselage belly aft "
      "of firewall. Oil seep now a continuous drip after engine shutdown. "
      "ASSESSMENT: Rocker cover gasket failure in progress. Risk of oil contact with "
      "exhaust components — potential engine compartment fire hazard. "
      "AIRCRAFT GROUNDED — do not fly pending immediate inspection and rocker cover "
      "gasket replacement on #3 cylinder. Oil change also overdue (last at 4808, "
      "current 4897, due was 4858 — 39 hours overdue). Aircraft must be serviced before "
      "return to flight.",
      hobbs=4897.0, squawk_id="SQ-2026-OILSEEP",
      severity="grounding", status="open",
      mechanic=_MECHS["torres"],
      signoff_type="return_to_service"),
]


# ===========================================================================
# FLIGHTS_SHARED — Jan 2024 through Oct 31 2025
# Hobbs advances from ~4651 to ~4820.
# ~50 flights. FLIGHTS_SHARED is identical across all three demo states.
# ===========================================================================

FLIGHTS_SHARED: list[dict[str, Any]] = [
    # Jan 2024 — first flights after Blackstone oil change at 4650
    F("2024-01-14", "KPHX-KPRC-KPHX", 4651.0, 4654.2,
      oil_temp_max=188, cht_max=372, egt_max=1318, pilot_notes=""),
    F("2024-01-26", "KPHX local", 4654.2, 4655.7,
      oil_temp_max=182, cht_max=355, egt_max=1295, pilot_notes=""),

    # Feb 2024 — CHT spike squawk (SQ-2024-CHT3)
    F("2024-02-08", "KPHX-KCHD-KPHX", 4655.7, 4657.9,
      oil_temp_max=186, cht_max=396,  # elevated CHT #3
      egt_max=1328,
      pilot_notes="CHT #3 running ~30°F above other cylinders in cruise — 395°F vs 365°F "
                  "others at 8500ft. Filed squawk SQ-2024-CHT3."),
    F("2024-02-13", "KPHX local", 4658.5, 4659.8,
      oil_temp_max=183, cht_max=358, egt_max=1302,
      pilot_notes="Spark plugs cleaned after squawk — CHT equal all cylinders. "
                  "SQ-2024-CHT3 resolved."),

    # Mar 2024
    F("2024-03-10", "KPHX-KPRC-KPHX", 4659.8, 4663.0,
      oil_temp_max=190, cht_max=378, egt_max=1322, pilot_notes=""),
    F("2024-03-22", "KPHX-KTUS-KPHX", 4663.0, 4665.5,
      oil_temp_max=192, cht_max=382, egt_max=1330, pilot_notes=""),

    # Apr 2024 — Flagstaff
    F("2024-04-06", "KPHX-KFLG-KPHX", 4665.5, 4669.8,
      oil_temp_max=208, cht_max=415, egt_max=1368,
      oil_pressure_min=66, oil_pressure_max=82,
      pilot_notes="DA ~6500ft at KFLG. Long ground roll on 21. CHT peaked 415°F on climb, "
                  "normalized to 385°F at cruise altitude (9500ft). Density altitude "
                  "effects notable — performance reduced as expected."),
    F("2024-04-20", "KPHX local", 4669.8, 4671.2,
      oil_temp_max=185, cht_max=361, egt_max=1298, pilot_notes=""),

    # May 2024
    F("2024-05-05", "KPHX-KPRC-KPHX", 4671.2, 4674.5,
      oil_temp_max=198, cht_max=383, egt_max=1335, pilot_notes=""),
    F("2024-05-19", "KPHX-KSEZ-KPHX", 4674.5, 4678.3,
      oil_temp_max=205, cht_max=391, egt_max=1341, pilot_notes=""),

    # Jun 2024 — Phoenix summer begins
    F("2024-06-04", "KPHX-KPRC", 4678.3, 4679.9,
      oil_temp_max=214, cht_max=388, egt_max=1342,
      pilot_notes="OAT 106°F on ground at KPHX. Oil temp peaked 214°F on initial climb, "
                  "normal at cruise altitude. CHT normal."),
    F("2024-06-20", "KPRC-KPHX", 4679.9, 4681.5,
      oil_temp_max=210, cht_max=384, egt_max=1338, pilot_notes=""),

    # Jul 2024 — Fuel cap squawk (SQ-2024-FUELCAP)
    F("2024-07-04", "KPHX local", 4681.5, 4682.8,
      oil_temp_max=208, cht_max=379, egt_max=1328,
      pilot_notes="July 4 morning flight — OAT 98°F. All normal."),
    F("2024-07-12", "KPHX-KCHD", 4682.8, 4684.0,
      oil_temp_max=211, cht_max=381, egt_max=1330,
      pilot_notes="Fuel odor in cockpit on climbout — right fuel cap seal. Filed "
                  "SQ-2024-FUELCAP."),
    F("2024-07-16", "KCHD-KPHX", 4684.5, 4685.5,
      oil_temp_max=207, cht_max=376, egt_max=1322,
      pilot_notes="New fuel cap installed — no fuel odor. SQ-2024-FUELCAP resolved."),

    # Aug 2024 — Phoenix summer peak
    F("2024-08-08", "KPHX-KPRC-KPHX", 4685.5, 4688.7,
      oil_temp_max=218, cht_max=398,  # elevated due to summer heat
      egt_max=1352,
      pilot_notes="OAT 108°F on ground. Oil temp peaked 218°F on initial climb — within "
                  "limits (245°F redline). Normal at cruise altitude. CHT 398°F on climb."),
    F("2024-08-24", "KPHX local", 4688.7, 4690.2,
      oil_temp_max=213, cht_max=387, egt_max=1338, pilot_notes=""),

    # Sep 2024 — Flagstaff before oil change
    F("2024-09-08", "KPHX-KFLG-KPHX", 4690.2, 4694.5,
      oil_temp_max=205, cht_max=412, egt_max=1360,
      pilot_notes="DA ~6200ft at KFLG. CHT peaked 412°F on climb. Excellent mountain "
                  "visibility — ATIS reported 50sm vis."),
    F("2024-09-22", "KPHX local", 4694.5, 4696.0,
      oil_temp_max=196, cht_max=370, egt_max=1315, pilot_notes=""),

    # Oct 2024 — after 4700 oil change (Sep 28) — Grand Canyon
    F("2024-10-08", "KPHX-KGCN-KPHX", 4700.5, 4706.3,
      oil_temp_max=198, cht_max=394, egt_max=1342,
      pilot_notes="Grand Canyon fall trip. DA ~5800ft at KGCN. Long flight — spectacular "
                  "visibility. CHT normalized at 9500ft cruise."),
    F("2024-10-20", "KPHX local", 4706.3, 4707.8,
      oil_temp_max=188, cht_max=362, egt_max=1305, pilot_notes=""),

    # Nov 2024
    F("2024-11-04", "KPHX-KPRC-KPHX", 4707.8, 4711.0,
      oil_temp_max=183, cht_max=360, egt_max=1298, pilot_notes=""),
    F("2024-11-18", "KPHX-KTUS-KPHX", 4711.0, 4713.5,
      oil_temp_max=180, cht_max=355, egt_max=1292, pilot_notes=""),

    # Nov 2024 annual was at 4750 — aircraft flies after
    # Dec 2024
    F("2024-12-05", "KPHX-KPRC-KPHX", 4750.5, 4753.8,
      oil_temp_max=175, cht_max=348, egt_max=1285, pilot_notes=""),
    F("2024-12-19", "KPHX local", 4753.8, 4755.2,
      oil_temp_max=172, cht_max=345, egt_max=1280, pilot_notes=""),

    # Jan 2025
    F("2025-01-10", "KPHX-KCHD-KPHX", 4755.2, 4757.5,
      oil_temp_max=173, cht_max=350, egt_max=1287, pilot_notes=""),
    F("2025-01-25", "KPHX local", 4757.5, 4758.8,
      oil_temp_max=170, cht_max=342, egt_max=1278, pilot_notes=""),

    # May 2025 oil change at 4758 — flights after
    # Jun 2025 — Flagstaff summer trip
    F("2025-06-08", "KPHX-KFLG-KPHX", 4758.5, 4762.8,
      oil_temp_max=209, cht_max=410, egt_max=1355,
      pilot_notes="DA ~6800ft at KFLG — summer density altitude significant. Long ground "
                  "roll on Rwy 21. CHT peaked 410°F climb, good at cruise."),
    F("2025-06-22", "KPHX-KPRC-KPHX", 4762.8, 4766.1,
      oil_temp_max=212, cht_max=386, egt_max=1338, pilot_notes=""),

    # Jul 2025
    F("2025-07-05", "KPHX local", 4766.1, 4767.3,
      oil_temp_max=215, cht_max=381, egt_max=1330,
      pilot_notes=""),
    F("2025-07-19", "KPHX-KGCN-KPHX", 4767.3, 4773.1,
      oil_temp_max=211, cht_max=396, egt_max=1345,
      pilot_notes="Grand Canyon summer trip. OAT 102°F KPHX departure. Oil temp "
                  "peaked 216°F initial climb — within limits. CHT 396°F climb at KGCN "
                  "altitude. Spectacular monsoon cloud formations around the canyon."),

    # Aug 2025 — Phoenix peak heat
    F("2025-08-02", "KPHX-KSDL-KPHX", 4773.1, 4774.5,
      oil_temp_max=218, cht_max=391, egt_max=1342,
      pilot_notes="OAT 112°F on ground. Oil temp 218°F peak on climb — warm but within "
                  "limits. No anomalies."),
    F("2025-08-17", "KPHX local", 4774.5, 4775.8,
      oil_temp_max=214, cht_max=385, egt_max=1335, pilot_notes=""),

    # Sep 2025
    F("2025-09-06", "KPHX-KTUS-KPHX", 4775.8, 4778.3,
      oil_temp_max=203, cht_max=379, egt_max=1328, pilot_notes=""),
    F("2025-09-20", "KPHX-KSEZ-KPHX", 4778.3, 4782.0,
      oil_temp_max=198, cht_max=375, egt_max=1322, pilot_notes=""),

    # Oct 2025 — annual Oct 8 at 4801
    F("2025-10-02", "KPHX-KPRC-KPHX", 4782.0, 4785.2,
      oil_temp_max=189, cht_max=365, egt_max=1308, pilot_notes=""),
    F("2025-10-19", "KPHX local", 4808.5, 4810.0,
      oil_temp_max=183, cht_max=355, egt_max=1295,
      pilot_notes="First flight after annual and oil change. All systems normal."),
    F("2025-10-26", "KPHX-KPRC-KPHX", 4810.0, 4813.2,
      oil_temp_max=187, cht_max=363, egt_max=1305, pilot_notes=""),

    # Late Oct / Early Nov 2025 — final shared flights
    F("2025-10-31", "KPHX local", 4813.2, 4814.8,
      oil_temp_max=182, cht_max=358, egt_max=1298, pilot_notes=""),
]


# ===========================================================================
# Post-divergence flight variants
# ===========================================================================

FLIGHTS_CLEAN_RECENT: list[dict[str, Any]] = [
    # Nov 2025 — normal flying before holiday slowdown
    F("2025-11-06", "KPHX-KPRC-KPHX", 4814.8, 4818.0,
      oil_temp_max=183, cht_max=360, egt_max=1300, pilot_notes=""),
    F("2025-11-15", "KPHX local", 4818.0, 4819.3,
      oil_temp_max=180, cht_max=352, egt_max=1290, pilot_notes=""),
    F("2025-11-22", "KPHX-KCHD-KPHX", 4819.3, 4821.5,
      oil_temp_max=178, cht_max=349, egt_max=1285, pilot_notes=""),
    # Dec 2025 — oil change at 4858 on Dec 15
    F("2025-12-06", "KPHX-KFLG-KPHX", 4821.5, 4825.8,
      oil_temp_max=175, cht_max=370, egt_max=1298,
      pilot_notes="Flagstaff winter flight — cool and smooth. DA ~5200ft."),
    F("2025-12-13", "KPHX-KPRC-KPHX", 4825.8, 4829.0,
      oil_temp_max=172, cht_max=352, egt_max=1285, pilot_notes=""),
    F("2025-12-20", "KPHX-KSDL-KPHX", 4858.5, 4860.0,
      oil_temp_max=170, cht_max=348, egt_max=1280,
      pilot_notes="First flight after Dec 15 oil change."),
    F("2025-12-28", "KPHX local", 4860.0, 4861.4,
      oil_temp_max=168, cht_max=345, egt_max=1278, pilot_notes=""),
    # Jan 2026 — 2 flights
    F("2026-01-12", "KPHX-KPRC-KPHX", 4861.4, 4864.7,
      oil_temp_max=172, cht_max=355, egt_max=1290, pilot_notes=""),
    F("2026-01-25", "KPHX-KTUS-KPHX", 4864.7, 4867.2,
      oil_temp_max=174, cht_max=359, egt_max=1295, pilot_notes=""),
    # Feb 2026 — 3 flights
    F("2026-02-08", "KPHX-KFLG-KPHX", 4867.2, 4871.5,
      oil_temp_max=179, cht_max=374, egt_max=1308,
      pilot_notes="Nice winter Flagstaff trip. DA ~5000ft. All normal."),
    F("2026-02-18", "KPHX local", 4871.5, 4873.0,
      oil_temp_max=175, cht_max=355, egt_max=1292, pilot_notes=""),
    F("2026-02-27", "KPHX-KPRC-KPHX", 4873.0, 4876.2,
      oil_temp_max=177, cht_max=361, egt_max=1298, pilot_notes=""),
    # Mar 2026 — 2 flights
    F("2026-03-10", "KPHX-KGCN-KPHX", 4876.2, 4882.5,
      oil_temp_max=182, cht_max=378, egt_max=1315,
      pilot_notes="Spring Grand Canyon trip. Perfect VFR day."),
    F("2026-03-22", "KPHX-KSEZ-KPHX", 4882.5, 4889.5,
      oil_temp_max=186, cht_max=381, egt_max=1322, pilot_notes=""),
]

FLIGHTS_CAUTION_RECENT: list[dict[str, Any]] = [
    # Nov 2025 — slightly more active flying
    F("2025-11-05", "KPHX-KPRC-KPHX", 4814.8, 4818.1,
      oil_temp_max=184, cht_max=361, egt_max=1302, pilot_notes=""),
    F("2025-11-14", "KPHX local", 4818.1, 4819.5,
      oil_temp_max=181, cht_max=354, egt_max=1292, pilot_notes=""),
    F("2025-11-21", "KPHX-KCHD-KPHX", 4819.5, 4821.8,
      oil_temp_max=179, cht_max=350, egt_max=1288, pilot_notes=""),
    # Dec 2025 — oil change at 4861 on Dec 20 (3hr late)
    F("2025-12-05", "KPHX-KFLG-KPHX", 4821.8, 4826.2,
      oil_temp_max=176, cht_max=371, egt_max=1300, pilot_notes="Flagstaff winter flight."),
    F("2025-12-12", "KPHX-KPRC-KPHX", 4826.2, 4829.5,
      oil_temp_max=173, cht_max=353, egt_max=1287, pilot_notes=""),
    F("2025-12-27", "KPHX-KGCN-KPHX", 4861.5, 4867.8,
      oil_temp_max=171, cht_max=368, egt_max=1298,
      pilot_notes="Post-oil-change Grand Canyon trip. Great holiday flying."),
    # Jan 2026 — 3 flights
    F("2026-01-08", "KPHX local", 4867.8, 4869.2,
      oil_temp_max=173, cht_max=352, egt_max=1288, pilot_notes=""),
    F("2026-01-16", "KPHX-KPRC-KPHX", 4869.2, 4872.5,
      oil_temp_max=175, cht_max=358, egt_max=1295, pilot_notes=""),
    F("2026-01-28", "KPHX-KTUS-KPHX", 4872.5, 4875.1,
      oil_temp_max=177, cht_max=362, egt_max=1300, pilot_notes=""),
    # Feb 2026 — 4 flights (oil change due at 4911 after this period)
    F("2026-02-05", "KPHX-KFLG-KPHX", 4875.1, 4879.5,
      oil_temp_max=180, cht_max=376, egt_max=1310, pilot_notes=""),
    F("2026-02-14", "KPHX local", 4879.5, 4881.0,
      oil_temp_max=176, cht_max=357, egt_max=1295, pilot_notes=""),
    F("2026-02-22", "KPHX-KSEZ-KPHX", 4881.0, 4885.0,
      oil_temp_max=178, cht_max=365, egt_max=1302, pilot_notes=""),
    F("2026-02-28", "KPHX-KPRC-KPHX", 4885.0, 4888.3,
      oil_temp_max=181, cht_max=369, egt_max=1308, pilot_notes=""),
    # Mar 2026 — 3 flights, passes oil change due at 4911
    F("2026-03-08", "KPHX-KGCN-KPHX", 4888.3, 4894.8,
      oil_temp_max=185, cht_max=380, egt_max=1318, pilot_notes=""),
    F("2026-03-15", "KPHX local", 4894.8, 4896.2,
      oil_temp_max=182, cht_max=360, egt_max=1300, pilot_notes=""),
    F("2026-03-28", "KPHX-KPRC-KPHX", 4916.5, 4919.2,
      oil_temp_max=190, cht_max=374, egt_max=1315,
      pilot_notes="Forgot to check oil change interval before flying — current hobbs "
                  "well past 4911 due point. Will schedule service immediately."),
]

FLIGHTS_GROUNDED_RECENT: list[dict[str, Any]] = [
    # Nov 2025 — owner makes several flights before departing internationally
    F("2025-11-03", "KPHX-KPRC-KPHX", 4814.8, 4818.1,
      oil_temp_max=184, cht_max=360, egt_max=1300, pilot_notes=""),
    F("2025-11-07", "KPHX-KFLG-KPHX", 4818.1, 4822.5,
      oil_temp_max=181, cht_max=375, egt_max=1310,
      pilot_notes="Quick Flagstaff trip before upcoming travel."),
    F("2025-11-12", "KPHX local", 4822.5, 4823.8,
      oil_temp_max=179, cht_max=352, egt_max=1290, pilot_notes=""),
    # Owner departs for international travel Nov 15 — no flying Dec/Jan
    # Feb 2026 — owner returns, resumes flying without checking maintenance status
    F("2026-02-03", "KPHX local", 4823.8, 4825.2,
      oil_temp_max=174, cht_max=351, egt_max=1289,
      pilot_notes="Back from extended travel. First flight in 2.5 months. "
                  "Aircraft felt good."),
    F("2026-02-08", "KPHX-KPRC-KPHX", 4825.2, 4828.4,
      oil_temp_max=176, cht_max=358, egt_max=1296, pilot_notes=""),
    F("2026-02-14", "KPHX-KCHD-KPHX", 4828.4, 4830.5,
      oil_temp_max=179, cht_max=364, egt_max=1302,
      pilot_notes="CHT running slightly warm — 382°F vs typical 360°F. Oil pressure "
                  "nominal. Dismissed as possibly oil type (due for change but not "
                  "checked). Will monitor."),
    F("2026-02-20", "KPHX-KSDL-KPHX", 4830.5, 4832.0,
      oil_temp_max=181, cht_max=370, egt_max=1308, pilot_notes=""),
    # Feb 28 2026: A&P visits, inspects squawk, aircraft grounded
    # (No more flights after Feb 28 2026)
]


# ===========================================================================
# State summary constants
# Used by transform scripts, API, and frontend display logic.
# ===========================================================================

SECOND_OVERHAUL_HOBBS: float = 3350.0  # Engine SMOH baseline for current engine

CLEAN_STATE: dict[str, Any] = {
    "current_hobbs": 4889.5,
    "oil_last_hobbs": 4858.0,
    "oil_next_due_hobbs": 4908.0,
    "oil_hours_overdue": 0.0,
    "annual_due_date": "2026-10-08",
    "annual_days_remaining": 188,
    "airworthiness": "airworthy",
    "open_squawks": ["SQ-2026-OILSEEP"],
    "grounding_squawks": [],
    "engine_smoh": round(4889.5 - SECOND_OVERHAUL_HOBBS, 1),  # 1539.5
}

CAUTION_STATE: dict[str, Any] = {
    "current_hobbs": 4919.2,
    "oil_last_hobbs": 4861.0,
    "oil_next_due_hobbs": 4911.0,
    "oil_hours_overdue": round(4919.2 - 4911.0, 1),  # 8.2
    "annual_due_date": "2026-10-08",
    "annual_days_remaining": 188,
    "airworthiness": "caution",
    "open_squawks": ["SQ-2026-OILSEEP"],
    "grounding_squawks": [],
    "engine_smoh": round(4919.2 - SECOND_OVERHAUL_HOBBS, 1),  # 1569.2
}

GROUNDED_STATE: dict[str, Any] = {
    "current_hobbs": 4897.0,
    "oil_last_hobbs": 4808.0,
    "oil_next_due_hobbs": 4858.0,
    "oil_hours_overdue": round(4897.0 - 4858.0, 1),  # 39.0
    "annual_due_date": "2026-10-08",
    "annual_days_remaining": 188,
    "airworthiness": "not_airworthy",
    "open_squawks": ["SQ-2026-OILSEEP"],
    "grounding_squawks": ["SQ-2026-OILSEEP"],
    "engine_smoh": round(4897.0 - SECOND_OVERHAUL_HOBBS, 1),  # 1547.0
}

STATE_DICTS: dict[str, dict[str, Any]] = {
    "clean": CLEAN_STATE,
    "caution": CAUTION_STATE,
    "grounded": GROUNDED_STATE,
}
