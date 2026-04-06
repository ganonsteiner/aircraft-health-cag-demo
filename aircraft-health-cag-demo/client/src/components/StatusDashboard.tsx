import { useEffect, useState } from "react";
import {
  Clock,
  Calendar,
  AlertTriangle,
  Activity,
  CheckCircle,
  XCircle,
  Wrench,
  Info,
  MessageSquare,
} from "lucide-react";
import { cn, formatDate, severityColor } from "../lib/utils";
import { api } from "../lib/api";
import { TAILS, type TailNumber } from "../lib/store";
import type { AircraftStatus, Squawk } from "../lib/types";

type AirworthinessState = "AIRWORTHY" | "FERRY_ONLY" | "CAUTION" | "NOT_AIRWORTHY" | "UNKNOWN";

function deriveAirworthiness(status: AircraftStatus): AirworthinessState {
  return (status.airworthiness as AirworthinessState) || "UNKNOWN";
}

function formatBannerAnnual(status: AircraftStatus): string {
  const d = status.annualDaysRemaining;
  if (d === null) return "Annual unknown";
  if (d < 0) return `Annual expired (${Math.abs(d)}d ago)`;
  if (d <= 30) return `Annual due in ${d} days`;
  return "Annual current";
}

function formatBannerOil(status: AircraftStatus): string {
  const over = status.oilTachHoursOverdue ?? status.oilHoursOverdue ?? 0;
  const until = Math.max(0, status.oilTachHoursUntilDue ?? 0);
  if (over > 0) return `Oil ${over.toFixed(1)} hr overdue`;
  if (until > 0) return `Oil due in ${until.toFixed(1)} hr`;
  return "Oil current";
}

function formatBannerSquawks(status: AircraftStatus): string {
  const n = status.groundingSquawkCount;
  if (n <= 0) return "No grounding squawks";
  return n === 1 ? "1 grounding squawk" : `${n} grounding squawks`;
}

function buildAirworthinessBannerLine2(status: AircraftStatus): string {
  return `${formatBannerAnnual(status)} · ${formatBannerOil(status)} · ${formatBannerSquawks(status)}`;
}

/** Shared clickable panel wrapper — tooltip + hover affordance. */
function ClickPanel({
  chatHint,
  onClick,
  className,
  children,
}: {
  chatHint: string;
  onClick: () => void;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={chatHint}
      aria-label={chatHint}
      className={cn(
        "w-full text-left cursor-pointer group/panel transition-all",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-500",
        className
      )}
    >
      {children}
      <div className="flex items-center gap-1 mt-2 opacity-0 group-hover/panel:opacity-60 transition-opacity text-xs text-sky-400">
        <MessageSquare className="w-3 h-3" />
        <span>Ask in AI Assistant</span>
      </div>
    </button>
  );
}

interface Props {
  selectedAircraft: TailNumber | null;
  onSelectAircraft: (tail: TailNumber | null) => void;
  onOpenAssistant?: () => void;
}

