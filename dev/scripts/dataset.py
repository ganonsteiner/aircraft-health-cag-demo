"""
Fleet Dataset — Southwest Airlines, 737 Fleet.

Single source of truth for the 9-aircraft demo fleet:
  N287WN       — NOT_AIRWORTHY  (Engine #1 CFM56-7B failure: compressor blade fracture,
                                  emergency diversion ~30 days ago)
  N246WN       — CAUTION        (Engine #1 EGT deviation +14°C and rising, N1 vibration 1.9 units;
                                  pattern matches N287WN pre-failure telemetry window)
  N231WN, N251WN, N266WN, N277WN, N291WN — AIRWORTHY (Boeing 737-800, basic asset + maintenance records; no flight telemetry)

Calendar fields and ISO timestamps are offsets from get_demo_anchor() (UTC). Hobbs story
numbers stay fixed. Optional env SW_DEMO_DATE=YYYY-MM-DD makes transforms reproducible.

Uses numpy.random.default_rng for fully deterministic output.
Story-beat overrides are applied on top of the random baseline.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

# ---------------------------------------------------------------------------
# Fleet constants
# ---------------------------------------------------------------------------

# All 9 Southwest tails — instrumented planes first, then placeholders
TAILS: tuple[str, ...] = (
    "N287WN", "N246WN", "N220WN", "N235WN",
    "N231WN", "N251WN", "N266WN", "N277WN", "N291WN",
)

# Tails with full flight telemetry and maintenance records
INSTRUMENTED_TAILS: tuple[str, ...] = ("N287WN", "N246WN", "N220WN", "N235WN")

# Tails with asset + maintenance records only (no flight telemetry)
PLACEHOLDER_TAILS: tuple[str, ...] = (
    "N231WN", "N251WN", "N266WN", "N277WN", "N291WN",
)

# Generation parameters per instrumented tail
FLIGHT_COUNTS: dict[str, int] = {"N287WN": 90, "N246WN": 75, "N220WN": 65, "N235WN": 60}
HISTORY_MONTHS: dict[str, int] = {"N287WN": 8, "N246WN": 7, "N220WN": 6, "N235WN": 7}

# Hobbs vs tach: Hobbs includes taxi/ground time in addition to airborne/engine time.
# We model that by adding a small, fixed per-flight increment to Hobbs only.
HOBBS_TAXI_HR_PER_FLIGHT: float = 0.15  # 9 minutes per flight, deterministic

# Airframe flight hours (AFH) at first flight in log (N287WN frozen at failure)
FIRST_HOBBS: dict[str, float] = {"N287WN": 28000.0, "N246WN": 23200.0, "N220WN": 18500.0, "N235WN": 22000.0}

# N287WN: engine failure event AFH (last flight ends here)
N287WN_FAILURE_HOBBS: float = 28368.0
N287WN_FAILURE_DAYS_BEFORE_ANCHOR: int = 30

# N246WN: current AFH (aircraft still flying under enhanced monitoring)
N246WN_CURRENT_HOBBS: float = 23476.0

# Healthy instrumented tails — current AFH
N220WN_CURRENT_HOBBS: float = 18700.0
N235WN_CURRENT_HOBBS: float = 22200.0

CURRENT_HOBBS_SNAPSHOT: dict[str, float] = {
    "N287WN": N287WN_FAILURE_HOBBS,
    "N246WN": N246WN_CURRENT_HOBBS,
    "N220WN": N220WN_CURRENT_HOBBS,
    "N235WN": N235WN_CURRENT_HOBBS,
}

# Engine TBO (CFM56-7B nominal limit in EFH — display only)
ENGINE_TBO: int = 30000

# EFH at last engine shop visit (SMOH-equivalent for display; EFH since shop = current − this)
ENGINE_EFH_AT_SHOP_VISIT: dict[str, float] = {
    "N287WN": 18650.0,
    "N246WN": 14200.0,
}

# Engine #2 EFH at last shop visit (different shop intervals from Engine #1)
ENGINE2_EFH_AT_SHOP: dict[str, float] = {
    "N287WN": 19500.0,
    "N246WN": 14800.0,
    "N220WN": 10200.0,
    "N235WN": 15700.0,
}

# ---------------------------------------------------------------------------
# External ID constants
# ---------------------------------------------------------------------------

POLICY_A_CHECK = "Policy_ACheckInterval"
POLICY_AD_COMPLIANCE = "Policy_ADCompliance"
POLICY_MEL = "Policy_MELCompliance"

FLEET_OWNER_ID = "Southwest_Airlines"

ENGINE_MODEL_EXT_ID = "ENGINE_MODEL_CFM56_7B"

# ---------------------------------------------------------------------------
# Southwest city-pair routes
# ---------------------------------------------------------------------------

ROUTE_CHOICES: list[str] = [
    "DAL-LAX", "MDW-DEN", "HOU-LAS", "PHX-SEA", "BWI-MDW",
    "DAL-MDW", "PHX-LAS", "DAL-DEN", "HOU-MDW", "LAS-MDW",
]
ROUTE_WEIGHTS: list[float] = [0.15, 0.15, 0.12, 0.08, 0.10, 0.12, 0.10, 0.08, 0.05, 0.05]

ROUTE_DURATIONS: dict[str, tuple[float, float]] = {
    "DAL-LAX": (2.5, 3.2),
    "MDW-DEN": (2.0, 2.8),
    "HOU-LAS": (2.8, 3.5),
    "PHX-SEA": (3.0, 4.0),
    "BWI-MDW": (1.5, 2.0),
    "DAL-MDW": (2.0, 2.5),
    "PHX-LAS": (1.2, 1.8),
    "DAL-DEN": (2.2, 2.8),
    "HOU-MDW": (2.8, 3.5),
    "LAS-MDW": (2.8, 3.5),
}

def _make_placeholder_specs() -> dict[str, dict[str, Any]]:
    """
    Generate placeholder-style specs for every aircraft that uses the placeholder
    maintenance generator — that's the non-instrumented tails PLUS N220WN/N235WN,
    which are instrumented but reuse the placeholder maintenance path.
    All are Boeing 737-800, all based at PHX.
    AFH and EFH are deterministically seeded by tail number for variety.
    """
    spec_tails = tuple(PLACEHOLDER_TAILS) + ("N220WN", "N235WN")
    rng = np.random.default_rng(seed=999)
    n = len(spec_tails)
    afh_vals = sorted(rng.integers(8000, 34000, size=n).tolist())
    efh_vals = [int(v * rng.uniform(0.3, 1.0)) for v in afh_vals]
    specs = {}
    for i, tail in enumerate(spec_tails):
        specs[tail] = {
            "model": "Boeing 737-800",
            "base": "PHX",
            "afh": int(afh_vals[i]),
            "efh": int(efh_vals[i]),
        }
    return specs

PLACEHOLDER_SPECS: dict[str, dict[str, Any]] = _make_placeholder_specs()

# ---------------------------------------------------------------------------
# Demo anchor (UTC midnight). All calendar dates in this module derive from it.
# ---------------------------------------------------------------------------


def get_demo_anchor() -> datetime:
    """
    Demo as-of instant: UTC midnight for the resolved calendar day.

    Set SW_DEMO_DATE=YYYY-MM-DD for reproducible CSVs and CI; otherwise today (UTC).
    """
    raw = os.environ.get("SW_DEMO_DATE", "").strip()
    if raw:
        return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    d = datetime.now(timezone.utc).date()
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _d(anchor: datetime, day_offset: int) -> str:
    """Calendar date YYYY-MM-DD for anchor + day_offset."""
    return (anchor + timedelta(days=day_offset)).strftime("%Y-%m-%d")


def n287wn_failure_datetime(anchor: datetime | None = None) -> datetime:
    """N287WN engine failure instant (UTC date boundary)."""
    a = anchor or get_demo_anchor()
    return a - timedelta(days=N287WN_FAILURE_DAYS_BEFORE_ANCHOR)


def format_n287wn_failure_iso(anchor: datetime | None = None) -> str:
    return n287wn_failure_datetime(anchor).strftime("%Y-%m-%d")


def format_n287wn_failure_month_year(anchor: datetime | None = None) -> str:
    return n287wn_failure_datetime(anchor).strftime("%B %Y")


# ---------------------------------------------------------------------------
# Policy data
# ---------------------------------------------------------------------------

OPERATIONAL_POLICIES: list[dict[str, Any]] = [
    {
        "externalId": POLICY_A_CHECK,
        "title": "A-Check Maintenance Interval",
        "description": (
            "Boeing 737 A-check required every 500–600 flight hours or 45 calendar days, "
            "whichever comes first. Includes inspection of flight controls, landing gear, "
            "hydraulic systems, and engine cowlings. Engine oil and hydraulic fluid serviced. "
            "References Boeing 737 Maintenance Planning Document (MPD)."
        ),
        "rule": "a_check_flight_hours=550; a_check_calendar_days=45",
        "category": "scheduled_maintenance",
        "references": "Boeing 737 MPD; Southwest Airlines GMM Chapter 5",
    },
    {
        "externalId": POLICY_AD_COMPLIANCE,
        "title": "Airworthiness Directive (AD) Compliance",
        "description": (
            "All applicable FAA Airworthiness Directives must be complied with per 14 CFR 39. "
            "CFM56-7B applicable ADs: AD 2020-14-06 (fan blade inspection every 2,500 EFH), "
            "AD 2018-23-09 (HPT stage 1 blade inspection every 1,000 EFH), "
            "AD 2022-01-04 (combustor inspection). Boeing 737 structural ADs: AD 2020-09-07 "
            "(nacelle strut inspection)."
        ),
        "rule": "ad_compliance_required=true; cfm56_fan_blade_interval_efh=2500; hpt_blade_interval_efh=1000",
        "category": "airworthiness",
        "references": "14 CFR 39; FAA AD 2020-14-06; AD 2018-23-09; AD 2022-01-04; AD 2020-09-07",
    },
    {
        "externalId": POLICY_MEL,
        "title": "Minimum Equipment List (MEL) Compliance",
        "description": (
            "All Southwest Airlines aircraft must be dispatched in accordance with the "
            "FAA-approved Minimum Equipment List. Category A MEL items require repair within "
            "3 calendar days; Category B within 10 days; Category C within 120 days. "
            "Aircraft with items beyond MEL limits are NOT AIRWORTHY."
        ),
        "rule": "mel_category_a_days=3; mel_category_b_days=10; mel_category_c_days=120; dispatch_requires_mel_compliance=true",
        "category": "airworthiness",
        "references": "FAA-approved Southwest Airlines MEL; Boeing 737 MEL; 14 CFR 91.213",
    },
]

FLEET_OWNER: dict[str, Any] = {
    "externalId": FLEET_OWNER_ID,
    "name": "Southwest Airlines",
    "description": (
        "Major US low-cost carrier operating a fleet of 47 Boeing 737-800 aircraft "
        "based at Phoenix Sky Harbor (PHX). Fleet maintained under FAA-approved maintenance program."
    ),
    "location": "HQ: Dallas Love Field (DAL), Texas",
    "contact": "maintenance@southwestairlines.com",
}

# ---------------------------------------------------------------------------
# CFM56-7B / Boeing 737-800 normal parameter ranges
# ---------------------------------------------------------------------------

NORMAL_PARAMS: dict[str, tuple[float, float]] = {
    "egt_deviation":   (-5.0,  8.0),     # °C above baseline
    "n1_vibration":    (0.30,  1.40),    # vibration units
    "n2_speed":        (91.0, 97.0),     # % N2
    "fuel_flow_kgh":   (2200.0, 2650.0), # kg/hr per engine (cruise)
    "oil_pressure_min": (42.0, 58.0),    # psi
    "oil_pressure_max": (55.0, 72.0),    # psi
    "oil_temp_max":    (82.0, 102.0),    # °C
}

CAUTION_PARAMS: dict[str, tuple[float, float]] = {
    "egt_deviation":  (10.0, 16.0),
    "n1_vibration":   (1.50, 2.20),
    "oil_temp_max":   (102.0, 115.0),
}

CRITICAL_PARAMS: dict[str, tuple[float, float]] = {
    "egt_deviation":   (17.0, 23.0),
    "n1_vibration":    (2.20, 2.90),
    "oil_pressure_min": (28.0, 40.0),
    "oil_temp_max":    (112.0, 128.0),
}

# ---------------------------------------------------------------------------
# Flight parameter generation (737-specific)
# ---------------------------------------------------------------------------

def _gen_flight_params_737(
    rng: np.random.Generator,
    route: str,
    *,
    egt_deviation_override: float | None = None,
    n1_vib_override: float | None = None,
    is_caution: bool = False,
    is_critical: bool = False,
) -> dict[str, Any]:
    """Generate realistic CFM56-7B flight parameters for a single flight."""
    dur_lo, dur_hi = ROUTE_DURATIONS[route]
    raw_dur = rng.beta(2.0, 3.0) * (dur_hi - dur_lo) + dur_lo
    duration = float(np.clip(raw_dur, 1.0, 5.0))

    def _p(key: str) -> float:
        if is_critical and key in CRITICAL_PARAMS:
            lo, hi = CRITICAL_PARAMS[key]
        elif is_caution and key in CAUTION_PARAMS:
            lo, hi = CAUTION_PARAMS[key]
        else:
            lo, hi = NORMAL_PARAMS[key]
        return float(rng.uniform(lo, hi))

    egt = egt_deviation_override if egt_deviation_override is not None else _p("egt_deviation")
    n1v = n1_vib_override if n1_vib_override is not None else _p("n1_vibration")

    oil_lo = round(_p("oil_pressure_min"), 1)
    oil_hi = round(_p("oil_pressure_max"), 1)
    if oil_lo > oil_hi:
        oil_lo, oil_hi = oil_hi, oil_lo
    oil_hi = max(oil_hi, round(oil_lo + 0.1, 1))

    return {
        "duration":         round(duration, 2),
        "egt_deviation":    round(egt, 1),
        "n1_vibration":     round(n1v, 2),
        "n2_speed":         round(_p("n2_speed"), 1),
        "fuel_flow_kgh":    round(_p("fuel_flow_kgh"), 0),
        "oil_pressure_min": oil_lo,
        "oil_pressure_max": oil_hi,
        "oil_temp_max":     round(_p("oil_temp_max"), 1),
        "cycles": 1,
    }


def _gen_pilot_notes_737(
    rng: np.random.Generator,
    params: dict[str, Any],
    tail: str,
    idx: int,
    *,
    is_caution: bool = False,
    is_critical: bool = False,
    is_failure_flight: bool = False,
) -> str:
    egt = params["egt_deviation"]
    vib = params["n1_vibration"]

    if tail == "N287WN":
        if is_failure_flight:
            if idx >= 88:
                return (
                    f"Engine #1 EGT deviation +{egt:.0f}°C, N1 vibration {vib:.2f} — severe. "
                    "Compressor stall on #1 during climb, uncontained blade failure. "
                    "Declared emergency, engine shutdown, diverted to ABQ. Single-engine landing. "
                    "NTSB notified. Aircraft grounded."
                )
            elif idx >= 86:
                return (
                    f"Engine #1 EGT running +{egt:.0f}°C above baseline. N1 vib {vib:.2f}. "
                    "Crew reduced power on #1, ACARS alert sent to dispatch. "
                    "Requesting immediate inspection on arrival."
                )
            else:
                return (
                    f"Engine #1 EGT deviation +{egt:.0f}°C. N1 vibration {vib:.2f}. "
                    "Elevated but within dispatch limits. Logged for maintenance."
                )
        elif is_critical:
            opts = [
                f"Engine #1 EGT dev +{egt:.0f}°C, N1 vib {vib:.2f}. ACARS alert issued. Maintenance flagged.",
                f"EGT deviation on #1 now +{egt:.0f}°C — trending worse. Vib {vib:.2f}. Recommend borescope.",
                f"Engine #1 running hot. EGT +{egt:.0f}°C above baseline, vib {vib:.2f}. Monitoring closely.",
            ]
            return str(rng.choice(opts))
        elif is_caution:
            opts = [
                f"Engine #1 EGT dev +{egt:.0f}°C noted. Logged for maintenance review.",
                f"Slight EGT deviation on #1 — +{egt:.0f}°C. N1 vib {vib:.2f}. Within advisory limits.",
                f"EGT margin trending. #1 at +{egt:.0f}°C above baseline. Monitoring.",
            ]
            return str(rng.choice(opts))
        elif rng.random() < 0.15:
            return str(rng.choice([
                "Normal flight, all parameters in limits.",
                "All engine parameters nominal throughout.",
                "Smooth flight, no anomalies.",
                "Both engines normal. No issues.",
            ]))

    elif tail == "N246WN":
        if is_critical:
            opts = [
                f"Engine #1 EGT dev +{egt:.0f}°C, N1 vib {vib:.2f}. Per MX tracking, monitoring closely.",
                f"EGT deviation on #1: +{egt:.0f}°C. Vibration at {vib:.2f}. ACARS advisory active.",
                f"Engine #1 elevated EGT +{egt:.0f}°C above baseline. Crew briefed on monitoring protocol.",
            ]
            return str(rng.choice(opts))
        elif is_caution:
            opts = [
                f"Engine #1 EGT dev +{egt:.0f}°C logged per maintenance tracking.",
                f"EGT deviation on #1: +{egt:.0f}°C. N1 vib {vib:.2f}. Monitoring.",
                f"Slight EGT elevation on #1 — +{egt:.0f}°C. Otherwise normal.",
            ]
            return str(rng.choice(opts))
        elif rng.random() < 0.12:
            return str(rng.choice([
                "Normal operations.",
                "All parameters in limits.",
                "Smooth flight.",
                "No anomalies.",
            ]))

    return ""


def _generate_flights_n287wn() -> list[dict[str, Any]]:
    """90 flights for N287WN ending at engine #1 failure ~30 days before demo anchor."""
    rng = np.random.default_rng(seed=389)
    tail = "N287WN"
    count = FLIGHT_COUNTS[tail]
    months = HISTORY_MONTHS[tail]
    now = get_demo_anchor()
    history_start = now - timedelta(days=months * 30)
    failure_date = n287wn_failure_datetime(now)
    span_days = max(1.0, (failure_date - history_start).total_seconds() / 86400.0)

    # Phase boundaries:
    # 0–83:  Normal, mild early EGT drift (+2→+7°C, vib 0.8→1.4)
    # 84–87: Caution — EGT elevated, vib increasing
    # 88–89: Failure sequence — severe EGT, compressor blade failure, emergency declared

    routes = rng.choice(ROUTE_CHOICES, size=count, p=ROUTE_WEIGHTS)
    time_offsets = sorted(rng.uniform(0.0, 1.0, size=count))

    scheduled: list[tuple[datetime, str]] = []
    for i in range(count):
        elapsed_days = time_offsets[i] * span_days
        flight_dt = history_start + timedelta(days=elapsed_days)
        if flight_dt > failure_date:
            flight_dt = failure_date - timedelta(minutes=30)
        scheduled.append((flight_dt, str(routes[i])))
    scheduled.sort(key=lambda x: x[0])

    draft: list[dict[str, Any]] = []
    for idx, (flight_dt, route) in enumerate(scheduled):
        is_caution = 84 <= idx < 88
        is_critical = False
        is_failure = idx >= 88

        # Compute graduated EGT and vibration overrides for early/normal phase
        if idx < 84:
            t = idx / 83.0
            egt_base = 2.0 + t * 5.0       # +2 → +7
            egt_noise = float(rng.uniform(-1.5, 2.5))
            egt_override = max(0.0, round(egt_base + egt_noise, 1))
            vib_base = 0.8 + t * 0.6       # 0.8 → 1.4
            vib_noise = float(rng.uniform(-0.15, 0.20))
            vib_override = max(0.3, round(vib_base + vib_noise, 2))
        else:
            egt_override = None
            vib_override = None

        params = _gen_flight_params_737(
            rng, route,
            egt_deviation_override=egt_override,
            n1_vib_override=vib_override,
            is_caution=is_caution,
            is_critical=is_critical or is_failure,
        )
        pilot_notes = _gen_pilot_notes_737(
            rng, params, tail, idx,
            is_caution=is_caution,
            is_critical=is_critical,
            is_failure_flight=is_failure,
        )
        draft.append({
            "timestamp": flight_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "route": route,
            "params": params,
            "pilot_notes": pilot_notes,
            "flight_index": idx,
        })

    # Scale durations so total span matches the *tach* target. Hobbs advances
    # slightly faster due to taxi time modeled by HOBBS_TAXI_HR_PER_FLIGHT.
    target_span = float(N287WN_FAILURE_HOBBS - FIRST_HOBBS[tail])
    raw_total = sum(float(row["params"]["duration"]) for row in draft)
    taxi_total = float(len(draft)) * HOBBS_TAXI_HR_PER_FLIGHT
    tach_target_span = max(1.0, target_span - taxi_total)
    scale = tach_target_span / raw_total if raw_total > 0 else 1.0

    hobbs = float(FIRST_HOBBS[tail])
    tach = float(FIRST_HOBBS[tail])
    flights: list[dict[str, Any]] = []
    for idx, row in enumerate(draft):
        p = row["params"]
        dur = round(float(p["duration"]) * scale, 2)
        if idx == len(draft) - 1:
            # Last flight: make Hobbs end exactly at the failure snapshot.
            dur = round(float(N287WN_FAILURE_HOBBS) - hobbs - HOBBS_TAXI_HR_PER_FLIGHT, 2)
        dur = max(1.0, dur)

        flights.append({
            "timestamp":        row["timestamp"],
            "hobbs_start":      round(hobbs, 1),
            "hobbs_end":        round(hobbs + dur + HOBBS_TAXI_HR_PER_FLIGHT, 1),
            "tach_start":       round(tach, 1),
            "tach_end":         round(tach + dur, 1),
            "route":            row["route"],
            "duration":         dur,
            "egt_deviation":    p["egt_deviation"],
            "n1_vibration":     p["n1_vibration"],
            "n2_speed":         p["n2_speed"],
            "fuel_flow_kgh":    p["fuel_flow_kgh"],
            "oil_pressure_min": p["oil_pressure_min"],
            "oil_pressure_max": p["oil_pressure_max"],
            "oil_temp_max":     p["oil_temp_max"],
            "cycles":           1,
            "pilot_notes":      row["pilot_notes"],
            "tail":             tail,
            "flight_index":     row["flight_index"],
        })
        hobbs = round(hobbs + dur + HOBBS_TAXI_HR_PER_FLIGHT, 1)
        tach = round(tach + dur, 1)

    return flights


