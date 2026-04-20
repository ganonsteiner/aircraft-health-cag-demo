import { useState, useEffect } from "react";
import {
  RefreshCw,
  ShieldCheck,
  AlertTriangle,
  ChevronDown,
  Wifi,
} from "lucide-react";
import { api } from "../lib/api";
import {
  cn,
  CARD_SURFACE_A,
  CARD_SURFACE_B,
  CARD_SURFACE_C,
  MAIN_TAB_CONTENT_FRAME,
  TAB_PAGE_TOP_INSET,
  toneClasses,
} from "../lib/utils";
import { TAILS, INSTRUMENTED_TAILS } from "../lib/store";
import type { PredictiveRisk } from "../lib/types";

const RISK_CONFIG: Record<
  string,
  { label: string; badge: string; barColor: string; card: string }
> = {
  low: {
    label: "Low Risk",
    badge: toneClasses("ok").badge,
    barColor: "bg-emerald-500",
    card: "border border-emerald-300 border-l-[3px] border-l-emerald-500",
  },
  moderate: {
    label: "Moderate",
    badge: toneClasses("warn").badge,
    barColor: "bg-amber-500",
    card: "border border-amber-300 border-l-[3px] border-l-amber-500",
  },
  high: {
    label: "High Risk",
    badge: "bg-orange-50 text-orange-700 border border-orange-200",
    barColor: "bg-orange-500",
    card: "border border-orange-300 border-l-[3px] border-l-orange-500",
  },
  critical: {
    label: "Critical",
    badge: toneClasses("bad").badge,
    barColor: "bg-red-600",
    card: "border border-red-300 border-l-[3px] border-l-red-500",
  },
  failed: {
    label: "Engine Failure",
    badge: toneClasses("bad").badge,
    barColor: "bg-red-700",
    card: "border border-red-300 border-l-[3px] border-l-red-600",
  },
};

function RiskScoreBar({ score, riskLevel }: { score: number; riskLevel: string }) {
  const cfg = RISK_CONFIG[riskLevel] ?? RISK_CONFIG.moderate;
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all", cfg.barColor)}
          style={{ width: `${Math.min(100, score)}%` }}
        />
      </div>
      <span className="text-xs tabular-nums font-semibold text-slate-700 w-8 shrink-0 text-right">
        {score}
      </span>
    </div>
  );
}

