import { useEffect, useState, useMemo, useRef, useLayoutEffect, type ReactNode } from "react";
import {
  History,
  ChevronLeft,
  ChevronRight,
  AlertTriangle,
  ChevronDown,
  ArrowDownWideNarrow,
  ArrowUpNarrowWide,
  BarChart2,
} from "lucide-react";
import {
  cn,
  CARD_SURFACE_A,
  CARD_SURFACE_B,
  MAIN_TAB_CONTENT_FRAME,
  TAB_PAGE_TOP_INSET,
  toneClasses,
} from "../lib/utils";
import { MenuSelect } from "./MenuSelect";
import { api } from "../lib/api";
import { useStore, INSTRUMENTED_TAILS, DEFAULT_TAIL } from "../lib/store";
import type { FlightRecord } from "../lib/types";
import {
  telemetrySeverityForField,
  type TelemetrySeverity,
  telemetrySortFieldIsWarn,
  type TelemetrySortField,
} from "../lib/flightThresholds";
import TimeSeriesChart from "./TimeSeriesChart";

const CURRENT_YEAR = new Date().getFullYear();
const YEARS = Array.from({ length: 3 }, (_, i) => CURRENT_YEAR - i);

type SortField =
  | "timestamp"
  | "duration"
  | "route"
  | "egt_deviation"
  | "n1_vibration"
  | "oil_temp_max"
  | "oil_pressure_min"
  | "oil_pressure_max"
  | "fuel_flow_kgh";
type SortDir = "asc" | "desc";

const FLIGHT_ROW_PX = 52;
const FLIGHT_TABLE_HEADER_PX = 44;
/** Reserved for pagination bar above the table (stable layout). */
const FLIGHT_PAGINATION_BAR_PX = 44;
/**
 * Vertical budget for one expanded row's detail panel (flex-wrap tiles + clamped notes).
 * Always subtracted so the list fits when any row is open — no inner/outer scroll.
 * Bump if a viewport clips after layout changes.
 */
const FLIGHT_DETAIL_RESERVE_PX = 288;
const SLOT_GAP_PX = 12;
const FLIGHT_FIT_SAFETY_PX = 10;
const PER_PAGE_MIN = 4;
const PER_PAGE_MAX = 60;

function formatRouteForDisplay(route: string): string {
  const r = (route || "").trim();
  if (!r) return "—";
  const m = /^([A-Za-z0-9]{3,4})-local$/i.exec(r);
  if (m) return m[1].toUpperCase();
  return r;
}

/** API/CSV may send "nan" or empty for missing pilot notes. */
function formatPilotNotes(raw: string | undefined | null): string {
  const s = (raw ?? "").trim();
  if (!s) return "—";
  if (/^nan$/i.test(s)) return "—";
  return s;
}

