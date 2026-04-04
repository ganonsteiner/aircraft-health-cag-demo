import { useEffect, useState } from "react";
import {
  Clock,
  Gauge,
  Calendar,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Wrench,
  Info,
} from "lucide-react";
import { cn, formatDate, severityColor } from "../lib/utils";
import { api } from "../lib/api";
import { useStore } from "../lib/store";
import type { AircraftStatus, Squawk } from "../lib/types";

type AirworthinessState = "AIRWORTHY" | "CAUTION" | "NOT AIRWORTHY";

function deriveAirworthiness(status: AircraftStatus, squawks: Squawk[]): AirworthinessState {
  const hasGroundingSquawk = squawks.some(
    (s) => s.severity === "grounding" && s.status === "open"
  );
  const hoursOverdue = status.oilHoursOverdue ?? 0;
  const annualDaysRemaining = status.annualDaysRemaining ?? 999;

  if (hasGroundingSquawk || hoursOverdue > 10 || annualDaysRemaining < 0) {
    return "NOT AIRWORTHY";
  }
  if (hoursOverdue > 0 || annualDaysRemaining <= 30) {
    return "CAUTION";
  }
  return "AIRWORTHY";
}

function groundingConditions(status: AircraftStatus, squawks: Squawk[]): string[] {
  const reasons: string[] = [];
  const hoursOverdue = status.oilHoursOverdue ?? 0;
  if (status.annualDaysRemaining !== null && status.annualDaysRemaining < 0) {
    reasons.push(`Annual inspection expired ${Math.abs(status.annualDaysRemaining)} days ago`);
  }
  if (hoursOverdue > 10) {
    reasons.push(`Oil change ${hoursOverdue.toFixed(1)} hours overdue (>${10}hr threshold)`);
  }
  squawks
    .filter((s) => s.severity === "grounding" && s.status === "open")
    .forEach((s) => reasons.push(`Grounding squawk: ${s.description.slice(0, 80)}…`));
  return reasons;
}

function cautionConditions(status: AircraftStatus, squawks: Squawk[]): string[] {
  const conditions: string[] = [];
  const hoursOverdue = status.oilHoursOverdue ?? 0;
  if (hoursOverdue > 0 && hoursOverdue <= 10) {
    conditions.push(`Oil change ${hoursOverdue.toFixed(1)} hours overdue`);
  }
  if (status.annualDaysRemaining !== null && status.annualDaysRemaining >= 0 && status.annualDaysRemaining <= 30) {
    conditions.push(`Annual due in ${status.annualDaysRemaining} days`);
  }
  squawks
    .filter((s) => s.severity === "non-grounding" && s.status === "open")
    .forEach((s) => conditions.push(`Open squawk: ${s.component} — ${s.description.slice(0, 60)}…`));
  return conditions;
}