def _generate_healthy_flights(tail: str) -> list[dict[str, Any]]:
    """Generate healthy flights for N220WN and N235WN (all params in normal range)."""
    seeds = {"N220WN": 472, "N235WN": 831}
    rng = np.random.default_rng(seed=seeds[tail])
    count = FLIGHT_COUNTS[tail]
    months = HISTORY_MONTHS[tail]
    now = get_demo_anchor()
    history_start = now - timedelta(days=months * 30)
    total_span_days = float(months * 30)
    target_hobbs = CURRENT_HOBBS_SNAPSHOT[tail]
    first_hobbs = FIRST_HOBBS[tail]

    routes = rng.choice(ROUTE_CHOICES, size=count, p=ROUTE_WEIGHTS)
    day_offsets = _chronological_day_offsets_into_history(rng, count, total_span_days)

    # EGT and vib caps per tail (spec from plan)
    egt_max = 2.0 if tail == "N220WN" else 3.0
    vib_max = 0.9 if tail == "N220WN" else 1.1

    draft_params: list[tuple[dict[str, Any], str, int]] = []
    for i in range(count):
        route = str(routes[i])
        egt_override = round(float(rng.uniform(-3.0, egt_max)), 1)
        vib_override = round(float(rng.uniform(0.3, vib_max)), 2)
        params = _gen_flight_params_737(
            rng, route,
            egt_deviation_override=egt_override,
            n1_vib_override=vib_override,
        )
        draft_params.append((params, route, i))

    raw_total = sum(float(p["duration"]) for p, _, _ in draft_params)
    taxi_total = float(count) * HOBBS_TAXI_HR_PER_FLIGHT
    tach_target_span = max(1.0, float(target_hobbs - first_hobbs) - taxi_total)
    scale = tach_target_span / raw_total if raw_total > 0 else 1.0

    hobbs = first_hobbs
    tach = first_hobbs
    flights: list[dict[str, Any]] = []
    for i, (params, route, fi) in enumerate(draft_params):
        flight_dt = history_start + timedelta(days=float(day_offsets[i]))
        dur = round(float(params["duration"]) * scale, 2)
        if i == count - 1:
            dur = round(float(target_hobbs) - hobbs - HOBBS_TAXI_HR_PER_FLIGHT, 2)
        dur = max(1.0, dur)

        flights.append({
            "timestamp":        flight_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "hobbs_start":      round(hobbs, 1),
            "hobbs_end":        round(hobbs + dur + HOBBS_TAXI_HR_PER_FLIGHT, 1),
            "tach_start":       round(tach, 1),
            "tach_end":         round(tach + dur, 1),
            "route":            route,
            "duration":         dur,
            "egt_deviation":    params["egt_deviation"],
            "n1_vibration":     params["n1_vibration"],
            "n2_speed":         params["n2_speed"],
            "fuel_flow_kgh":    params["fuel_flow_kgh"],
            "oil_pressure_min": params["oil_pressure_min"],
            "oil_pressure_max": params["oil_pressure_max"],
            "oil_temp_max":     params["oil_temp_max"],
            "cycles":           1,
            "pilot_notes":      "",
            "tail":             tail,
            "flight_index":     fi,
        })
        hobbs = round(hobbs + dur + HOBBS_TAXI_HR_PER_FLIGHT, 1)
        tach = round(tach + dur, 1)

    return flights


