import { useState, useEffect } from "react";
import {
  RefreshCw,
  ChevronDown,
  AlertTriangle,
  Info,
  Shield,
  Wrench,
  Activity,
} from "lucide-react";
import { api } from "../lib/api";
import {
  cn,
  CARD_SURFACE_A,
  CARD_SURFACE_B,
  MAIN_TAB_CONTENT_FRAME,
  TAB_PAGE_TOP_INSET,
  toneClasses,
} from "../lib/utils";
import type { Insight, InsightsResponse } from "../lib/types";

type CategoryFilter = "all" | "safety" | "maintenance" | "pattern" | "compliance";

const SEVERITY_CONFIG: Record<
  Insight["severity"],
  { label: string; badge: string; dot: string }
> = {
  critical: {
    label: "Critical",
    badge: toneClasses("bad").badge,
    dot: "bg-red-500",
  },
  warning: {
    label: "Warning",
    badge: toneClasses("warn").badge,
    dot: "bg-orange-500",
  },
  info: {
    label: "Info",
    badge: "bg-blue-50 text-[#304cb2] border border-blue-200",
    dot: "bg-[#304cb2]",
  },
};

const CATEGORY_ICONS: Record<string, React.FC<{ className?: string }>> = {
  safety: AlertTriangle,
  maintenance: Wrench,
  pattern: Activity,
  compliance: Shield,
};

const SEVERITY_ORDER: Record<Insight["severity"], number> = {
  critical: 0,
  warning: 1,
  info: 2,
};

