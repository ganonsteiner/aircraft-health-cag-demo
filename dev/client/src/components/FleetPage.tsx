import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle, Info, XCircle, Plane, ArrowRight } from "lucide-react";
import { api } from "../lib/api";
import { useStore, TAILS, type TailNumber } from "../lib/store";
import type { FleetAircraft } from "../lib/types";
import {
  cn,
  CARD_SURFACE_A,
  CARD_SURFACE_B,
  CARD_SURFACE_C,
  TAB_PAGE_TOP_INSET,
  toneClasses,
  toneForAirworthiness,
} from "../lib/utils";

type Tab = "fleet" | "dashboard" | "query" | "maintenance" | "flights" | "aircraft" | "graph";

/** Mirrors StatusDashboard assistant footer inset: `left-2 bottom-2` there → `right-2 bottom-2` here (do not change Status). */
const FLEET_CARD_STATUS_FOOTER_ROW =
  "pointer-events-none absolute right-2 bottom-2 z-10 inline-flex shrink-0 items-center gap-0.5 text-sm leading-none text-slate-400 transition-colors group-hover/card:text-[#304cb2]";

interface FleetPageProps {
  onNavigate: (tab: Tab, tail: TailNumber) => void;
}

const AIRWORTHINESS_CONFIG = {
  AIRWORTHY: {
    label: "AIRWORTHY",
    icon: CheckCircle,
    dot: "bg-emerald-400",
    badge: toneClasses("ok").badge,
    card: "border-slate-200",
  },
  FERRY_ONLY: {
    label: "FERRY ONLY",
    icon: Info,
    dot: "bg-orange-400",
    badge: toneClasses("warn").badge,
    card: "border-slate-200",
  },
  CAUTION: {
    label: "CAUTION",
    icon: AlertTriangle,
    dot: "bg-orange-400",
    badge: toneClasses("warn").badge,
    card: "border-slate-200",
  },
  NOT_AIRWORTHY: {
    label: "NOT AIRWORTHY",
    icon: XCircle,
    dot: "bg-red-500",
    badge: toneClasses("bad").badge,
    card: "border-slate-200",
  },
  UNKNOWN: {
    label: "UNKNOWN",
    icon: Info,
    dot: "bg-slate-400",
    badge: toneClasses("unknown").badge,
    card: "border-slate-200",
  },
};

const STATUS_ORDER: Record<string, number> = {
  NOT_AIRWORTHY: 0,
  CAUTION: 1,
  FERRY_ONLY: 2,
  AIRWORTHY: 3,
  UNKNOWN: 4,
};


function SmohBar({
  smoh,
  tbo,
  pct,
  failed,
}: {
  smoh: number;
  tbo: number;
  pct: number;
  failed?: boolean;
}) {
  if (failed) {
    return (
      <div className="flex items-center gap-2">
        <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
          <div className="h-full w-full bg-red-500 rounded-full" />
        </div>
        <span className="text-[11px] font-semibold text-red-600 shrink-0">FAILED</span>
      </div>
    );
  }
  const hasData = smoh > 0;
  const barColor = pct > 80 ? "bg-red-500" : pct > 60 ? "bg-orange-500" : "bg-emerald-500";
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        {hasData && (
          <div
            className={cn("h-full rounded-full transition-all", barColor)}
            style={{ width: `${Math.min(100, pct)}%` }}
          />
        )}
      </div>
      <span className="text-[11px] tabular-nums text-slate-500 shrink-0 w-24 text-right">
        {hasData ? `${Math.round(smoh).toLocaleString()} / ${(tbo || 30000).toLocaleString()} h` : "—"}
      </span>
    </div>
  );
}