function InstrumentedRiskCard({
  risk,
}: {
  risk: PredictiveRisk;
}) {
  const [expanded, setExpanded] = useState(false);
  const cfg = RISK_CONFIG[risk.risk_level ?? "moderate"] ?? RISK_CONFIG.moderate;
  const primaryDriverDisplay = (risk.primary_driver || "")
    // Keep internal phrasing out of the UI.
    .replace(/\bno peer overlap\b\.?/gi, "")
    // Tidy up leftover punctuation/whitespace.
    .replace(/\s+,/g, ",")
    .replace(/,\s*,/g, ",")
    .replace(/\s{2,}/g, " ")
    .replace(/\s+([.)])/g, "$1")
    .trim()
    .replace(/^[,.\s]+/, "")
    .replace(/[,.\s]+$/, "")
    .trim();

  return (
    <div className={cn("rounded-xl p-4", CARD_SURFACE_B, cfg.card)}>
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="font-bold text-slate-900 text-sm">{risk.aircraft}</span>
            <span
              className={cn(
                "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-semibold",
                cfg.badge
              )}
            >
              {cfg.label}
            </span>
          </div>
          {primaryDriverDisplay && (
            <p className="text-xs text-slate-500 mb-2">
              Primary driver: {primaryDriverDisplay}
            </p>
          )}
          {risk.risk_score !== null && (
            <div className="mb-2">
              <div className="flex justify-between text-[11px] text-slate-400 mb-1">
                <span>Risk score</span>
                <span>{risk.risk_score} / 100</span>
              </div>
              <RiskScoreBar score={risk.risk_score} riskLevel={risk.risk_level ?? "moderate"} />
            </div>
          )}
          {risk.recommended_action && (
            <p className="text-xs font-medium text-slate-700 mt-2">
              Action: {risk.recommended_action}
            </p>
          )}
        </div>
        {risk.reasoning && (
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            className="shrink-0 p-1 rounded text-slate-400 hover:text-slate-600 transition-colors"
            aria-label={expanded ? "Collapse reasoning" : "View AI reasoning"}
          >
            <ChevronDown
              className={cn("w-4 h-4 transition-transform", expanded && "rotate-180")}
            />
          </button>
        )}
      </div>

      {expanded && risk.reasoning && (
        <div className="mt-3 pt-3 border-t border-slate-200">
          <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest mb-1.5">
            AI Reasoning
          </p>
          <p className="text-xs text-slate-600 leading-relaxed">{risk.reasoning}</p>
          {risk.data_points_analyzed !== null && (
            <p className="text-[11px] text-slate-400 mt-1.5">
              {risk.data_points_analyzed} sensor data points analyzed
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function PlaceholderCard({ tail }: { tail: string }) {
  return (
    <div className={cn("rounded-xl p-4", CARD_SURFACE_B)}>
      <div className="flex items-center gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-slate-900 text-sm">{tail}</span>
            <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-500 border border-slate-200">
              No telemetry data
            </span>
          </div>
        </div>
      </div>
      <div className="mt-3 h-2 bg-slate-100 rounded-full overflow-hidden">
        <div className="h-full w-0 rounded-full bg-slate-200" />
      </div>
    </div>
  );
}

export default function PredictiveMaintenance(_props: { active?: boolean } = {}) {
  const [riskMap, setRiskMap] = useState<Record<string, PredictiveRisk>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchAll = () => {
    setLoading(true);
    setError(null);
    const instrumented = INSTRUMENTED_TAILS as unknown as string[];
    Promise.all(instrumented.map((t) => api.predictive(t).catch(() => null)))
      .then((results) => {
        const map: Record<string, PredictiveRisk> = {};
        instrumented.forEach((t, i) => {
          if (results[i]) map[t] = results[i]!;
        });
        setRiskMap(map);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  const handleRefresh = (force = false) => {
    setRefreshing(true);
    const instrumented = INSTRUMENTED_TAILS as unknown as string[];
    // Snapshot previous generated_at per tail so we know when each one has been refreshed.
    const prevGeneratedAt: Record<string, string | null> = {};
    for (const t of instrumented) prevGeneratedAt[t] = riskMap[t]?.generated_at ?? null;

    Promise.all(
      instrumented.map((t) =>
        api.refreshPredictive(t, force).then((r: { status?: string } | null) => r).catch(() => null)
      )
    ).then((responses) => {
      // If every tail came back as "already_cached", just re-fetch to ensure the UI has the data.
      const allCached = responses.every((r) => r && r.status === "already_cached");
      if (allCached) {
        fetchAll();
        setRefreshing(false);
        return;
      }
      // 4 aircraft risk scorings run in parallel on the server. Poll up to 4 minutes.
      const deadline = Date.now() + 240_000;
      const poll = () => {
        Promise.all(instrumented.map((t) => api.predictive(t).catch(() => null))).then((results) => {
          const map: Record<string, PredictiveRisk> = {};
          instrumented.forEach((t, i) => { if (results[i]) map[t] = results[i]!; });
          const allDone = instrumented.every((t) => {
            const nowGen = map[t]?.generated_at ?? null;
            return nowGen !== prevGeneratedAt[t];
          });
          if (allDone) {
            setRiskMap(map);
            setRefreshing(false);
          } else if (Date.now() < deadline) {
            setRiskMap(map); // show partial progress
            setTimeout(poll, 3000);
          } else {
            setRiskMap(map);
            setRefreshing(false);
          }
        }).catch(() => { setRefreshing(false); });
      };
      setTimeout(poll, 3000);
    });
  };

  // On mount: pull the current cache AND start a background poll so when the
  // server-side refresh (triggered at app launch) completes, this page updates
  // automatically even if the user hasn't visited this tab yet.
  useEffect(() => {
    fetchAll();
    const instrumented = INSTRUMENTED_TAILS as unknown as string[];
    let cancelled = false;
    const deadline = Date.now() + 300_000;
    const schedule = () => {
      if (!cancelled && Date.now() < deadline) setTimeout(poll, 3500);
    };
    const poll = () => {
      if (cancelled) return;
      Promise.all(instrumented.map((t) => api.predictive(t).catch(() => null))).then((results) => {
        if (cancelled) return;
        const map: Record<string, PredictiveRisk> = {};
        instrumented.forEach((t, i) => { if (results[i]) map[t] = results[i]!; });
        setRiskMap(map);
        const allScored = instrumented.every((t) => map[t]?.status === "scored");
        if (!allScored) schedule();
      }).catch(() => schedule());
    };
    setTimeout(poll, 2500);
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const scoredRisks = Object.values(riskMap)
    .filter((r) => r.status === "scored")
    .sort((a, b) => (b.risk_score ?? 0) - (a.risk_score ?? 0));

  const placeholderTails = (TAILS as unknown as string[]).filter(
    (t) => !scoredRisks.some((r) => r.aircraft === t)
  );

  const riskCounts = {
    critical: scoredRisks.filter((r) => r.risk_level === "critical" || r.risk_level === "failed")
      .length,
    high: scoredRisks.filter((r) => r.risk_level === "high").length,
    moderate: scoredRisks.filter((r) => r.risk_level === "moderate").length,
    low: scoredRisks.filter((r) => r.risk_level === "low").length,
    insufficient: placeholderTails.length,
  };

  return (
    <div className="flex flex-1 min-h-0 flex-col overflow-y-auto w-full">
      <div className={cn("flex flex-col min-w-0 pb-6", MAIN_TAB_CONTENT_FRAME, TAB_PAGE_TOP_INSET)}>
      {/* Header */}
      <div className="shrink-0 flex items-center justify-between gap-4 mb-4">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Predictive Maintenance</h2>
          <p className="text-xs text-slate-400 mt-0.5">AI-powered risk assessment</p>
        </div>
        <button
          type="button"
          onClick={() => handleRefresh(true)}
          disabled={refreshing || loading}
          title="Regenerate risk scores"
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-slate-200 text-slate-600 hover:border-slate-300 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <RefreshCw className={cn("w-3.5 h-3.5", refreshing && "animate-spin")} />
          Refresh
        </button>
      </div>

      {/* Fleet risk summary — outer shell is muted (subdued) so the five
          in-focus stat tiles (white bg-card) visually pop forward. */}
      {!loading && !error && (
        <div className={cn("shrink-0 rounded-xl p-4 mb-4 grid grid-cols-2 sm:grid-cols-5 gap-3", CARD_SURFACE_A)}>
          {[
            { label: "Critical/Failed", count: riskCounts.critical, color: "text-red-500" },
            { label: "High", count: riskCounts.high, color: "text-orange-500" },
            { label: "Moderate", count: riskCounts.moderate, color: "text-amber-500" },
            { label: "Low", count: riskCounts.low, color: "text-emerald-500" },
            { label: "Insufficient Data", count: riskCounts.insufficient, color: "text-slate-400" },
          ].map((s) => (
            <div key={s.label} className={cn("rounded-lg p-3 text-center", CARD_SURFACE_B)}>
              <div className={cn("text-xl font-bold", s.color)}>{s.count}</div>
              <div className="text-[11px] text-slate-400 mt-0.5">{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Content */}
      <div>
        {loading && (
          <div className="flex flex-col gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                className={cn("h-24 rounded-xl animate-pulse", CARD_SURFACE_A)}
                aria-busy="true"
              />
            ))}
          </div>
        )}

        {error && (
          <div className={cn("flex items-center gap-3 p-4 rounded-xl", toneClasses("bad").bannerPanel)}>
            <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}

        {!loading && !error && (
          <div className="flex flex-col gap-3">
            {/* Scored instrumented aircraft */}
            {scoredRisks.map((risk) => (
              <InstrumentedRiskCard key={risk.aircraft} risk={risk} />
            ))}

            {/* Placeholder section header */}
            {placeholderTails.length > 0 && (
              <div className="flex items-center gap-3 mt-2 mb-1">
                <div className="flex-1 h-px bg-slate-200" />
                <div className="flex items-center gap-1.5 text-xs text-slate-400">
                  <Wifi className="w-3.5 h-3.5" />
                  <span>{placeholderTails.length} aircraft — no telemetry data</span>
                </div>
                <div className="flex-1 h-px bg-slate-200" />
              </div>
            )}

            {/* Placeholder aircraft */}
            {placeholderTails.map((tail) => (
              <PlaceholderCard key={tail} tail={tail} />
            ))}

            {/* "How this works" section */}
            <div className={cn("rounded-xl border border-slate-200 p-4 mt-2", CARD_SURFACE_B)}>
              <div className="flex items-center gap-2 mb-2">
                <ShieldCheck className="w-4 h-4 text-[#304cb2]" />
                <span className="text-xs font-semibold text-slate-700">How This Works</span>
              </div>
              <p className="text-xs text-slate-500 leading-relaxed">
                The AI agent traverses the fleet knowledge graph to analyze engine sensor trends —
                EGT deviation, N1 vibration, oil temperatures — for aircraft with active telemetry.
                It identifies patterns that preceded historical engine events and compares those
                patterns against current readings to generate risk scores and recommended actions.
                Aircraft without sensor data show no risk score.
              </p>
            </div>
          </div>
        )}
      </div>
      </div>
    </div>
  );
}