def generate_flights(tail: str) -> list[dict[str, Any]]:
    """Generate deterministic flight records for one aircraft.

    Returns an empty list for placeholder tails (N231WN–N209WN).
    """
    if tail == "N287WN":
        return _generate_flights_n287wn()

    if tail in ("N220WN", "N235WN"):
        return _generate_healthy_flights(tail)

    if tail not in INSTRUMENTED_TAILS:
        return []

    # N246WN
    rng = np.random.default_rng(seed=251)
    count = FLIGHT_COUNTS[tail]
    months = HISTORY_MONTHS[tail]
    now = get_demo_anchor()
    history_start = now - timedelta(days=months * 30)
    total_span_days = float(months * 30)

    routes = rng.choice(ROUTE_CHOICES, size=count, p=ROUTE_WEIGHTS)
    day_offsets = _chronological_day_offsets_into_history(rng, count, total_span_days)

    target_hobbs = N246WN_CURRENT_HOBBS
    first_hobbs = FIRST_HOBBS[tail]

    # Build draft params first, then scale durations to hit target AFH
    draft_params: list[tuple[dict[str, Any], str, int]] = []
    for i in range(count):
        # N246WN mirrors N287WN's pre-failure curve, shifted later:
        # flights 0–67: normal (+1→+6°C EGT, vib 0.5→1.3)
        # flights 68–72: caution (+6→+14°C, vib 1.5→1.9)
        # flights 73–74: critical-approaching (+13→+15°C, vib 1.8→2.0) — open squawk
        is_caution = 68 <= i < 73
        is_critical = i >= 73

        if i < 68:
            t = i / 67.0
            egt_base = 1.0 + t * 5.0       # +1 → +6
            egt_noise = float(rng.uniform(-2.0, 2.5))
            egt_override = max(0.0, round(egt_base + egt_noise, 1))
            vib_base = 0.5 + t * 0.8       # 0.5 → 1.3
            vib_noise = float(rng.uniform(-0.15, 0.20))
            vib_override = max(0.3, round(vib_base + vib_noise, 2))
        else:
            egt_override = None
            vib_override = None

        route = str(routes[i])
        params = _gen_flight_params_737(
            rng, route,
            egt_deviation_override=egt_override,
            n1_vib_override=vib_override,
            is_caution=is_caution,
            is_critical=is_critical,
        )
        draft_params.append((params, route, i))

    # Scale durations to match the *tach* target. Hobbs advances slightly faster
    # due to taxi time modeled by HOBBS_TAXI_HR_PER_FLIGHT.
    raw_total = sum(float(p["duration"]) for p, _, _ in draft_params)
    taxi_total = float(count) * HOBBS_TAXI_HR_PER_FLIGHT
    tach_target_span = max(1.0, float(target_hobbs - first_hobbs) - taxi_total)
    scale = tach_target_span / raw_total if raw_total > 0 else 1.0

    hobbs = first_hobbs
    tach = first_hobbs
    flights: list[dict[str, Any]] = []
    for i, (params, route, fi) in enumerate(draft_params):
        is_caution = 68 <= fi < 73
        is_critical = fi >= 73

        flight_dt = history_start + timedelta(days=float(day_offsets[i]))
        dur = round(float(params["duration"]) * scale, 2)
        if i == count - 1:
            dur = round(float(target_hobbs) - hobbs - HOBBS_TAXI_HR_PER_FLIGHT, 2)
        dur = max(1.0, dur)

        pilot_notes = _gen_pilot_notes_737(
            rng, params, tail, fi,
            is_caution=is_caution,
            is_critical=is_critical,
        )

        flights.append({
            "timestamp":        flight_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "hobbs_start":      round(hobbs, 1),
            "hobbs_end":        round(hobbs + dur + HOBBS_TAXI_HR_PER_FLIGHT, 1),
            "tach_start":       round(tach, 1),
            "tach_end":         round(tach + dur, 1),
            "route":            route,
            "duration":         dur,
            "egt_deviation":    params["egt_deviation"],
            "n1_vibration":     params["n1_vibration"],
            "n2_speed":         params["n2_speed"],
            "fuel_flow_kgh":    params["fuel_flow_kgh"],
            "oil_pressure_min": params["oil_pressure_min"],
            "oil_pressure_max": params["oil_pressure_max"],
            "oil_temp_max":     params["oil_temp_max"],
            "cycles":           1,
            "pilot_notes":      pilot_notes,
            "tail":             tail,
            "flight_index":     fi,
        })
        hobbs = round(hobbs + dur + HOBBS_TAXI_HR_PER_FLIGHT, 1)
        tach = round(tach + dur, 1)

    return flights


