import { useEffect, useState, useMemo, useRef } from "react";
import {
  GitBranch,
  MessageSquare,
  X,
  Box,
  Activity,
  FileText,
  AlertTriangle,
} from "lucide-react";
import { api } from "../lib/api";
import { useStore } from "../lib/store";
import type { GraphData, GraphNode } from "../lib/types";
import TraversalGraph from "./TraversalGraph";
import QueryInterface from "./QueryInterface";

interface Props {
  active: boolean;
}

export default function KnowledgeGraph({ active }: Props) {
  const { demoMode, traversalEvents } = useStore();
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [chatOpen, setChatOpen] = useState(false);
  const [_selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(600);

  useEffect(() => {
    if (!active) return;
    setLoading(true);
    setError(null);
    api
      .graph()
      .then(setGraphData)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [active, demoMode]);

  // Measure available height for the graph canvas
  useEffect(() => {
    if (!containerRef.current) return;
    const update = () => {
      if (containerRef.current) {
        setHeight(containerRef.current.clientHeight);
      }
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, []);

  // Build set of traversed node IDs from the live Zustand traversal feed
  const traversedIds = useMemo<Set<string>>(() => {
    const ids = new Set<string>();
    for (const evt of traversalEvents) {
      if (evt.type === "traversal" && evt.node) {
        // node format: "Asset:ENGINE-1" — extract the id after the colon
        const colonIdx = evt.node.indexOf(":");
        if (colonIdx !== -1) ids.add(evt.node.slice(colonIdx + 1));
      }
    }
    return ids;
  }, [traversalEvents]);

  const stats = graphData?.stats;

  return (
    <div className="flex flex-col h-[calc(100vh-220px)] min-h-[500px] relative">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-wide flex items-center gap-2">
          <GitBranch className="w-4 h-4" />
          Knowledge Graph
        </h2>

        {stats && (
          <div className="flex items-center gap-3 ml-auto">
            {[
              { label: "Assets", count: stats.assets, icon: <Box className="w-3 h-3" />, color: "text-sky-400" },
              { label: "TimeSeries", count: stats.timeseries, icon: <Activity className="w-3 h-3" />, color: "text-emerald-400" },
              { label: "Files", count: stats.files, icon: <FileText className="w-3 h-3" />, color: "text-purple-400" },
              { label: "Relations", count: stats.relationships, icon: <GitBranch className="w-3 h-3" />, color: "text-violet-400" },
            ].map((s) => (
              <div key={s.label} className={`flex items-center gap-1.5 text-xs ${s.color}`}>
                {s.icon}
                <span className="font-semibold">{s.count}</span>
                <span className="text-zinc-600 hidden sm:inline">{s.label}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Graph canvas */}
      <div ref={containerRef} className="flex-1 bg-zinc-900 rounded-xl border border-zinc-800 overflow-hidden relative">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center text-zinc-600">
            <div className="text-center">
              <GitBranch className="w-10 h-10 mb-3 animate-pulse mx-auto" />
              <p className="text-sm">Loading knowledge graph…</p>
            </div>
          </div>
        )}

        {error && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="flex flex-col items-center gap-3 text-center px-8">
              <AlertTriangle className="w-10 h-10 text-yellow-400" />
              <p className="text-sm text-zinc-300">Could not load graph data</p>
              <p className="text-xs text-zinc-600 font-mono max-w-sm">{error}</p>
            </div>
          </div>
        )}

        {!loading && !error && graphData && (
          <TraversalGraph
            data={graphData}
            traversedIds={traversedIds}
            onNodeClick={setSelectedNode}
            height={height}
          />
        )}

        {/* Legend overlay */}
        {graphData && !loading && (
          <div className="absolute top-3 left-3 bg-zinc-900/90 border border-zinc-700 rounded-lg px-3 py-2 backdrop-blur-sm">
            <p className="text-xs font-medium text-zinc-500 mb-1.5 uppercase tracking-wide">
              Node types
            </p>
            <div className="space-y-1">
              {[
                { type: "Asset", color: "#38bdf8" },
                { type: "TimeSeries", color: "#4ade80" },
                { type: "File", color: "#c084fc" },
              ].map((l) => (
                <div key={l.type} className="flex items-center gap-2 text-xs text-zinc-400">
                  <span
                    className="w-2.5 h-2.5 rounded-full shrink-0"
                    style={{ backgroundColor: l.color }}
                  />
                  {l.type}
                </div>
              ))}
            </div>
            {traversedIds.size > 0 && (
              <div className="flex items-center gap-2 text-xs text-yellow-400 mt-1.5 border-t border-zinc-700 pt-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-yellow-400 shrink-0" />
                Traversed ({traversedIds.size})
              </div>
            )}
          </div>
        )}
      </div>

      {/* Floating chat button */}
      <button
        onClick={() => setChatOpen((v) => !v)}
        className="fixed bottom-6 right-6 w-12 h-12 bg-sky-600 hover:bg-sky-500 rounded-full
          shadow-lg flex items-center justify-center transition-colors z-40"
        title="Open AI assistant"
      >
        {chatOpen ? (
          <X className="w-5 h-5 text-white" />
        ) : (
          <MessageSquare className="w-5 h-5 text-white" />
        )}
      </button>

      {/* Chat overlay */}
      {chatOpen && (
        <div
          className="fixed right-4 bottom-20 w-96 bg-zinc-900 border border-zinc-700 rounded-2xl
            shadow-2xl overflow-hidden z-40 flex flex-col"
          style={{ height: "70vh" }}
        >
          <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-700 bg-zinc-900/90 backdrop-blur-sm">
            <div className="flex items-center gap-2">
              <MessageSquare className="w-4 h-4 text-sky-400" />
              <span className="text-sm font-semibold text-zinc-200">AI Assistant</span>
              <span className="text-xs text-zinc-600">· queries animate graph</span>
            </div>
            <button
              onClick={() => setChatOpen(false)}
              className="text-zinc-600 hover:text-zinc-300 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="flex-1 overflow-hidden">
            <QueryInterface apiKeyMissing={false} compact />
          </div>
        </div>
      )}
    </div>
  );
}
