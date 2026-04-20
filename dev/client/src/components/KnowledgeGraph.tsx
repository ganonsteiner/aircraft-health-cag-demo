import { useEffect, useState, useMemo, useRef } from "react";
import {
  Box,
  Crosshair,
  FileText,
  LineChart,
  RotateCcw,
  Share2,
  AlertTriangle,
  Waypoints,
  Zap,
} from "lucide-react";
import {
  cn,
  CARD_SURFACE_A,
  CARD_SURFACE_B,
  MAIN_TAB_CONTENT_FRAME,
  TAB_PAGE_TOP_INSET,
} from "../lib/utils";
import { api } from "../lib/api";
import {
  highlightedGraphIdsFromTraversal,
  graphIdsFromTraversalNode,
} from "../lib/traversalGraphIds";
import { useStore } from "../lib/store";
import type { GraphData, GraphLink, GraphNode } from "../lib/types";
import TraversalGraph, { type TraversalGraphHandle } from "./TraversalGraph";

interface Props {
  active: boolean;
}

const STAGGER_MS = 150;

export default function KnowledgeGraph({ active }: Props) {
  const {
    traversalEvents,
    isQuerying,
    isReplaying,
    replayNodes,
    setGraphDataSnapshot,
  } = useStore();
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [_selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<TraversalGraphHandle>(null);
  const [viewport, setViewport] = useState<{ width: number; height: number }>({ width: 0, height: 0 });

  /** Load once per page session; revisiting the tab keeps data and TraversalGraph state (no re-fetch, no re-animation). */
  useEffect(() => {
    if (!active) return;
    if (graphData !== null) return;
    setLoading(true);
    setError(null);
    api
      .graph()
      .then(setGraphData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [active, graphData]);

  useEffect(() => {
    if (graphData) setGraphDataSnapshot(graphData);
  }, [graphData, setGraphDataSnapshot]);

  /**
   * Measure once on mount and on resize. The KG tab uses `opacity-0` when inactive so the
   * container stays in the layout — dimensions remain valid without re-measuring on tab switch.
   */
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => {
      const box = containerRef.current;
      if (box) {
        const w = box.clientWidth;
        const h = box.clientHeight;
        if (w > 0 && h > 0) {
          setViewport((prev) => (prev.width === w && prev.height === h ? prev : { width: w, height: h }));
        }
      }
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    const id = requestAnimationFrame(() => update());
    return () => {
      cancelAnimationFrame(id);
      ro.disconnect();
    };
  }, []);

  /** Set of graph node ids for fast membership checks. */
  const graphIdSet = useMemo(
    () => new Set(graphData?.nodes.map((n) => n.id) ?? []),
    [graphData]
  );

  // Staggered traversal highlight state — grows one batch at a time during streaming.
  const [visibleTraversedIds, setVisibleTraversedIds] = useState<Set<string>>(new Set());
  const idBufferRef = useRef<string[][]>([]);
  const drainTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lastEventCountRef = useRef(0);

  // Replay: replayNodes already advances at 150ms intervals in the store — derive directly.
  const replayTraversedIds = useMemo(
    () => (isReplaying ? highlightedGraphIdsFromTraversal(replayNodes, graphData) : null),
    [isReplaying, replayNodes, graphData]
  );

  // Streaming: buffer new traversal events, drain one batch of node IDs every 150ms.
  useEffect(() => {
    if (isReplaying) return;

    if (!isQuerying) {
      // Not streaming — show the full set immediately.
      const out = new Set<string>();
      for (const evt of traversalEvents) {
        if (evt.type !== "traversal" || !evt.node) continue;
        for (const id of graphIdsFromTraversalNode(evt.node)) {
          if (graphIdSet.has(id)) out.add(id);
        }
      }
      setVisibleTraversedIds(out);
      idBufferRef.current = [];
      if (drainTimerRef.current) {
        clearInterval(drainTimerRef.current);
        drainTimerRef.current = null;
      }
      lastEventCountRef.current = traversalEvents.length;
      return;
    }

    // Buffer any newly arrived events.
    const newEvents = traversalEvents.slice(lastEventCountRef.current);
    lastEventCountRef.current = traversalEvents.length;
    for (const evt of newEvents) {
      if (evt.type !== "traversal" || !evt.node) continue;
      const ids = graphIdsFromTraversalNode(evt.node).filter((id) => graphIdSet.has(id));
      if (ids.length) idBufferRef.current.push(ids);
    }

    // Start drain timer if not already running.
    if (!drainTimerRef.current) {
      drainTimerRef.current = setInterval(() => {
        const batch = idBufferRef.current.shift();
        if (batch) {
          setVisibleTraversedIds((prev) => {
            const next = new Set(prev);
            for (const id of batch) next.add(id);
            return next;
          });
        } else {
          clearInterval(drainTimerRef.current!);
          drainTimerRef.current = null;
        }
      }, STAGGER_MS);
    }
  }, [traversalEvents, isQuerying, isReplaying, graphIdSet]);

  // Reset when traversalEvents is cleared (new query).
  useEffect(() => {
    if (traversalEvents.length === 0) {
      setVisibleTraversedIds(new Set());
      idBufferRef.current = [];
      lastEventCountRef.current = 0;
      if (drainTimerRef.current) {
        clearInterval(drainTimerRef.current);
        drainTimerRef.current = null;
      }
    }
  }, [traversalEvents.length]);

  // Cleanup drain timer on unmount.
  useEffect(() => {
    return () => {
      if (drainTimerRef.current) clearInterval(drainTimerRef.current);
    };
  }, []);

  // During replay use replayNodes-derived set; otherwise use streaming-buffered set.
  const displayTraversedIds = isReplaying
    ? (replayTraversedIds ?? new Set<string>())
    : visibleTraversedIds;

  const allEdgeTypes = useMemo(() => {
    if (!graphData?.links.length) return [] as string[];
    const s = new Set<string>();
    for (const l of graphData.links) {
      if (l.type) s.add(l.type);
    }
    // Edge ordering: mirror the node-type legend order (Asset → File → Event → TimeSeries),
    // then keep the rest logical. `LINKED_TO` is a high-fanout bridge, so it always goes last.
    const EDGE_ORDER: Record<string, number> = {
      // Asset-structural
      HAS_COMPONENT: 10,
      IS_TYPE: 11,
      GOVERNED_BY: 12,
      // File-centric
      HAS_POLICY: 20,
      REFERENCES_AD: 21,
      // Event-centric
      IDENTIFIED_ON: 30,
      PERFORMED_ON: 31,
      // TimeSeries-centric
      HAS_TIMESERIES: 40,
      // Always last
      LINKED_TO: 99,
    };
    return Array.from(s).sort((a, b) => {
      const ra = EDGE_ORDER[a] ?? 50;
      const rb = EDGE_ORDER[b] ?? 50;
      if (ra !== rb) return ra - rb;
      return a.localeCompare(b);
    });
  }, [graphData?.links]);

  const stats = graphData?.stats;

  return (
    <div
      className={cn(
        "flex flex-1 min-h-0 flex-col overflow-hidden pb-6 relative",
        MAIN_TAB_CONTENT_FRAME,
        TAB_PAGE_TOP_INSET
      )}
    >
      {/* Tab→graph card ≈ AI chat: TAB_PAGE_TOP_INSET + chrome row + mb-1. Min-height offsets smaller mb-1 vs AI mb-3; items-end keeps stats flush above the card. */}
      <div className="shrink-0 mb-1 flex min-h-[34px] flex-wrap items-end justify-end gap-3 sm:min-h-[30px]">
        {stats && (
          <div className="flex items-center gap-3">
            {[
              { label: "Assets",     count: stats.assets,        icon: <Box className="w-3 h-3" aria-hidden />,        color: "text-blue-500"   },
              { label: "Files",      count: stats.files,         icon: <FileText className="w-3 h-3" aria-hidden />,   color: "text-purple-500" },
              { label: "Events",     count: stats.events,        icon: <Zap className="w-3 h-3" aria-hidden />,        color: "text-orange-500" },
              { label: "TimeSeries", count: stats.timeseries,    icon: <LineChart className="w-3 h-3" aria-hidden />,  color: "text-green-500"  },
              { label: "Relations",  count: stats.relationships, icon: <Share2 className="w-3 h-3" aria-hidden />,     color: "text-indigo-500" },
            ].map((s) => (
              <div key={s.label} className={`flex items-center gap-1.5 text-xs ${s.color}`}>
                {s.icon}
                <span className="font-semibold">{s.count}</span>
                <span className="text-slate-800 hidden sm:inline">{s.label}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Graph canvas */}
      <div
        ref={containerRef}
        className={cn("flex-1 min-h-[16rem] sm:min-h-[24rem] rounded-xl overflow-hidden relative", CARD_SURFACE_A)}
      >
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center text-slate-400">
            <div className="text-center">
              <Waypoints className="w-10 h-10 mb-3 animate-pulse mx-auto" />
              <p className="text-sm">Loading knowledge graph…</p>
            </div>
          </div>
        )}

        {error && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="flex flex-col items-center gap-3 text-center px-8">
              <AlertTriangle className="w-10 h-10 text-yellow-400" />
              <p className="text-sm text-slate-700">Could not load graph data</p>
              <p className="text-xs text-slate-400 font-mono max-w-sm">{error}</p>
            </div>
          </div>
        )}

        {!loading &&
          !error &&
          graphData &&
          viewport.width > 0 &&
          viewport.height > 0 && (
            <TraversalGraph
              ref={graphRef}
              active={active}
              data={graphData}
              traversedIds={displayTraversedIds}
              onNodeClick={setSelectedNode}
              width={viewport.width}
              height={viewport.height}
            />
          )}

        {graphData &&
          !loading &&
          !error &&
          viewport.width > 0 &&
          viewport.height > 0 && (
            <div className="absolute bottom-3 right-3 z-10 flex gap-2">
              <button
                type="button"
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white/90 px-2.5 py-1.5 text-xs text-slate-700 backdrop-blur-sm hover:border-slate-300 hover:bg-slate-100/90 focus:outline-none focus:border-[#304cb2]"
                title="Fit graph in view"
                aria-label="Recenter graph"
                onClick={() => graphRef.current?.recenter()}
              >
                <Crosshair className="h-3.5 w-3.5 shrink-0" aria-hidden />
                <span className="hidden sm:inline">Recenter</span>
              </button>
              <button
                type="button"
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white/90 px-2.5 py-1.5 text-xs text-slate-700 backdrop-blur-sm hover:border-slate-300 hover:bg-slate-100/90 focus:outline-none focus:border-[#304cb2]"
                title="Animate back to the default settled layout"
                aria-label="Reset graph layout"
                onClick={() => graphRef.current?.resetLayout()}
              >
                <RotateCcw className="h-3.5 w-3.5 shrink-0" aria-hidden />
                <span className="hidden sm:inline">Reset</span>
              </button>
            </div>
          )}

        {/* Legend overlay */}
        {graphData && !loading && (
          <div className={cn("absolute top-3 left-3 rounded-lg px-3 py-2 backdrop-blur-sm max-w-[220px] max-h-[min(70vh,520px)] overflow-y-auto bg-white/90 border-slate-200", CARD_SURFACE_B)}>
            <p className="text-xs font-semibold text-slate-500 mb-1.5 uppercase tracking-widest">
              Node types
            </p>
            <div className="space-y-1">
              {[
                { type: "Asset",      color: "#3b82f6" },
                { type: "File",       color: "#a855f7" },
                { type: "Event",      color: "#f97316" },
                { type: "TimeSeries", color: "#22c55e" },
              ].map((l) => (  // order: Asset → File → Event → TimeSeries
                <div key={l.type} className="flex items-center gap-2 text-xs text-slate-800">
                  <span
                    className="w-2.5 h-2.5 rounded-full shrink-0 border border-slate-300"
                    style={{ backgroundColor: l.color }}
                  />
                  {l.type}
                </div>
              ))}
            </div>
            {allEdgeTypes.length > 0 && (
              <>
                <p className="text-xs font-semibold text-slate-500 mb-1 mt-2 pt-2 border-t border-slate-200 uppercase tracking-widest">
                  Edge types
                </p>
                <div className="space-y-1">
                  {allEdgeTypes.map((t) => {
                    const sample = graphData.links.find((l: GraphLink) => l.type === t);
                    const swatch = sample?.color || "#666";
                    return (
                      <div key={t} className="flex items-center gap-2 text-xs text-slate-800">
                        <span className="w-6 h-0.5 shrink-0" style={{ backgroundColor: swatch }} />
                        <span className="truncate font-mono">{t}</span>
                      </div>
                    );
                  })}
                </div>
              </>
            )}
            {displayTraversedIds.size > 0 && (
              <div className="flex items-center gap-2 text-xs text-red-600 mt-1.5 border-t border-slate-200 pt-1.5 font-medium">
                <span className="w-2.5 h-2.5 rounded-full bg-red-500 shrink-0 ring-2 ring-red-200" />
                {displayTraversedIds.size} node{displayTraversedIds.size === 1 ? "" : "s"} traversed
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