export default function StatusDashboard() {
  const [status, setStatus] = useState<AircraftStatus | null>(null);
  const [squawks, setSquawks] = useState<Squawk[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const { demoMode } = useStore();

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([api.status(), api.squawks()])
      .then(([s, sq]) => {
        setStatus(s);
        setSquawks(sq);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [demoMode]);

  if (loading) return <LoadingState />;
  if (error) return <ErrorState message={error} />;
  if (!status) return null;

  const airworthiness = deriveAirworthiness(status, squawks);
  const smohPct = Math.min(100, status.engineSMOHPercent);
  const smohBarColor =
    smohPct >= 85 ? "bg-red-500" : smohPct >= 65 ? "bg-yellow-500" : "bg-emerald-500";

  return (
    <div className="space-y-6">
      {/* Three-state airworthiness banner */}
      <AirworthinessBanner
        state={airworthiness}
        status={status}
        squawks={squawks}
      />

      {/* Primary stats grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={<Clock className="w-4 h-4" />}
          label="Hobbs Time"
          value={`${status.hobbs.toFixed(1)} hr`}
          sub={`Tach: ${status.tach.toFixed(1)} hr`}
          color="sky"
        />
        <StatCard
          icon={<Gauge className="w-4 h-4" />}
          label="Engine SMOH"
          value={`${status.engineSMOH.toFixed(0)} hr`}
          sub={`${smohPct.toFixed(1)}% of ${status.engineTBO}hr TBO`}
          color={smohPct >= 85 ? "red" : smohPct >= 65 ? "yellow" : "emerald"}
        />
        <StatCard
          icon={<Calendar className="w-4 h-4" />}
          label="Annual Due"
          value={formatDate(status.annualDueDate) ?? "Unknown"}
          sub={
            status.annualDaysRemaining !== null
              ? status.annualDaysRemaining < 0
                ? `EXPIRED ${Math.abs(status.annualDaysRemaining)} days ago`
                : `${status.annualDaysRemaining} days remaining`
              : "Check records"
          }
          color={
            status.annualDaysRemaining === null
              ? "zinc"
              : status.annualDaysRemaining < 0
              ? "red"
              : status.annualDaysRemaining <= 30
              ? "red"
              : status.annualDaysRemaining <= 60
              ? "yellow"
              : "emerald"
          }
        />
        <StatCard
          icon={<AlertTriangle className="w-4 h-4" />}
          label="Open Squawks"
          value={`${status.openSquawkCount}`}
          sub={
            status.groundingSquawkCount > 0
              ? `${status.groundingSquawkCount} GROUNDING`
              : "None grounding"
          }
          color={
            status.groundingSquawkCount > 0
              ? "red"
              : status.openSquawkCount > 0
              ? "yellow"
              : "emerald"
          }
        />
      </div>

      {/* Engine SMOH progress bar */}
      <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-4">
        <div className="flex justify-between items-center mb-2">
          <span className="text-sm font-medium text-zinc-300">
            Engine TBO Progress — Lycoming O-320-H2AD
          </span>
          <span className="text-sm text-zinc-500">
            {status.engineSMOH.toFixed(0)} / {status.engineTBO} hr SMOH
          </span>
        </div>
        <div className="h-3 bg-zinc-800 rounded-full overflow-hidden">
          <div
            className={cn("h-full rounded-full transition-all duration-700", smohBarColor)}
            style={{ width: `${smohPct}%` }}
          />
        </div>
        <div className="flex justify-between mt-1 text-xs text-zinc-600">
          <span>0 hr (overhaul)</span>
          <span className="text-yellow-600">1000 hr midpoint</span>
          <span className="text-red-600">2000 hr TBO</span>
        </div>
        <p className="text-xs text-zinc-500 mt-2">
          H2AD variant — barrel lifters subject to AD 80-04-03 R2 recurring inspection ·{" "}
          {(status.engineTBO - status.engineSMOH).toFixed(0)} hr remaining to TBO
        </p>
      </div>

      {/* Open squawks */}
      {squawks.length > 0 && (
        <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-4">
          <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wide mb-3 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-yellow-400" />
            Open Squawks
          </h2>
          <div className="space-y-2">
            {squawks.map((sq) => (
              <div
                key={sq.externalId}
                className={cn(
                  "flex items-start gap-3 p-3 rounded-lg border text-sm",
                  severityColor(sq.severity)
                )}
              >
                <div className="flex-1 min-w-0">
                  <p className="font-medium leading-snug">{sq.description}</p>
                  <p className="text-xs opacity-60 mt-0.5">
                    {sq.component} · Identified {formatDate(sq.dateIdentified)}
                  </p>
                </div>
                <span
                  className={cn(
                    "shrink-0 text-xs px-2 py-0.5 rounded-full border uppercase tracking-wide font-medium",
                    severityColor(sq.severity)
                  )}
                >
                  {sq.severity}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Last maintenance */}
      <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-4">
        <div className="flex items-center gap-2 mb-1">
          <Wrench className="w-4 h-4 text-zinc-500" />
          <span className="text-sm font-medium text-zinc-400">Last Maintenance</span>
        </div>
        <p className="text-lg font-semibold text-zinc-200">
          {formatDate(status.lastMaintenanceDate)}
        </p>
        <p className="text-xs text-zinc-600 mt-1">
          Data fresh: {new Date(status.dataFreshAt).toLocaleTimeString()}
        </p>
      </div>
    </div>
  );
}

function AirworthinessBanner({
  state,
  status,
  squawks,
}: {
  state: AirworthinessState;
  status: AircraftStatus;
  squawks: Squawk[];
}) {
  if (state === "AIRWORTHY") {
    return (
      <div className="flex items-center gap-3 p-4 rounded-xl border bg-emerald-950/30 border-emerald-800/40 text-emerald-300">
        <CheckCircle className="w-5 h-5 shrink-0" />
        <div>
          <p className="font-semibold text-sm">N4798E — AIRWORTHY ✓</p>
          <p className="text-xs opacity-70 mt-0.5">
            Annual current · No grounding squawks · All ADs compliant
          </p>
        </div>
      </div>
    );
  }

  if (state === "CAUTION") {
    const conditions = cautionConditions(status, squawks);
    return (
      <div className="p-4 rounded-xl border bg-yellow-950/30 border-yellow-700/40 text-yellow-300">
        <div className="flex items-center gap-3 mb-2">
          <AlertTriangle className="w-5 h-5 shrink-0" />
          <p className="font-semibold text-sm">N4798E — CAUTION ⚠</p>
        </div>
        <ul className="space-y-1 pl-8">
          {conditions.map((c) => (
            <li key={c} className="text-xs opacity-80 flex items-start gap-1.5">
              <span className="text-yellow-500 mt-0.5">•</span>
              {c}
            </li>
          ))}
        </ul>
        <p className="text-xs text-yellow-600/70 mt-2 pl-8">
          Not grounded — review conditions before flying
        </p>
      </div>
    );
  }

  // NOT AIRWORTHY
  const conditions = groundingConditions(status, squawks);
  return (
    <div className="p-4 rounded-xl border bg-red-950/30 border-red-700/40 text-red-300">
      <div className="flex items-center gap-3 mb-2">
        <XCircle className="w-5 h-5 shrink-0" />
        <p className="font-semibold text-sm">N4798E — NOT AIRWORTHY ✗</p>
      </div>
      <ul className="space-y-1 pl-8">
        {conditions.map((c) => (
          <li key={c} className="text-xs opacity-80 flex items-start gap-1.5">
            <span className="text-red-500 mt-0.5">•</span>
            {c}
          </li>
        ))}
      </ul>
      <div className="flex items-start gap-1.5 mt-2 pl-8">
        <Info className="w-3 h-3 text-red-500 shrink-0 mt-0.5" />
        <p className="text-xs text-red-400/70">
          Aircraft must not be flown until all grounding conditions are resolved
        </p>
      </div>
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  sub,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub: string;
  color: string;
}) {
  const colorMap: Record<string, string> = {
    sky: "text-sky-400",
    emerald: "text-emerald-400",
    yellow: "text-yellow-400",
    red: "text-red-400",
    zinc: "text-zinc-400",
  };
  const bgMap: Record<string, string> = {
    sky: "bg-sky-500/10 border-sky-500/20",
    emerald: "bg-emerald-500/10 border-emerald-500/20",
    yellow: "bg-yellow-500/10 border-yellow-500/20",
    red: "bg-red-500/10 border-red-500/20",
    zinc: "bg-zinc-800 border-zinc-700",
  };

  return (
    <div className={cn("rounded-xl border p-4", bgMap[color] || bgMap["zinc"])}>
      <div className={cn("flex items-center gap-2 mb-1", colorMap[color] || "text-zinc-400")}>
        {icon}
        <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
      </div>
      <p className={cn("text-2xl font-bold", colorMap[color] || "text-zinc-200")}>{value}</p>
      <p className="text-xs text-zinc-500 mt-0.5">{sub}</p>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="h-16 bg-zinc-800 rounded-xl" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-24 bg-zinc-800 rounded-xl" />
        ))}
      </div>
      <div className="h-20 bg-zinc-800 rounded-xl" />
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-zinc-500">
      <XCircle className="w-8 h-8 mb-3 text-red-500" />
      <p className="font-medium text-zinc-300">Could not load aircraft status</p>
      <p className="text-sm mt-1 font-mono text-zinc-600 max-w-md text-center">{message}</p>
      <p className="text-xs mt-3 text-zinc-700">
        Make sure the mock CDF server (port 4000) and API server (port 3000) are running.
      </p>
    </div>
  );
}