def _chronological_day_offsets_into_history(
    rng: np.random.Generator,
    count: int,
    total_span_days: float,
) -> np.ndarray:
    """Strictly increasing offsets in [0, total_span_days], recent activity guaranteed."""
    RECENT_FLIGHT_COUNT = 6
    RECENT_FLIGHT_DAYS_BEFORE_END = 14

    if count <= 0:
        return np.array([], dtype=float)
    k = min(RECENT_FLIGHT_COUNT, count)
    early_n = count - k
    t = float(total_span_days)
    r = float(RECENT_FLIGHT_DAYS_BEFORE_END)
    if t <= r + 1e-9:
        return np.sort(rng.uniform(0.0, t, size=count))
    early = np.sort(rng.uniform(0.0, t - r, size=early_n)) if early_n > 0 else np.array([], dtype=float)
    recent = np.sort(rng.uniform(t - r, t, size=k))
    if early_n > 0:
        return np.concatenate([early, recent])
    return recent


# ---------------------------------------------------------------------------
# Maintenance records
# ---------------------------------------------------------------------------

def _get_placeholder_maintenance_records(tail: str, anchor: datetime) -> list[dict[str, Any]]:
    """Generate realistic maintenance records for a placeholder aircraft (no flight telemetry)."""
    tail_num = int(tail[1:4])  # e.g. N231WN → 231
    rng = np.random.default_rng(seed=tail_num * 7 + 13)
    spec = PLACEHOLDER_SPECS[tail]
    afh = float(spec["afh"])
    # Use actual hobbs snapshot when available (instrumented tails like N220WN/N235WN have
    # a CURRENT_HOBBS_SNAPSHOT that differs from the randomly-generated placeholder spec efh)
    efh = float(CURRENT_HOBBS_SNAPSHOT.get(tail, spec["efh"]))

    # Last oil change: 1-8 weeks ago
    oil_weeks_ago = int(rng.integers(1, 9))
    last_oil = anchor - timedelta(weeks=oil_weeks_ago)
    next_oil = last_oil + timedelta(days=122)  # 4-month interval
    oil_afh = round(afh - oil_weeks_ago * 15, 0)
    oil_efh = round(efh - oil_weeks_ago * 15, 0)

    # Last A-check: 1-5 months ago
    acheck_months_ago = int(rng.integers(1, 6))
    last_acheck = anchor - timedelta(days=acheck_months_ago * 30)
    next_acheck = last_acheck + timedelta(days=365)
    acheck_afh = round(afh - acheck_months_ago * 200, 0)
    acheck_efh = round(efh - acheck_months_ago * 200, 0)

    # Routine borescope inspection: 2-6 months ago
    bore_months_ago = int(rng.integers(2, 7))
    last_bore = anchor - timedelta(days=bore_months_ago * 30)
    next_bore = last_bore + timedelta(days=155)  # ~5 months
    bore_afh = round(afh - bore_months_ago * 200, 0)
    bore_efh = round(efh - bore_months_ago * 200, 0)

    mechanic = "Southwest Airlines Line Maintenance — PHX"
    inspector = "Southwest Airlines IA — PHX Station"

    return [
        {
            "date": last_bore.strftime("%Y-%m-%d"),
            "component_id": f"{tail}-ENGINE-1",
            "maintenance_type": "borescope_inspection",
            "description": (
                "Engine #1 CFM56-7B borescope — scheduled 500 EFH interval. "
                "Fan blade inspection, HPC/HPT visual inspection. No findings. "
                "EGT deviation within normal limits. Aircraft returned to service."
            ),
            "hobbs_at_service": max(1.0, bore_afh),
            "tach_at_service": max(1.0, bore_efh),
            "next_due_hobbs": "",
            "next_due_date": next_bore.strftime("%Y-%m-%d"),
            "mechanic": mechanic,
            "inspector": "",
            "ad_reference": "AD 2020-14-06",
            "sb_reference": "CFM SB 72-0842",
            "squawk_id": "",
            "resolved_by": "",
            "parts_replaced": "",
            "labor_hours": 10.0,
            "signoff_type": "return_to_service",
            "severity": "",
            "status": "",
        },
        {
            "date": last_acheck.strftime("%Y-%m-%d"),
            "component_id": tail,
            "maintenance_type": "a_check",
            "description": (
                "A-check — 550 flight hour interval. Flight control rigging checked, "
                "hydraulic fluid serviced, engine cowlings inspected. Engine oil serviced. "
                "No discrepancies. Aircraft returned to service."
            ),
            "hobbs_at_service": max(1.0, acheck_afh),
            "tach_at_service": max(1.0, acheck_efh),
            "next_due_hobbs": "",
            "next_due_date": next_acheck.strftime("%Y-%m-%d"),
            "mechanic": mechanic,
            "inspector": inspector,
            "ad_reference": "AD 2020-09-07",
            "sb_reference": "",
            "squawk_id": "",
            "resolved_by": "",
            "parts_replaced": "Engine oil (both engines); hydraulic fluid top-off",
            "labor_hours": 24.0,
            "signoff_type": "inspection_approval",
            "severity": "",
            "status": "",
        },
        {
            "date": last_oil.strftime("%Y-%m-%d"),
            "component_id": f"{tail}-ENGINE-1",
            "maintenance_type": "oil_change",
            "description": (
                "Engine #1 oil change — routine 120-day service interval. "
                "Engine oil drained and refilled. Oil filter replaced. No discrepancies."
            ),
            "hobbs_at_service": max(1.0, oil_afh),
            "tach_at_service": max(1.0, oil_efh),
            "next_due_hobbs": "",
            "next_due_tach": max(1.0, oil_efh) + 200 if tail in INSTRUMENTED_TAILS else "",
            "next_due_date": next_oil.strftime("%Y-%m-%d"),
            "mechanic": mechanic,
            "inspector": "",
            "ad_reference": "",
            "sb_reference": "",
            "squawk_id": "",
            "resolved_by": "",
            "parts_replaced": "Engine oil; oil filter",
            "labor_hours": 2.0,
            "signoff_type": "return_to_service",
            "severity": "",
            "status": "",
        },
    ]