export default function StatusDashboard({ selectedAircraft, onSelectAircraft, onOpenAssistant }: Props) {
  const tail = selectedAircraft ?? "N4798E";
  const [status, setStatus] = useState<AircraftStatus | null>(null);
  const [squawks, setSquawks] = useState<Squawk[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    Promise.all([api.status(tail), api.squawks(tail)])
      .then(([s, sq]) => {
        setStatus(s);
        setSquawks(sq);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [tail]);

  const open = onOpenAssistant ?? (() => {});

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-4xl mx-auto py-6 px-2 space-y-6">
        <div className="flex items-center gap-2">
          <span className="text-xs text-zinc-500">Aircraft:</span>
          <div className="flex gap-1 flex-wrap">
            {TAILS.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => onSelectAircraft(t)}
                className={cn(
                  "px-2.5 py-0.5 rounded-full text-xs font-medium border transition-colors",
                  tail === t
                    ? "bg-sky-600 text-white border-sky-500"
                    : "bg-zinc-800 text-zinc-400 border-zinc-700 hover:border-zinc-500"
                )}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        {error ? (
          <ErrorState message={error} />
        ) : loading || !status || status.tail !== tail ? (
          <DashboardSkeleton />
        ) : (
          <DashboardContent tail={tail} status={status} squawks={squawks} onOpenAssistant={open} />
        )}
      </div>
    </div>
  );
}

function DashboardContent({
  tail,
  status,
  squawks,
  onOpenAssistant,
}: {
  tail: string;
  status: AircraftStatus;
  squawks: Squawk[];
  onOpenAssistant: () => void;
}) {
  const airworthiness = deriveAirworthiness(status);
  const smohPct = Math.min(100, status.engineSMOHPercent);
  const smohBarColor =
    smohPct >= 85 ? "bg-red-500" : smohPct >= 65 ? "bg-yellow-500" : "bg-emerald-500";
  const open = onOpenAssistant;

  const oilSubParts: string[] = [];
  if (status.oilNextDueTach > 0) {
    oilSubParts.push(`Due at ${status.oilNextDueTach.toFixed(1)} tach`);
  }
  if (status.oilNextDueDate) {
    const fd = formatDate(status.oilNextDueDate);
    if (fd) oilSubParts.push(fd);
  }
  const oilSub = oilSubParts.length > 0 ? oilSubParts.join(" · ") : "Per maintenance log";

  const annualSub =
    status.annualDaysRemaining === null
      ? "—"
      : status.annualDaysRemaining < 0
      ? `${Math.abs(status.annualDaysRemaining)} days ago`
      : `${status.annualDaysRemaining} days`;

  return (
    <div className="space-y-6">
      <AirworthinessBanner
        state={airworthiness}
        tail={tail}
        status={status}
        onOpenAssistant={open}
      />

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <AircraftTimeCard hobbs={status.hobbs} tach={status.tach} onClick={open} />
        <StatCard
          icon={<Wrench className="w-4 h-4" />}
          label="Oil Life"
          value={
            (status.oilTachHoursOverdue ?? status.oilHoursOverdue) > 0
              ? `${(status.oilTachHoursOverdue ?? status.oilHoursOverdue).toFixed(1)} hr overdue`
              : status.oilNextDueTach > 0
              ? `${Math.max(0, status.oilTachHoursUntilDue).toFixed(1)} hr`
              : "—"
          }
          sub={oilSub}
          color={
            (status.oilTachHoursOverdue ?? status.oilHoursOverdue) > 5
              ? "red"
              : (status.oilTachHoursOverdue ?? status.oilHoursOverdue) >= 1
              ? "yellow"
              : status.oilTachHoursUntilDue > 0 && status.oilTachHoursUntilDue <= 10
              ? "yellow"
              : "emerald"
          }
          chatHint="Ask about oil change interval in the AI Assistant"
          onClick={open}
        />
        <StatCard
          icon={<Calendar className="w-4 h-4" />}
          label="Annual Due"
          value={formatDate(status.annualDueDate) ?? "Unknown"}
          sub={annualSub}
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
          chatHint="Ask about annual inspection currency in the AI Assistant"
          onClick={open}
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
          chatHint="Ask about open squawks in the AI Assistant"
          onClick={open}
        />
      </div>

      <ClickPanel
        chatHint="Ask about engine time, TBO, and H2AD maintenance in the AI Assistant"
        onClick={open}
        className="bg-zinc-900 rounded-xl border border-zinc-800 p-4 hover:border-zinc-600"
      >
        <div className="flex justify-between items-center gap-3 mb-3">
          <span className="text-sm font-medium text-zinc-300">
            Engine life · Lycoming O-320-H2AD
          </span>
          <span className="text-sm text-zinc-500 tabular-nums shrink-0">
            {status.engineSMOH.toFixed(0)} / {status.engineTBO} hr
          </span>
        </div>
        <div className="h-3 bg-zinc-800 rounded-full overflow-hidden">
          <div
            className={cn("h-full rounded-full transition-all duration-700", smohBarColor)}
            style={{ width: `${smohPct}%` }}
          />
        </div>
        <p className="text-xs text-zinc-500 mt-2">
          H2AD · AD 80-04-03 R2 · {(status.engineTBO - status.engineSMOH).toFixed(0)} hr to TBO
        </p>
      </ClickPanel>

      {squawks.length > 0 && (
        <ClickPanel
          chatHint="Ask about these squawks in the AI Assistant"
          onClick={open}
          className="bg-zinc-900 rounded-xl border border-zinc-800 p-4 hover:border-zinc-600"
        >
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
        </ClickPanel>
      )}

      {(status.symptoms ?? []).length > 0 && (
        <ClickPanel
          chatHint="Ask about these symptoms and fleet-wide patterns in the AI Assistant"
          onClick={open}
          className="bg-zinc-900 rounded-xl border border-zinc-800 p-4 hover:border-zinc-600"
        >
          <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wide mb-3 flex items-center gap-2">
            <Activity className="w-4 h-4 text-orange-400" />
            Observed Symptoms
          </h2>
          <div className="space-y-2">
            {(status.symptoms ?? []).map((sym) => (
              <div
                key={sym.externalId}
                className={cn(
                  "flex items-start gap-3 p-3 rounded-lg border text-sm",
                  severityColor(sym.severity)
                )}
              >
                <div className="flex-1 min-w-0">
                  <p className="font-medium leading-snug">{sym.title}</p>
                  <p className="text-zinc-300/90 mt-1 leading-snug">{sym.description}</p>
                  {sym.observation ? (
                    <p className="text-xs opacity-70 mt-1.5 leading-snug">{sym.observation}</p>
                  ) : null}
                  <p className="text-xs opacity-60 mt-1">
                    First observed {(formatDate(sym.firstObserved) ?? sym.firstObserved) || "—"}
                  </p>
                </div>
                <span
                  className={cn(
                    "shrink-0 text-xs px-2 py-0.5 rounded-full border uppercase tracking-wide font-medium",
                    severityColor(sym.severity)
                  )}
                >
                  {sym.severity}
                </span>
              </div>
            ))}
          </div>
        </ClickPanel>
      )}

      <ClickPanel
        chatHint="Ask about maintenance history and upcoming items in the AI Assistant"
        onClick={open}
        className="bg-zinc-900 rounded-xl border border-zinc-800 p-4 hover:border-zinc-600"
      >
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
      </ClickPanel>
    </div>
  );
}

const BANNER_HINTS: Record<AirworthinessState, string> = {
  AIRWORTHY: "Ask about airworthiness and operational status in the AI Assistant",
  FERRY_ONLY: "Ask about ferry policy and oil compliance in the AI Assistant",
  CAUTION: "Ask about caution items and required inspections in the AI Assistant",
  NOT_AIRWORTHY: "Ask about grounding reasons and next steps in the AI Assistant",
  UNKNOWN: "Ask about airworthiness status in the AI Assistant",
};

const BANNER_STYLE: Record<
  AirworthinessState,
  { Icon: typeof CheckCircle; line1: string; panel: string }
> = {
  AIRWORTHY: {
    Icon: CheckCircle,
    line1: "AIRWORTHY ✓",
    panel: "bg-emerald-950/30 border-emerald-800/40 text-emerald-300 hover:border-emerald-700",
  },
  FERRY_ONLY: {
    Icon: Info,
    line1: "FERRY ONLY",
    panel: "bg-yellow-950/30 border-yellow-700/40 text-yellow-300 hover:border-yellow-600",
  },
  CAUTION: {
    Icon: AlertTriangle,
    line1: "CAUTION ⚠",
    panel: "bg-orange-950/30 border-orange-700/40 text-orange-300 hover:border-orange-600",
  },
  NOT_AIRWORTHY: {
    Icon: XCircle,
    line1: "NOT AIRWORTHY ✗",
    panel: "bg-red-950/30 border-red-700/40 text-red-300 hover:border-red-600",
  },
  UNKNOWN: {
    Icon: Info,
    line1: "UNKNOWN",
    panel: "bg-zinc-900/40 border-zinc-700 text-zinc-400 hover:border-zinc-600",
  },
};

function AirworthinessBanner({
  state,
  tail,
  status,
  onOpenAssistant,
}: {
  state: AirworthinessState;
  tail: string;
  status: AircraftStatus;
  onOpenAssistant: () => void;
}) {
  const cfg = BANNER_STYLE[state];
  const Icon = cfg.Icon;
  const line2 = buildAirworthinessBannerLine2(status);

  return (
    <ClickPanel
      chatHint={BANNER_HINTS[state]}
      onClick={onOpenAssistant}
      className={cn("flex items-start gap-3 p-4 rounded-xl border", cfg.panel)}
    >
      <Icon className="w-5 h-5 shrink-0 mt-0.5" />
      <div className="min-w-0">
        <p className="font-semibold text-sm">
          {tail} — {cfg.line1}
        </p>
        <p className="text-xs opacity-70 mt-0.5 leading-snug">{line2}</p>
      </div>
    </ClickPanel>
  );
}

function AircraftTimeCard({
  hobbs,
  tach,
  onClick,
}: {
  hobbs: number;
  tach: number;
  onClick: () => void;
}) {
  const hint = "Ask about Hobbs and tach time in the AI Assistant";
  return (
    <button
      type="button"
      onClick={onClick}
      title={hint}
      aria-label={hint}
      className={cn(
        "rounded-xl border p-4 text-left w-full cursor-pointer transition-all group/stat",
        "bg-sky-500/10 border-sky-500/20 hover:border-sky-400/40",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-500"
      )}
    >
      <div className="flex items-center gap-2 mb-2 text-sky-400">
        <Clock className="w-4 h-4" />
        <span className="text-xs font-medium uppercase tracking-wide">Aircraft time</span>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <p className="text-xs text-zinc-500">Hobbs</p>
          <p className="text-2xl font-bold tabular-nums text-sky-400 leading-tight">{hobbs.toFixed(1)}</p>
          <p className="text-xs text-zinc-600">hr</p>
        </div>
        <div>
          <p className="text-xs text-zinc-500">Tach</p>
          <p className="text-2xl font-bold tabular-nums text-sky-400 leading-tight">{tach.toFixed(1)}</p>
          <p className="text-xs text-zinc-600">hr</p>
        </div>
      </div>
      <div className="flex items-center gap-1 mt-1.5 opacity-0 group-hover/stat:opacity-60 transition-opacity text-xs text-sky-400">
        <MessageSquare className="w-3 h-3" />
        <span>Ask in AI Assistant</span>
      </div>
    </button>
  );
}

function StatCard({
  icon,
  label,
  value,
  sub,
  color,
  chatHint,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub: string;
  color: string;
  chatHint: string;
  onClick: () => void;
}) {
  const colorMap: Record<string, string> = {
    sky: "text-sky-400",
    emerald: "text-emerald-400",
    yellow: "text-yellow-400",
    red: "text-red-400",
    zinc: "text-zinc-400",
  };
  const bgMap: Record<string, string> = {
    sky: "bg-sky-500/10 border-sky-500/20 hover:border-sky-400/40",
    emerald: "bg-emerald-500/10 border-emerald-500/20 hover:border-emerald-400/40",
    yellow: "bg-yellow-500/10 border-yellow-500/20 hover:border-yellow-400/40",
    red: "bg-red-500/10 border-red-500/20 hover:border-red-400/40",
    zinc: "bg-zinc-800 border-zinc-700 hover:border-zinc-500",
  };

  return (
    <button
      type="button"
      onClick={onClick}
      title={chatHint}
      aria-label={chatHint}
      className={cn(
        "rounded-xl border p-4 text-left w-full cursor-pointer transition-all group/stat",
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-500",
        bgMap[color] || bgMap["zinc"]
      )}
    >
      <div className={cn("flex items-center gap-2 mb-1", colorMap[color] || "text-zinc-400")}>
        {icon}
        <span className="text-xs font-medium uppercase tracking-wide">{label}</span>
      </div>
      <p className={cn("text-2xl font-bold", colorMap[color] || "text-zinc-200")}>{value}</p>
      <p className="text-xs text-zinc-500 mt-0.5">{sub}</p>
      <div className="flex items-center gap-1 mt-1.5 opacity-0 group-hover/stat:opacity-60 transition-opacity text-xs text-sky-400">
        <MessageSquare className="w-3 h-3" />
        <span>Ask in AI Assistant</span>
      </div>
    </button>
  );
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <div className="rounded-xl border border-zinc-800/80 p-4 min-h-[5.5rem] bg-zinc-900/40">
        <div className="flex gap-3 animate-pulse">
          <div className="w-5 h-5 rounded-full bg-zinc-800 shrink-0 mt-0.5" />
          <div className="flex-1 space-y-2 min-w-0">
            <div className="h-4 bg-zinc-800 rounded w-48 max-w-full" />
            <div className="h-3 bg-zinc-800/80 rounded w-full max-w-md" />
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        <div className="rounded-xl border border-zinc-800/60 p-4 min-h-[7.5rem] bg-zinc-900/40 animate-pulse">
          <div className="h-3 bg-zinc-800 rounded w-24 mb-3" />
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="h-2.5 bg-zinc-800/80 rounded w-10 mb-1" />
              <div className="h-8 bg-zinc-800 rounded w-16" />
            </div>
            <div>
              <div className="h-2.5 bg-zinc-800/80 rounded w-10 mb-1" />
              <div className="h-8 bg-zinc-800 rounded w-16" />
            </div>
          </div>
        </div>
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="rounded-xl border border-zinc-800/60 p-4 min-h-[7rem] bg-zinc-900/40 animate-pulse"
          >
            <div className="h-3 bg-zinc-800 rounded w-20 mb-3" />
            <div className="h-8 bg-zinc-800 rounded w-24 mb-2" />
            <div className="h-3 bg-zinc-800/80 rounded w-32" />
          </div>
        ))}
      </div>
      <div className="rounded-xl border border-zinc-800 p-4 min-h-[6.5rem] bg-zinc-900/40 space-y-3 animate-pulse">
        <div className="flex justify-between gap-4">
          <div className="h-4 bg-zinc-800 rounded flex-1 max-w-xs" />
          <div className="h-4 bg-zinc-800 rounded w-28 shrink-0" />
        </div>
        <div className="h-3 bg-zinc-800 rounded-full w-full" />
        <div className="h-3 bg-zinc-800/80 rounded w-full max-w-lg" />
      </div>
      <div className="rounded-xl border border-zinc-800 p-4 min-h-[5.5rem] bg-zinc-900/40 animate-pulse">
        <div className="h-4 bg-zinc-800 rounded w-36 mb-3" />
        <div className="h-6 bg-zinc-800 rounded w-28" />
        <div className="h-3 bg-zinc-800/80 rounded w-44 mt-2" />
      </div>
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