export default function AgenticInsights(_props: { active?: boolean } = {}) {
  const [data, setData] = useState<InsightsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<CategoryFilter>("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchInsights = () => {
    setLoading(true);
    setError(null);
    api
      .insights()
      .then(setData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  const handleRefresh = (force = false) => {
    const prevGeneratedAt = data?.generated_at ?? null;
    setRefreshing(true);
    api.refreshInsights(force).then((res: { status?: string }) => {
      if (res?.status === "already_cached") {
        fetchInsights();
        setRefreshing(false);
        return;
      }
      // Server runs one consolidated agent call (~1-2 min). Poll up to 5 min.
      const deadline = Date.now() + 300_000;
      const poll = () => {
        api.insights().then((r) => {
          if (r.generated_at !== prevGeneratedAt) {
            setData(r);
            setRefreshing(false);
          } else if (Date.now() < deadline) {
            setTimeout(poll, 3000);
          } else {
            setRefreshing(false);
            fetchInsights();
          }
        }).catch(() => { setRefreshing(false); });
      };
      setTimeout(poll, 3000);
    }).catch(() => setRefreshing(false));
  };

  // On mount: fetch whatever's cached AND start a background poll so that once the
  // server-side generation (kicked off at app launch) finishes, this page updates
  // automatically — even if the user hasn't visited the tab yet.
  useEffect(() => {
    fetchInsights();
    let cancelled = false;
    const deadline = Date.now() + 300_000;
    const schedule = () => {
      if (!cancelled && Date.now() < deadline) setTimeout(poll, 3500);
    };
    const poll = () => {
      if (cancelled) return;
      api.insights().then((r) => {
        if (cancelled) return;
        setData(r);
        // Stop only when we have real insights. If the backend reports fallback
        // we keep polling a little in case a retry completes; the deadline bounds it.
        const hasRealData = r.insights && r.insights.length > 0;
        if (!hasRealData) schedule();
      }).catch(() => schedule());
    };
    setTimeout(poll, 2500);
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filteredInsights = (data?.insights ?? [])
    .filter((i) => categoryFilter === "all" || i.category === categoryFilter)
    .sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 3) - (SEVERITY_ORDER[b.severity] ?? 3));

  return (
    <div className="flex flex-1 min-h-0 flex-col overflow-y-auto w-full">
      <div className={cn("flex flex-col min-w-0 pb-6", MAIN_TAB_CONTENT_FRAME, TAB_PAGE_TOP_INSET)}>
      {/* Header */}
      <div className="shrink-0 flex items-center justify-between gap-4 mb-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">Agentic Insights</h2>
          <p className="text-xs text-slate-400 mt-0.5">AI-powered fleet tracking</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => handleRefresh(true)}
            disabled={refreshing || loading}
            title="Regenerate insights"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-slate-200 text-slate-600 hover:border-slate-300 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <RefreshCw className={cn("w-3.5 h-3.5", (refreshing) && "animate-spin")} />
            Refresh
          </button>
        </div>
      </div>

      {/* Fallback banner */}
      {data?.is_fallback && (
        <div className="shrink-0 flex items-center gap-2 px-3 py-2 mb-3 rounded-lg bg-card border border-amber-300 border-l-[3px] border-l-amber-500 text-amber-700 text-xs">
          <Info className="w-3.5 h-3.5 shrink-0" />
          LLM unavailable — Configure ANTHROPIC_API_KEY for live generation.
        </div>
      )}

      {/* Category filters */}
      <div className="shrink-0 flex gap-2 mb-4 flex-wrap">
        {(["all", "safety", "maintenance", "pattern", "compliance"] as CategoryFilter[]).map(
          (cat) => {
            const Icon = cat !== "all" ? CATEGORY_ICONS[cat] : null;
            return (
              <button
                key={cat}
                type="button"
                onClick={() => setCategoryFilter(cat)}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors",
                  categoryFilter === cat
                    ? "bg-[#304cb2] text-white border-[#304cb2]"
                    : "bg-white text-slate-600 border-slate-200 hover:border-slate-300"
                )}
              >
                {Icon && <Icon className="w-3 h-3" />}
                {cat === "all" ? "All" : cat.charAt(0).toUpperCase() + cat.slice(1)}
              </button>
            );
          }
        )}
      </div>

      {/* Content */}
      <div>
        {loading && (
          <div className="flex flex-col gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div
                key={i}
                className={cn("h-28 rounded-xl animate-pulse", CARD_SURFACE_A)}
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
            {filteredInsights.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 text-slate-400">
                <Info className="w-8 h-8 mb-3" />
                <p className="text-sm">No insights in this category</p>
              </div>
            ) : (
              filteredInsights.map((insight) => {
                const sevCfg = SEVERITY_CONFIG[insight.severity] ?? SEVERITY_CONFIG.info;
                const expanded = expandedId === insight.id;

                return (
                  <div key={insight.id} className={cn("rounded-xl p-4", CARD_SURFACE_B)}>
                    <div className="flex items-start gap-3">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap mb-1.5">
                          <span
                            className={cn(
                              "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-semibold",
                              sevCfg.badge
                            )}
                          >
                            <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", sevCfg.dot)} />
                            {sevCfg.label}
                          </span>
                          <span className="text-[11px] text-slate-400 uppercase tracking-wider font-medium">
                            {insight.category}
                          </span>
                        </div>
                        <h3 className="font-semibold text-sm text-slate-900">{insight.title}</h3>
                      </div>
                      <button
                        type="button"
                        onClick={() => setExpandedId(expanded ? null : insight.id)}
                        className="shrink-0 p-1 rounded text-slate-400 hover:text-slate-600 transition-colors"
                        aria-label={expanded ? "Collapse reasoning" : "View AI reasoning"}
                      >
                        <ChevronDown
                          className={cn("w-4 h-4 transition-transform", expanded && "rotate-180")}
                        />
                      </button>
                    </div>

                    <p className="mt-2 text-sm text-slate-600 leading-relaxed">{insight.summary}</p>

                    {insight.aircraft.length > 0 && (
                      <div className="flex gap-1.5 mt-2.5 flex-wrap">
                        {insight.aircraft.map((t) => (
                          <span
                            key={t}
                            className="px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 text-slate-600 border border-slate-200"
                          >
                            {t}
                          </span>
                        ))}
                      </div>
                    )}

                    {expanded && insight.reasoning && (
                      <div className="mt-3 pt-3 border-t border-slate-200">
                        <p className="text-[10px] font-semibold text-slate-400 uppercase tracking-widest mb-1.5">
                          AI Reasoning
                        </p>
                        <p className="text-xs text-slate-600 leading-relaxed">{insight.reasoning}</p>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>
      </div>
    </div>
  );
}