/** Coerce API values (number, string, missing) for tach and other optional numerics. */
function toFiniteNumber(v: unknown): number | null {
  if (v === null || v === undefined) return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "string") {
    const t = v.trim();
    if (t === "" || /^nan$/i.test(t)) return null;
    const n = Number(t);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function normalizeFlightRecord(r: FlightRecord): FlightRecord {
  const raw = r as FlightRecord & {
    tach_start?: unknown;
    tach_end?: unknown;
    oil_pressure_min?: unknown;
    oil_pressure_max?: unknown;
  };
  let oilMin = toFiniteNumber(raw.oil_pressure_min);
  let oilMax = toFiniteNumber(raw.oil_pressure_max);
  if (oilMin !== null && oilMax !== null && oilMin > oilMax) {
    const t = oilMin;
    oilMin = oilMax;
    oilMax = t;
  }
  return {
    ...r,
    tach_start: toFiniteNumber(raw.tach_start),
    tach_end: toFiniteNumber(raw.tach_end),
    oil_pressure_min: oilMin,
    oil_pressure_max: oilMax,
  };
}

/** Chevron | Date | Duration | fixed peek slot | Route — peek column width reserved always so sort mode does not shift columns */
const FLIGHT_ROW_GRID_STYLE = {
  gridTemplateColumns: "auto minmax(0, 1fr) minmax(0, 1.35fr) 7.25rem minmax(0, 1fr)",
} as const;

function showsSortPeek(sf: SortField): sf is TelemetrySortField {
  return sf !== "timestamp" && sf !== "duration" && sf !== "route";
}

const SORT_PEEK_HEADER: Record<TelemetrySortField, string> = {
  egt_deviation: "EGT dev",
  n1_vibration: "N1 vib",
  oil_temp_max: "Oil °C",
  oil_pressure_min: "Oil psi min",
  oil_pressure_max: "Oil psi max",
  fuel_flow_kgh: "Fuel kg/h",
};

function formatSortPeekValue(rec: FlightRecord, field: TelemetrySortField): string {
  switch (field) {
    case "egt_deviation":
      return rec.egt_deviation !== null ? `+${rec.egt_deviation.toFixed(1)} °C` : "—";
    case "n1_vibration":
      return rec.n1_vibration !== null ? `${rec.n1_vibration.toFixed(2)} u` : "—";
    case "oil_temp_max":
      return rec.oil_temp_max !== null ? `${rec.oil_temp_max.toFixed(0)} °C` : "—";
    case "oil_pressure_min":
      return rec.oil_pressure_min !== null ? `${rec.oil_pressure_min.toFixed(1)} psi` : "—";
    case "oil_pressure_max":
      return rec.oil_pressure_max !== null ? `${rec.oil_pressure_max.toFixed(1)} psi` : "—";
    case "fuel_flow_kgh":
      return rec.fuel_flow_kgh !== null ? `${rec.fuel_flow_kgh.toFixed(0)} kg/h` : "—";
    default:
      return "—";
  }
}

function computeFlightsPerPage(slotHeightPx: number): number {
  if (slotHeightPx <= 0) return PER_PAGE_MIN;
  const listBudget =
    slotHeightPx -
    FLIGHT_PAGINATION_BAR_PX -
    FLIGHT_TABLE_HEADER_PX -
    SLOT_GAP_PX -
    FLIGHT_FIT_SAFETY_PX -
    FLIGHT_DETAIL_RESERVE_PX;
  const rows = Math.floor(Math.max(0, listBudget) / FLIGHT_ROW_PX);
  return Math.max(PER_PAGE_MIN, Math.min(PER_PAGE_MAX, rows));
}

interface Props {
  active: boolean;
}

function DetailMetric({
  label,
  children,
  severity,
}: {
  label: string;
  children: ReactNode;
  severity?: TelemetrySeverity;
}) {
  const sev: TelemetrySeverity = severity ?? "ok";
  const sevTone = sev === "bad" ? toneClasses("bad") : sev === "warn" ? toneClasses("warn") : null;
  const sevText = sevTone ? sevTone.text : "text-slate-800";
  // Flight telemetry cells are the ONE place in the app that keeps tinted
  // warning fills (bg-red-50 / bg-orange-50) — pilots need at-a-glance
  // identification of out-of-spec readings in a dense data table.
  const sevPanel =
    sev === "bad"
      ? "border border-red-200 bg-red-50"
      : sev === "warn"
      ? "border border-orange-200 bg-orange-50"
      : CARD_SURFACE_B;
  return (
    <div className={cn("rounded-md px-2 py-1.5 min-w-0 max-w-full", sevPanel)}>
      <div className="text-[10px] font-medium uppercase tracking-wide text-slate-400">{label}</div>
      <div className={cn("font-mono text-xs tabular-nums mt-0.5", sevText)}>
        {children}
      </div>
    </div>
  );
}

function FlightDetailPanel({ rec }: { rec: FlightRecord }) {
  const routeLabel = formatRouteForDisplay(rec.route);
  const rawRoute = (rec.route || "").trim();
  const notesDisplay = formatPilotNotes(rec.pilot_notes);

  return (
    <div className={cn("px-3 sm:px-4 py-3 pl-9 sm:pl-11 text-sm min-w-0 max-w-full overflow-hidden", CARD_SURFACE_A)}>
      <div className="text-slate-400 text-[10px] font-semibold uppercase tracking-widest mb-2">Flight details</div>
      <div className="flex flex-wrap gap-2 mb-3 min-w-0">
        <div className={cn("rounded-md px-2.5 py-1.5 min-w-[6rem] max-w-full", CARD_SURFACE_B)}>
          <div className="text-[10px] font-medium uppercase tracking-wide text-slate-400">Route</div>
          <div className="text-xs text-slate-800 mt-0.5">{routeLabel || rawRoute || "—"}</div>
        </div>
        <div className={cn("rounded-md px-2.5 py-1.5", CARD_SURFACE_B)}>
          <div className="text-[10px] font-medium uppercase tracking-wide text-slate-400">Duration</div>
          <div className="font-mono text-xs text-slate-800 tabular-nums mt-0.5">{rec.duration.toFixed(1)} hr</div>
        </div>
        <div className={cn("rounded-md px-2.5 py-1.5", CARD_SURFACE_B)}>
          <div className="text-[10px] font-medium uppercase tracking-wide text-slate-400">AFH</div>
          <div className="font-mono text-xs text-slate-800 tabular-nums mt-0.5">
            {rec.hobbs_start.toFixed(1)} → {rec.hobbs_end.toFixed(1)} hr
          </div>
        </div>
        <DetailMetric label="Fuel flow" severity="ok">
          {rec.fuel_flow_kgh !== null ? `${rec.fuel_flow_kgh.toFixed(0)} kg/hr` : "—"}
        </DetailMetric>
      </div>
      <div className="flex flex-wrap gap-2 border-t border-slate-200/40 pt-2 min-w-0">
        <DetailMetric label="EGT deviation" severity={telemetrySeverityForField("egt_deviation", rec)}>
          {rec.egt_deviation !== null ? `+${rec.egt_deviation.toFixed(1)} °C` : "—"}
        </DetailMetric>
        <DetailMetric label="N1 vibration" severity={telemetrySeverityForField("n1_vibration", rec)}>
          {rec.n1_vibration !== null ? `${rec.n1_vibration.toFixed(2)} units` : "—"}
        </DetailMetric>
        <DetailMetric label="Oil temp" severity={telemetrySeverityForField("oil_temp_max", rec)}>
          {rec.oil_temp_max !== null ? `${rec.oil_temp_max.toFixed(0)} °C` : "—"}
        </DetailMetric>
        <DetailMetric label="Oil psi min" severity={telemetrySeverityForField("oil_pressure_min", rec)}>
          {rec.oil_pressure_min !== null ? `${rec.oil_pressure_min.toFixed(1)} psi` : "—"}
        </DetailMetric>
        <DetailMetric label="Oil psi max" severity={telemetrySeverityForField("oil_pressure_max", rec)}>
          {rec.oil_pressure_max !== null ? `${rec.oil_pressure_max.toFixed(1)} psi` : "—"}
        </DetailMetric>
      </div>
      <div className="mt-2 pt-2 border-t border-slate-200/40 min-w-0">
        <div className="text-[10px] font-medium uppercase tracking-wide text-slate-400">Pilot notes</div>
        <p
          className="text-slate-500 text-xs mt-0.5 leading-snug line-clamp-2 break-words"
          title={notesDisplay !== "—" ? notesDisplay : undefined}
        >
          {notesDisplay}
        </p>
      </div>
    </div>
  );
}

const SORT_OPTIONS: { value: SortField; label: string }[] = [
  { value: "timestamp", label: "Date" },
  { value: "duration", label: "Duration" },
  { value: "route", label: "Route" },
  { value: "egt_deviation", label: "EGT deviation" },
  { value: "n1_vibration", label: "N1 vibration" },
  { value: "oil_temp_max", label: "Oil temp" },
  { value: "oil_pressure_min", label: "Oil pressure min" },
  { value: "oil_pressure_max", label: "Oil pressure max" },
  { value: "fuel_flow_kgh", label: "Fuel flow" },
];

function directionAriaLabel(field: SortField, dir: SortDir): string {
  if (field === "timestamp") {
    return dir === "desc" ? "Sort: newest first" : "Sort: oldest first";
  }
  if (field === "route") {
    return dir === "desc" ? "Sort: Z to A" : "Sort: A to Z";
  }
  return dir === "desc" ? "Sort: high to low" : "Sort: low to high";
}

export default function FlightHistory({ active }: Props) {
  const { selectedAircraft, setSelectedAircraft } = useStore();
  const tail = (INSTRUMENTED_TAILS as unknown as string[]).includes(selectedAircraft ?? "")
    ? (selectedAircraft ?? DEFAULT_TAIL)
    : DEFAULT_TAIL;
  const [showChart, setShowChart] = useState(false);
  const [records, setRecords] = useState<FlightRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [page, setPage] = useState(1);
  const [yearFilter, setYearFilter] = useState<number | undefined>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sortField, setSortField] = useState<SortField>("timestamp");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const tableSlotRef = useRef<HTMLDivElement>(null);
  const [perPage, setPerPage] = useState(PER_PAGE_MIN);
  const [measureReady, setMeasureReady] = useState(false);
  const prevPerPageRef = useRef(perPage);

  useLayoutEffect(() => {
    if (!active) {
      setMeasureReady(false);
      return;
    }
    const root = tableSlotRef.current;
    const apply = () => {
      const el = tableSlotRef.current;
      if (!el) return;
      const h = el.clientHeight;
      if (h > 0) {
        setPerPage(computeFlightsPerPage(h));
        setMeasureReady(true);
      }
    };
    apply();
    if (!root) return;
    const ro = new ResizeObserver(apply);
    ro.observe(root);
    return () => ro.disconnect();
  }, [active]);

  useEffect(() => {
    if (prevPerPageRef.current !== perPage) {
      prevPerPageRef.current = perPage;
      setPage(1);
    }
  }, [perPage]);

  useEffect(() => {
    setPage(1);
  }, [tail]);

  useEffect(() => {
    setPage(1);
  }, [sortField, sortDir]);

  /** First row expanded whenever the current page's list loads or changes. */
  useEffect(() => {
    setExpandedIdx(records.length > 0 ? 0 : null);
  }, [records]);

  useEffect(() => {
    if (!active || !measureReady) return;
    setLoading(true);
    setError(null);
    api
      .flights(tail, {
        page,
        per_page: perPage,
        year: yearFilter,
        sort: sortField,
        order: sortDir,
      })
      .then((res) => {
        setRecords(res.records.map(normalizeFlightRecord));
        setTotal(res.total);
        setTotalPages(res.total_pages);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [active, measureReady, tail, page, yearFilter, perPage, sortField, sortDir]);

  const { showingStart, showingEnd } = useMemo(() => {
    if (total === 0 || records.length === 0) {
      return { showingStart: 0, showingEnd: 0 };
    }
    const start = (page - 1) * perPage + 1;
    const end = start + records.length - 1;
    return { showingStart: start, showingEnd: end };
  }, [total, page, perPage, records.length]);

  const handleYearChange = (v: string) => {
    setPage(1);
    setYearFilter(v ? Number(v) : undefined);
  };

  const handleSortFieldChange = (field: SortField) => {
    setSortField(field);
    if (field === "timestamp" || field === "route") {
      setSortDir(field === "timestamp" ? "desc" : "asc");
    } else {
      setSortDir("desc");
    }
  };

  const skeletonRows = measureReady ? perPage : PER_PAGE_MIN;
  const peekField: TelemetrySortField | null = showsSortPeek(sortField) ? sortField : null;
  const peekHeaderLabel =
    peekField !== null ? SORT_PEEK_HEADER[peekField] : "\u00a0";
  const tableHeaderLabels = ["Date", "Duration", peekHeaderLabel, "Route"] as const;

  const yearOptions: { value: string; label: string }[] = [
    { value: "", label: "All years" },
    ...YEARS.map((y) => ({ value: String(y), label: String(y) })),
  ];
  const yearValue = yearFilter !== undefined ? String(yearFilter) : "";

  const paginationInner = (() => {
    if (!measureReady) {
      return <span className="text-slate-400">…</span>;
    }
    if (error) return null;
    if (loading && total === 0) {
      return <span className="text-slate-400">Loading…</span>;
    }
    if (total === 0) return null;
    return (
      <>
        <p className="min-w-0">
          Showing{" "}
          <span className="text-slate-700 tabular-nums font-medium">
            {showingStart}–{showingEnd}
          </span>{" "}
          of <span className="text-slate-500 tabular-nums">{total}</span>
          {totalPages > 1 && (
            <span className="text-slate-400 ml-2 whitespace-nowrap">
              · Page {page} of {totalPages}
            </span>
          )}
        </p>
        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="p-1.5 rounded-lg border border-slate-200 text-slate-500 hover:text-slate-800
              hover:border-slate-300 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            aria-label="Previous page"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="p-1.5 rounded-lg border border-slate-200 text-slate-500 hover:text-slate-800
              hover:border-slate-300 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
            aria-label="Next page"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </>
    );
  })();

  return (
    <>
    <div className="flex flex-1 min-h-0 flex-col overflow-hidden w-full">
      <div className={cn("flex flex-1 min-h-0 flex-col min-w-0 pb-6", MAIN_TAB_CONTENT_FRAME, TAB_PAGE_TOP_INSET)}>
      <div className="shrink-0 flex flex-col gap-2 mb-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex gap-1 flex-wrap">
            {(INSTRUMENTED_TAILS as unknown as string[]).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setSelectedAircraft(t as ReturnType<typeof useStore.getState>["selectedAircraft"])}
                className={cn(
                  "px-2.5 py-0.5 rounded-full text-xs font-medium border transition-colors",
                  tail === t
                    ? "bg-[#304cb2] text-white border-[#304cb2]"
                    : "bg-slate-100 text-slate-500 border-slate-200 hover:border-slate-400"
                )}
              >
                {t}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => setShowChart((s) => !s)}
            className={cn(
              "flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border transition-colors shrink-0",
              showChart
                ? "bg-[#304cb2] text-white border-[#304cb2]"
                : "bg-slate-100 text-slate-500 border-slate-200 hover:border-slate-400"
            )}
          >
            <BarChart2 className="w-3.5 h-3.5" />
            Visualize
          </button>
        </div>

        <div className="flex items-center justify-between gap-4 flex-wrap">
          <h2 className="text-xs font-semibold text-slate-400 uppercase tracking-widest flex items-center gap-2">
            <History className="w-3.5 h-3.5" />
            {total > 0 && (
              <span>
                {total} recent flights
              </span>
            )}
          </h2>

          <div className="flex items-center gap-2 flex-wrap">
            <span className="hidden sm:inline text-xs text-slate-400 shrink-0">Sort by</span>
            <MenuSelect<SortField>
              ariaLabel="Sort flights by"
              value={sortField}
              options={SORT_OPTIONS}
              onChange={handleSortFieldChange}
            />
            <button
              type="button"
              onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
              className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-slate-100 text-slate-700 hover:border-slate-300 hover:bg-slate-100/90 focus:outline-none focus:border-[#304cb2]"
              aria-label={directionAriaLabel(sortField, sortDir)}
              title={directionAriaLabel(sortField, sortDir)}
            >
              {sortDir === "desc" ? (
                <ArrowDownWideNarrow className="h-4 w-4" aria-hidden />
              ) : (
                <ArrowUpNarrowWide className="h-4 w-4" aria-hidden />
              )}
            </button>
            <MenuSelect<string>
              ariaLabel="Filter by year"
              value={yearValue}
              options={yearOptions}
              onChange={handleYearChange}
            />
          </div>
        </div>
      </div>

      <div
        ref={tableSlotRef}
        className="flex-1 min-h-0 min-w-0 flex flex-col gap-3 overflow-hidden"
      >
        <div
          className={cn(
            "flex shrink-0 min-h-[44px] items-center gap-4 text-xs text-slate-400",
            (measureReady && total > 0 && !error) || (measureReady && loading && !error) ? "justify-between" : ""
          )}
        >
          {paginationInner}
        </div>

        {loading && (
          <div
            className={cn("shrink-0 flex flex-col rounded-xl overflow-hidden min-w-0", CARD_SURFACE_B)}
            aria-busy="true"
          >
            <div className="min-w-0">
              <div className="min-w-0 flex flex-col">
                <div
                  className="grid gap-x-2 sm:gap-x-3 gap-y-2 px-3 sm:px-4 py-2.5 border-b border-slate-200 shrink-0 items-end"
                  style={FLIGHT_ROW_GRID_STYLE}
                >
                  <span className="w-7" aria-hidden />
                  {tableHeaderLabels.map((label, hi) => (
                    <span
                      key={`${label}-${hi}`}
                      className={cn(
                        "text-[11px] font-semibold uppercase tracking-wider text-slate-400 whitespace-nowrap min-w-0 truncate",
                        hi === 2 && peekField === null && "select-none"
                      )}
                      aria-hidden={hi === 2 && peekField === null ? true : undefined}
                    >
                      {label}
                    </span>
                  ))}
                </div>
                <div className="flex flex-col divide-y divide-slate-200 min-w-0">
                  {Array.from({ length: skeletonRows }).map((_, i) => (
                    <div
                      key={i}
                      className="grid gap-x-2 sm:gap-x-3 gap-y-2 px-3 sm:px-4 py-3 items-center animate-pulse shrink-0 min-h-[52px] box-border min-w-0"
                      style={FLIGHT_ROW_GRID_STYLE}
                    >
                      <div className="h-4 w-4 bg-slate-100 rounded shrink-0" />
                      <div className="h-4 bg-slate-100 rounded w-24" />
                      <div className="h-4 bg-slate-100 rounded w-full max-w-[14rem]" />
                      <div className="h-4 bg-slate-100 rounded w-full min-w-0 max-w-[6.5rem]" />
                      <div className="h-4 bg-slate-100 rounded w-full min-w-0" />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {error && (
          <div
            className={cn(
              "flex items-center gap-3 p-4 rounded-xl shrink-0",
              toneClasses("bad").bannerPanel
            )}
          >
            <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
            <p className="text-sm text-red-300">{error}</p>
          </div>
        )}

        {!loading && !error && records.length === 0 && measureReady && (
          <div className="flex flex-1 flex-col items-center justify-center min-h-0 text-slate-400">
            <History className="w-10 h-10 mb-3" />
            <p className="text-sm">No flight records found</p>
            <p className="text-xs mt-1">Run ingestion to populate flight data</p>
          </div>
        )}

        {!loading && !error && records.length > 0 && (
          <div className={cn("shrink-0 flex flex-col rounded-xl overflow-hidden min-w-0 max-w-full", CARD_SURFACE_B)}>
            <div className="min-w-0 max-w-full">
              <div className="min-w-0 flex flex-col">
                <div
                  className="grid gap-x-2 sm:gap-x-3 gap-y-2 px-3 sm:px-4 py-2.5 border-b border-slate-200 shrink-0 items-end"
                  style={FLIGHT_ROW_GRID_STYLE}
                >
                  <span className="w-7" aria-hidden />
                  {tableHeaderLabels.map((label, hi) => (
                    <span
                      key={`${label}-${hi}`}
                      className={cn(
                        "text-[11px] font-semibold uppercase tracking-wider text-slate-400 whitespace-nowrap min-w-0 truncate",
                        hi === 2 && peekField === null && "select-none"
                      )}
                      aria-hidden={hi === 2 && peekField === null ? true : undefined}
                    >
                      {label}
                    </span>
                  ))}
                </div>

                <div className="divide-y divide-slate-200">
                  {records.map((rec, idx) => {
                    const date = new Date(rec.timestamp).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                      year: "numeric",
                    });
                    const durationTitle = `${rec.duration.toFixed(1)} hr · Hobbs ${rec.hobbs_start.toFixed(1)}→${rec.hobbs_end.toFixed(1)}`;
                    const routeDisplay = formatRouteForDisplay(rec.route);
                    const open = expandedIdx === idx;
                    const peekWarn =
                      peekField !== null && telemetrySortFieldIsWarn(peekField, rec);

                    return (
                      <div key={`${rec.timestamp}-${idx}`}>
                        <button
                          type="button"
                          onClick={() => setExpandedIdx((e) => (e === idx ? null : idx))}
                          className={cn(
                            "w-full min-w-0 grid gap-x-2 sm:gap-x-3 gap-y-1 px-3 sm:px-4 py-3 text-sm items-center shrink-0 min-h-[52px] box-border text-left",
                            "hover:bg-slate-100 transition-colors",
                            open && "bg-slate-100/50"
                          )}
                          style={FLIGHT_ROW_GRID_STYLE}
                        >
                          <ChevronDown
                            className={cn(
                              "w-4 h-4 text-slate-400 shrink-0 transition-transform",
                              open && "rotate-180"
                            )}
                            aria-hidden
                          />
                          <span className="text-slate-800 tabular-nums text-sm min-w-0 truncate">{date}</span>
                          <span
                            className="tabular-nums text-left min-w-0"
                            title={durationTitle}
                          >
                            <span className="text-slate-800 text-sm font-medium whitespace-nowrap">
                              {rec.duration.toFixed(1)} hr
                            </span>
                            <span className="text-slate-400 text-[11px] sm:text-xs font-mono block sm:inline sm:ml-1 truncate">
                              <span className="hidden sm:inline"> · </span>
                              {rec.hobbs_start.toFixed(1)}→{rec.hobbs_end.toFixed(1)}
                            </span>
                          </span>
                          <span
                            className={cn(
                              "font-mono text-[11px] sm:text-xs tabular-nums text-left min-w-0 truncate block w-full",
                              peekField !== null
                                ? peekWarn
                                  ? "text-yellow-400"
                                  : "text-slate-700"
                                : "text-transparent pointer-events-none select-none"
                            )}
                            aria-hidden={peekField === null}
                            title={peekField !== null ? formatSortPeekValue(rec, peekField) : undefined}
                          >
                            {peekField !== null
                              ? formatSortPeekValue(rec, peekField)
                              : "0000 F"}
                          </span>
                          <span className="text-slate-500 text-sm truncate min-w-0 text-left font-medium" title={routeDisplay}>
                            {routeDisplay}
                          </span>
                        </button>
                        {open ? <FlightDetailPanel rec={rec} /> : null}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
      </div>
    </div>

    {showChart && (
      <div
        className="fixed bottom-0 left-0 right-0 z-40 bg-white border-t border-slate-200 shadow-xl rounded-t-2xl"
        style={{ maxHeight: "55vh" }}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200">
          <span className="text-sm font-semibold text-slate-800">Time Series Data Visualization</span>
          <button
            onClick={() => setShowChart(false)}
            className="w-7 h-7 flex items-center justify-center rounded-full text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors text-lg leading-none"
            aria-label="Close chart"
          >
            ✕
          </button>
        </div>
        <div className="overflow-y-auto" style={{ maxHeight: "calc(55vh - 52px)" }}>
          <TimeSeriesChart />
        </div>
      </div>
    )}
    </>
  );
}