def build_all_maintenance_by_tail(anchor: datetime | None = None) -> dict[str, list[dict[str, Any]]]:
    """Per-tail maintenance CSV rows, ordered for export.

    Calendar date fields are offsets from the demo anchor; tach/hobbs match the fixed story.
    """
    a = anchor or get_demo_anchor()
    failure = n287wn_failure_datetime(a)
    fail_iso = format_n287wn_failure_iso(a)

    # N287WN post-failure timeline
    n287wn_post_inspection_date = (failure + timedelta(days=5)).strftime("%Y-%m-%d")
    n287wn_engine_removal_date = (failure + timedelta(days=12)).strftime("%Y-%m-%d")

    # N246WN maintenance timeline
    n246wn_last_acheck = a - timedelta(days=118)
    n246wn_annual = a - timedelta(days=156)       # ~Nov 15 2025
    n246wn_oil_change = a - timedelta(days=57)    # ~Feb 23 2026
    n246wn_borescope1 = a - timedelta(days=95)
    n246wn_borescope2 = a - timedelta(days=28)

    maint: dict[str, list[dict[str, Any]]] = {
        "N287WN": [
            {
                "date": _d(a, -580),
                "component_id": "N287WN",
                "maintenance_type": "c_check",
                "description": (
                    "C-check heavy maintenance visit. Airframe inspection per Boeing 737 MPD. "
                    "Engine #1 and #2 borescope performed — no findings. Landing gear overhauled. "
                    "All systems returned to service."
                ),
                "hobbs_at_service": 27650.0,
                "tach_at_service": 27650.0,
                "next_due_hobbs": "",
                "next_due_date": _d(a, 1970),
                "mechanic": "Southwest Airlines MRO — Dallas Heavy Maintenance",
                "inspector": "Southwest Airlines IA — J. Martinez #SW-IA-0047",
                "ad_reference": "AD 2020-09-07; AD 2020-14-06; AD 2022-01-04",
                "sb_reference": "Boeing SB 737-71-1052",
                "squawk_id": "",
                "resolved_by": "",
                "parts_replaced": "Landing gear seals; hydraulic actuators; multiple fasteners per SB",
                "labor_hours": 4800.0,
                "signoff_type": "inspection_approval",
            },
            {
                "date": _d(a, -210),
                "component_id": "N287WN",
                "maintenance_type": "annual",
                "description": (
                    "FAA annual airworthiness inspection — 12-month interval. "
                    "All systems inspected per Boeing 737 MPD. No discrepancies. "
                    "Certificate of airworthiness reissued."
                ),
                "hobbs_at_service": 27900.0,
                "tach_at_service": 27900.0,
                "next_due_hobbs": "",
                "next_due_date": _d(a, 155),
                "mechanic": "Southwest Airlines MRO — PHX",
                "inspector": "Southwest Airlines IA — J. Martinez #SW-IA-0047",
                "ad_reference": "",
                "sb_reference": "",
                "squawk_id": "",
                "resolved_by": "",
                "parts_replaced": "",
                "labor_hours": 14.0,
                "signoff_type": "inspection_approval",
                "severity": "",
                "status": "",
            },
            {
                "date": _d(a, -70),
                "component_id": "N287WN-ENGINE-1",
                "maintenance_type": "oil_change",
                "description": (
                    "Engine #1 oil change — routine 120-day service interval. "
                    "Engine oil drained and refilled. Oil filter replaced. No discrepancies."
                ),
                "hobbs_at_service": 28260.0,
                "tach_at_service": 28260.0,
                "next_due_hobbs": "",
                "next_due_tach": 28460.0,
                "next_due_date": _d(a, 52),
                "mechanic": "Southwest Airlines Line Maintenance — PHX",
                "inspector": "",
                "ad_reference": "",
                "sb_reference": "",
                "squawk_id": "",
                "resolved_by": "",
                "parts_replaced": "Engine oil; oil filter",
                "labor_hours": 2.0,
                "signoff_type": "return_to_service",
                "severity": "",
                "status": "",
            },
            {
                "date": _d(a, -190),
                "component_id": "N287WN-ENGINE-1",
                "maintenance_type": "borescope_inspection",
                "description": (
                    "Engine #1 CFM56-7B borescope — 500 EFH scheduled interval. "
                    "Fan blade visual inspection, HPC/HPT borescope. Minor leading edge nicks "
                    "on fan blade #7, within limits. EGT deviation measured at +5°C above baseline. "
                    "Trend monitoring recommended per CFM SB 72-0842."
                ),
                "hobbs_at_service": 28020.0,
                "tach_at_service": 28020.0,
                "next_due_hobbs": "",
                "next_due_date": _d(a, 155),
                "mechanic": "Southwest Airlines MRO — T. Rhodes, A&P #SW-AP-0193",
                "inspector": "",
                "ad_reference": "AD 2020-14-06",
                "sb_reference": "CFM SB 72-0842",
                "squawk_id": "",
                "resolved_by": "",
                "parts_replaced": "",
                "labor_hours": 12.0,
                "signoff_type": "return_to_service",
            },
            {
                "date": _d(a, -62),
                "component_id": "N287WN-ENGINE-1",
                "maintenance_type": "borescope_inspection",
                "description": (
                    "On-condition borescope — EGT deviation exceeded +10°C ACARS advisory. "
                    "HPT stage 1 nozzle guide vane erosion noted. Fan blade #7 nicks progressed "
                    "— still within limits but trending. EGT deviation +14°C. Compressor wash "
                    "performed. SQUAWK OPENED: repeat borescope in 100 EFH or at next EGT exceedance."
                ),
                "hobbs_at_service": 28230.0,
                "tach_at_service": 28230.0,
                "next_due_hobbs": "",
                "next_due_date": _d(a, -30),
                "mechanic": "Southwest Airlines MRO — T. Rhodes, A&P #SW-AP-0193",
                "inspector": "Southwest Airlines IA — J. Martinez #SW-IA-0047",
                "ad_reference": "AD 2020-14-06; AD 2018-23-09",
                "sb_reference": "CFM SB 72-0842",
                "squawk_id": "SQ-N287WN-001",
                "resolved_by": "",
                "parts_replaced": "Engine inlet cleaning chemicals",
                "labor_hours": 18.0,
                "signoff_type": "return_to_service",
            },
            {
                "date": fail_iso,
                "component_id": "N287WN-ENGINE-1",
                "maintenance_type": "squawk",
                "description": (
                    f"UNCONTAINED ENGINE #1 FAILURE on {fail_iso}. CFM56-7B compressor stage 3 "
                    "blade fracture during initial climb. Multiple blade fragments ejected. "
                    "Flight crew declared emergency, engine #1 shut down, diverted to ABQ. "
                    "Single-engine landing. Aircraft NOT AIRWORTHY. Engine #1 removal required. "
                    "NTSB notification filed. FAA AD compliance review initiated."
                ),
                "hobbs_at_service": N287WN_FAILURE_HOBBS,
                "tach_at_service": N287WN_FAILURE_HOBBS,
                "next_due_hobbs": "",
                "next_due_date": "",
                "mechanic": "Southwest Airlines MRO — Emergency Response Team",
                "inspector": "Southwest Airlines IA — J. Martinez #SW-IA-0047",
                "ad_reference": "AD 2020-14-06; AD 2018-23-09; AD 2022-01-04",
                "sb_reference": "",
                "squawk_id": "SQ-N287WN-002",
                "resolved_by": "",
                "parts_replaced": "",
                "labor_hours": 6.0,
                "signoff_type": "",
                "severity": "grounding",
                "status": "open",
            },
            {
                "date": n287wn_engine_removal_date,
                "component_id": "N287WN-ENGINE-1",
                "maintenance_type": "post_accident_inspection",
                "description": (
                    f"Post-failure teardown of Engine #1 following in-flight failure on {fail_iso}. "
                    "Compressor stage 3 blade root fatigue fracture confirmed. Metallurgical analysis: "
                    "high-cycle fatigue with pre-existing micro-crack at trailing edge. HPT stage 1 "
                    "blades show thermal coating spallation — correlates with EGT deviation trend. "
                    "Engine #1 removed from wing. Replacement CFM56-7B sourced from CFM International. "
                    "Engine #2 borescope performed — no anomalies."
                ),
                "hobbs_at_service": N287WN_FAILURE_HOBBS,
                "tach_at_service": N287WN_FAILURE_HOBBS,
                "next_due_hobbs": "",
                "next_due_date": "",
                "mechanic": "Southwest Airlines MRO — Heavy Maintenance, Dallas",
                "inspector": "Southwest Airlines IA — J. Martinez #SW-IA-0047",
                "ad_reference": "AD 2020-14-06; AD 2018-23-09",
                "sb_reference": "CFM SB 72-1218",
                "squawk_id": "SQ-N287WN-002",
                "resolved_by": "",
                "parts_replaced": "",
                "labor_hours": 80.0,
                "signoff_type": "conformity_statement",
            },
        ],

        "N246WN": [
            {
                "date": n246wn_annual.strftime("%Y-%m-%d"),
                "component_id": "N246WN",
                "maintenance_type": "annual",
                "description": (
                    "FAA annual airworthiness inspection — 12-month interval. "
                    "Flight controls, avionics, structures, powerplants all inspected. "
                    "No discrepancies. Certificate of airworthiness reissued."
                ),
                "hobbs_at_service": 23200.0,
                "tach_at_service": 23200.0,
                "next_due_hobbs": "",
                "next_due_date": (n246wn_annual + timedelta(days=365)).strftime("%Y-%m-%d"),
                "mechanic": "Southwest Airlines MRO — PHX",
                "inspector": "Southwest Airlines IA — K. Osei #SW-IA-0112",
                "ad_reference": "",
                "sb_reference": "",
                "squawk_id": "",
                "resolved_by": "",
                "parts_replaced": "",
                "labor_hours": 14.0,
                "signoff_type": "inspection_approval",
            },
            {
                "date": n246wn_last_acheck.strftime("%Y-%m-%d"),
                "component_id": "N246WN",
                "maintenance_type": "a_check",
                "description": (
                    "A-check — 550 flight hour interval. Flight control rigging checked, "
                    "hydraulic fluid serviced, engine cowlings inspected. Engine #1 and #2 "
                    "oil serviced. No discrepancies. Aircraft returned to service."
                ),
                "hobbs_at_service": 23310.0,
                "tach_at_service": 23310.0,
                "next_due_hobbs": "",
                "next_due_date": (n246wn_last_acheck + timedelta(days=550)).strftime("%Y-%m-%d"),
                "mechanic": "Southwest Airlines Line Maintenance — PHX",
                "inspector": "Southwest Airlines IA — K. Osei #SW-IA-0112",
                "ad_reference": "AD 2020-09-07",
                "sb_reference": "",
                "squawk_id": "",
                "resolved_by": "",
                "parts_replaced": "Engine oil (both engines); hydraulic fluid top-off",
                "labor_hours": 24.0,
                "signoff_type": "inspection_approval",
            },
            {
                "date": n246wn_oil_change.strftime("%Y-%m-%d"),
                "component_id": "N246WN-ENGINE-1",
                "maintenance_type": "oil_change",
                "description": (
                    "Engine #1 oil change — routine 120-day service interval. "
                    "Engine oil drained and refilled. Oil filter replaced. No discrepancies."
                ),
                "hobbs_at_service": 23440.0,
                "tach_at_service": 23440.0,
                "next_due_hobbs": "",
                "next_due_tach": 23640.0,
                "next_due_date": (n246wn_oil_change + timedelta(days=122)).strftime("%Y-%m-%d"),
                "mechanic": "Southwest Airlines Line Maintenance — PHX",
                "inspector": "",
                "ad_reference": "",
                "sb_reference": "",
                "squawk_id": "",
                "resolved_by": "",
                "parts_replaced": "Engine oil; oil filter",
                "labor_hours": 2.0,
                "signoff_type": "return_to_service",
            },
            {
                "date": n246wn_borescope1.strftime("%Y-%m-%d"),
                "component_id": "N246WN-ENGINE-1",
                "maintenance_type": "borescope_inspection",
                "description": (
                    "Engine #1 borescope — 500 EFH interval. Fan blade inspection normal. "
                    "EGT deviation measured at +9°C above baseline (elevated from prior check at +4°C). "
                    "HPC/HPT visual inspection — marginal HPT nozzle wear, within limits. "
                    "EGT trend flag raised. ACARS monitoring interval increased."
                ),
                "hobbs_at_service": 23330.0,
                "tach_at_service": 23330.0,
                "next_due_hobbs": "",
                "next_due_date": (n246wn_borescope1 + timedelta(days=90)).strftime("%Y-%m-%d"),
                "mechanic": "Southwest Airlines MRO — K. Osei, A&P #SW-AP-0112",
                "inspector": "",
                "ad_reference": "AD 2020-14-06",
                "sb_reference": "CFM SB 72-0842",
                "squawk_id": "",
                "resolved_by": "",
                "parts_replaced": "",
                "labor_hours": 10.0,
                "signoff_type": "return_to_service",
            },
            {
                "date": n246wn_borescope2.strftime("%Y-%m-%d"),
                "component_id": "N246WN-ENGINE-1",
                "maintenance_type": "borescope_inspection",
                "description": (
                    "On-condition borescope — EGT deviation at +12°C above baseline, ACARS alert triggered. "
                    "HPT nozzle guide vane erosion noted. Fan blade leading edge condition marginal. "
                    "Compressor wash performed. Engine shop visit recommended within 200 EFH."
                ),
                "hobbs_at_service": 23440.0,
                "tach_at_service": 23440.0,
                "next_due_hobbs": 23640.0,
                "next_due_tach": 23640.0,
                "next_due_date": _d(a, 45),
                "mechanic": "Southwest Airlines MRO — K. Osei, A&P #SW-AP-0112",
                "inspector": "Southwest Airlines IA — K. Osei #SW-IA-0112",
                "ad_reference": "AD 2020-14-06; AD 2018-23-09",
                "sb_reference": "CFM SB 72-0842",
                "squawk_id": "",
                "resolved_by": "",
                "parts_replaced": "Engine inlet cleaning chemicals",
                "labor_hours": 16.0,
                "signoff_type": "return_to_service",
            },
        ],
    }

    squawks: dict[str, list[dict[str, Any]]] = {
        "N287WN": [],  # squawks embedded in maint above
        "N246WN": [],
    }

    result = {t: maint.get(t, []) + squawks.get(t, []) for t in INSTRUMENTED_TAILS}

    # N220WN and N235WN are fully instrumented but use placeholder-style maintenance records
    for tail in ("N220WN", "N235WN"):
        if tail not in result or not result[tail]:
            result[tail] = _get_placeholder_maintenance_records(tail, a)

    # Add minimal maintenance records for all placeholder tails
    for tail in PLACEHOLDER_TAILS:
        result[tail] = _get_placeholder_maintenance_records(tail, a)

    return result


def get_all_maintenance(tail: str, *, anchor: datetime | None = None) -> list[dict[str, Any]]:
    """Return maintenance records + squawks for a given tail."""
    by_tail = build_all_maintenance_by_tail(anchor)
    return list(by_tail.get(tail, []))