function AircraftCard({
  aircraft,
  onSelect,
}: {
  aircraft: FleetAircraft;
  onSelect: () => void;
}) {
  const cfg = AIRWORTHINESS_CONFIG[aircraft.airworthiness] ?? AIRWORTHINESS_CONFIG.UNKNOWN;
  const awTone = toneForAirworthiness(aircraft.airworthiness);
  const smoh = Number(aircraft.smoh) || 0;
  const smohPct = Math.min(100, Number(aircraft.smohPercent) || 0);
  const smoh2 = Number(aircraft.engine2SMOH) || 0;
  const smoh2Pct = Math.min(100, Number(aircraft.engine2SMOHPercent) || 0);
  const tbo = aircraft.tbo || 30000;
  const eng1Failed = aircraft.airworthiness === "NOT_AIRWORTHY";
  const loadErr = aircraft.metadata?.load_error;
  const aircraftType = aircraft.metadata?.aircraft_type || "Boeing 737";

  const oilLabel = (() => {
    if (aircraft.oilDaysUntilDue === null || aircraft.oilDaysUntilDue === undefined) return "—";
    if (aircraft.oilDaysUntilDue < 0) return `${Math.abs(aircraft.oilDaysUntilDue)} d overdue`;
    return `${aircraft.oilDaysUntilDue} d`;
  })();
  const oilOverdue = typeof aircraft.oilDaysUntilDue === "number" && aircraft.oilDaysUntilDue < 0;

  const annualLabel = (() => {
    if (!aircraft.annualDueDate) return "—";
    const days = aircraft.annualDaysRemaining;
    if (days === null || days === undefined) return aircraft.annualDueDate;
    const dayStr = days < 0 ? `${Math.abs(days)} d over` : `${days} d`;
    return `${aircraft.annualDueDate} (${dayStr})`;
  })();
  const annualDays = aircraft.annualDaysRemaining;
  const annualOverdue = typeof annualDays === "number" && annualDays < 0;

  return (
    <button
      onClick={onSelect}
      className={cn(
        "relative text-left rounded-xl p-4 sm:p-5 pb-9 transition-all hover:bg-muted group/card",
        CARD_SURFACE_B,
        "flex flex-col w-full min-w-0 overflow-hidden",
        cfg.card
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2 mb-3 shrink-0 min-w-0">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="p-2 rounded-lg border shrink-0 bg-[#304cb2]/10 border-[#304cb2]/20">
            <Plane className="w-4 h-4 text-[#304cb2]" />
          </div>
          <div className="min-w-0">
            <div className="font-bold text-sm text-slate-900">{aircraft.tail}</div>
            <div className="text-xs text-slate-500 mt-0.5">{aircraftType}</div>
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <span
            className={cn(
              "inline-flex items-center gap-1 whitespace-nowrap px-2 py-0.5 rounded-full text-xs font-semibold border",
              awTone.badge
            )}
          >
            <span className={cn("w-1.5 h-1.5 shrink-0 rounded-full", awTone.dot)} />
            {cfg.label}
          </span>
        </div>
      </div>

      {/* Engine SMOH bars */}
      <div className="mb-3 shrink-0 space-y-2">
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-[11px] text-slate-400">Eng #1 — CFM56-7B</span>
            {!eng1Failed && smoh > 0 && (
              <span className="text-[11px] text-slate-400 tabular-nums">{smohPct.toFixed(0)}%</span>
            )}
          </div>
          <SmohBar smoh={smoh} tbo={tbo} pct={smohPct} failed={eng1Failed} />
        </div>
        {smoh2 > 0 && (
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-[11px] text-slate-400">Eng #2 — CFM56-7B</span>
              <span className="text-[11px] text-slate-400 tabular-nums">{smoh2Pct.toFixed(0)}%</span>
            </div>
            <SmohBar smoh={smoh2} tbo={tbo} pct={smoh2Pct} />
          </div>
        )}
      </div>

      {/* Oil / Annual grid */}
      <div className="grid grid-cols-2 gap-2 shrink-0 mb-2">
        <div className={cn("rounded-lg px-2.5 py-2", CARD_SURFACE_C)}>
          <div className="text-[10px] font-medium text-slate-500 mb-0.5">Oil Due</div>
          <div className={cn("text-xs font-medium", oilOverdue ? "text-red-600" : "text-slate-700")}>
            {oilLabel}
          </div>
        </div>
        <div className={cn("rounded-lg px-2.5 py-2", CARD_SURFACE_C)}>
          <div className="text-[10px] font-medium text-slate-500 mb-0.5">Annual Due</div>
          <div className={cn("text-xs font-medium", annualOverdue ? "text-red-600" : "text-slate-700")}>
            {annualLabel}
          </div>
        </div>
      </div>

      <div className="text-[11px] text-slate-400 mt-0.5 mb-1">
        Last maintenance: {aircraft.lastMaintenanceDate || "—"}
      </div>

      {loadErr && (
        <div className={cn("text-xs text-red-400/90 rounded-lg px-2 py-1.5 border-l-[3px] border-l-red-500/60 mt-1", CARD_SURFACE_C)}>
          Could not load status: {loadErr}
        </div>
      )}

      <div className={FLEET_CARD_STATUS_FOOTER_ROW}>
        <span className="whitespace-nowrap">View status</span>
        <ArrowRight className="w-3 h-3 shrink-0" aria-hidden />
      </div>
    </button>
  );
}

export default function FleetPage({ onNavigate }: FleetPageProps) {
  const [fleet, setFleet] = useState<FleetAircraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { setSelectedAircraft } = useStore();

  useEffect(() => {
    setLoading(true);
    api.fleet()
      .then(setFleet)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const handleSelect = (tail: TailNumber) => {
    setSelectedAircraft(tail);
    onNavigate("dashboard", tail);
  };

  const sortedFleet = [...fleet].sort((a, b) => {
    const statusDiff =
      (STATUS_ORDER[a.airworthiness] ?? 99) - (STATUS_ORDER[b.airworthiness] ?? 99);
    if (statusDiff !== 0) return statusDiff;
    // Within same status group: sort by whichever maintenance is sooner (oil or annual)
    const soonerA = Math.min(a.oilDaysUntilDue ?? 9999, a.annualDaysRemaining ?? 9999);
    const soonerB = Math.min(b.oilDaysUntilDue ?? 9999, b.annualDaysRemaining ?? 9999);
    return soonerA - soonerB;
  });

  const airworthyCounts = {
    AIRWORTHY: fleet.filter((a) => a.airworthiness === "AIRWORTHY").length,
    CAUTION: fleet.filter((a) => a.airworthiness === "CAUTION").length,
    NOT_AIRWORTHY: fleet.filter((a) => a.airworthiness === "NOT_AIRWORTHY").length,
  };

  return (
    <div className="flex flex-1 flex-col min-h-0 min-w-0 w-full overflow-y-auto">
      <div
        className={cn(
          "flex flex-col max-w-6xl mx-auto w-full min-w-0 px-4 sm:px-6 pb-4",
          TAB_PAGE_TOP_INSET
        )}
      >
        {/* Fleet header stats */}
        {!loading && fleet.length > 0 && (
          <div className="grid grid-cols-3 gap-2 sm:gap-3 mb-3 shrink-0">
            {[
              { label: "Airworthy", count: airworthyCounts.AIRWORTHY, color: "text-emerald-500" },
              { label: "Caution", count: airworthyCounts.CAUTION, color: "text-orange-500" },
              { label: "Grounded", count: airworthyCounts.NOT_AIRWORTHY, color: "text-red-500" },
            ].map((s) => (
              <div key={s.label} className={cn("rounded-xl p-3 sm:p-4 text-center", CARD_SURFACE_B)}>
                <div className={cn("text-2xl font-bold", s.color)}>{s.count}</div>
                <div className="text-xs text-slate-400 mt-1">{s.label}</div>
              </div>
            ))}
          </div>
        )}

        {loading && (
          <div className="flex flex-col min-w-0">
            <div className="grid grid-cols-3 gap-2 sm:gap-3 mb-3 shrink-0 animate-pulse" aria-busy="true">
              {Array.from({ length: 3 }).map((_, i) => (
                <div
                  key={i}
                  className={cn("rounded-xl p-4 h-[5.25rem]", CARD_SURFACE_B)}
                >
                  <div className="h-8 bg-slate-100 rounded mx-auto w-10 mb-2" />
                  <div className="h-3 bg-slate-100 rounded mx-auto w-20" />
                </div>
              ))}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4 w-full">
              {TAILS.map((t) => (
                <div
                  key={t}
                  className={cn(
                    "min-h-[10rem] rounded-xl p-5 sm:p-6 flex flex-col animate-pulse",
                    CARD_SURFACE_A
                  )}
                >
                  <div className="flex justify-between gap-3 mb-4">
                    <div className="flex gap-3 min-w-0">
                      <div className="w-10 h-10 rounded-lg bg-slate-100 shrink-0" />
                      <div className="space-y-2 min-w-0 pt-0.5">
                        <div className="h-5 bg-slate-100 rounded w-24" />
                        <div className="h-3 bg-slate-100 rounded w-36 max-w-full" />
                      </div>
                    </div>
                    <div className="h-7 w-28 rounded-full bg-slate-100 shrink-0" />
                  </div>
                  <div className="h-2 bg-slate-100 rounded-full mb-4" />
                  <div className="grid grid-cols-2 gap-3 flex-1 content-start">
                    {Array.from({ length: 6 }).map((_, j) => (
                      <div key={j} className={cn("min-h-[4.25rem] rounded-lg", CARD_SURFACE_C)} />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div
            className={cn(
              "shrink-0 rounded-xl p-4 text-red-400 text-sm mb-2",
              toneClasses("bad").bannerPanel
            )}
          >
            Failed to load fleet data: {error}
          </div>
        )}

        {/* Aircraft cards — sorted by status then next due maintenance */}
        {!loading && !error && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4 w-full">
            {sortedFleet.map((aircraft) => (
                <AircraftCard
                  key={aircraft.tail}
                  aircraft={aircraft}
                  onSelect={() => handleSelect(aircraft.tail as TailNumber)}
                />
              ))}
          </div>
        )}
      </div>
    </div>
  );
}
