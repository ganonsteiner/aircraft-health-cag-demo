/**
 * TraversalGraph — shared force-directed knowledge graph visualization.
 *
 * Used by:
 *   - KnowledgeGraph tab (full-width, static graph of all CDF nodes)
 *   - QueryInterface inline expanded view (same graph, traversed nodes highlighted live)
 *
 * Node types map to CDF resource types (same color scheme as GraphTraversalPanel):
 *   asset      → #38bdf8  (sky-400)
 *   timeseries → #4ade80  (green-400)
 *   event      → #fb923c  (orange-400)
 *   file       → #c084fc  (purple-400)
 *
 * Node radius proportional to linkCount (min 4, max 14).
 * Highlighted nodes get a glowing ring when their id appears in traversedIds.
 */

import { useRef, useEffect, useCallback, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";
import type { GraphData, GraphNode } from "../lib/types";

const NODE_COLOR: Record<string, string> = {
  asset: "#38bdf8",
  timeseries: "#4ade80",
  event: "#fb923c",
  file: "#c084fc",
};

const LINK_COLOR = "rgba(113,113,122,0.3)"; // zinc-500/30
const HIGHLIGHT_COLOR = "#facc15"; // yellow-400 glow for traversed nodes

function nodeRadius(node: GraphNode): number {
  const base = 3 + Math.min(10, node.linkCount ?? 0) * 0.8;
  return Math.max(4, Math.min(14, base));
}

interface SelectedNode extends GraphNode {
  x?: number;
  y?: number;
}

interface Props {
  data: GraphData;
  traversedIds?: Set<string>;
  onNodeClick?: (node: GraphNode) => void;
  height?: number;
}

export default function TraversalGraph({
  data,
  traversedIds = new Set(),
  onNodeClick,
  height = 600,
}: Props) {
  const fgRef = useRef<any>(null);
  const [selectedNode, setSelectedNode] = useState<SelectedNode | null>(null);

  // Auto-fit after data loads
  useEffect(() => {
    if (fgRef.current && data.nodes.length > 0) {
      setTimeout(() => {
        fgRef.current?.zoomToFit(400, 40);
      }, 500);
    }
  }, [data.nodes.length]);

  const drawNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const gNode = node as GraphNode & { x: number; y: number };
      const r = nodeRadius(gNode);
      const isHighlighted = traversedIds.has(gNode.id);
      const isSelected = selectedNode?.id === gNode.id;

      // Glow ring for traversed / selected nodes
      if (isHighlighted || isSelected) {
        ctx.beginPath();
        ctx.arc(gNode.x, gNode.y, r + 3, 0, 2 * Math.PI);
        ctx.fillStyle = isSelected ? "rgba(250,204,21,0.25)" : "rgba(250,204,21,0.15)";
        ctx.fill();
        ctx.strokeStyle = HIGHLIGHT_COLOR;
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      // Node circle
      ctx.beginPath();
      ctx.arc(gNode.x, gNode.y, r, 0, 2 * Math.PI);
      ctx.fillStyle = NODE_COLOR[gNode.type] || "#71717a";
      ctx.globalAlpha = isHighlighted ? 1 : 0.75;
      ctx.fill();
      ctx.globalAlpha = 1;

      // Label — only at sufficient zoom or for large nodes
      const fontSize = 10 / globalScale;
      if (globalScale > 1.5 || r >= 10) {
        const label = gNode.label.length > 16 ? gNode.label.slice(0, 14) + "…" : gNode.label;
        ctx.font = `${fontSize}px monospace`;
        ctx.fillStyle = "rgba(255,255,255,0.8)";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(label, gNode.x, gNode.y + r + fontSize * 0.8);
      }
    },
    [traversedIds, selectedNode]
  );

  const handleNodeClick = useCallback(
    (node: any) => {
      setSelectedNode((prev) => (prev?.id === node.id ? null : node));
      onNodeClick?.(node as GraphNode);
    },
    [onNodeClick]
  );

  return (
    <div className="relative w-full" style={{ height }}>
      <ForceGraph2D
        ref={fgRef}
        graphData={data as any}
        width={undefined}
        height={height}
        backgroundColor="#09090b" // zinc-950
        nodeCanvasObject={drawNode}
        nodeCanvasObjectMode={() => "replace"}
        linkColor={() => LINK_COLOR}
        linkWidth={0.5}
        linkDirectionalParticles={2}
        linkDirectionalParticleWidth={1}
        linkDirectionalParticleColor={() => "rgba(113,113,122,0.5)"}
        onNodeClick={handleNodeClick}
        cooldownTicks={100}
        d3AlphaDecay={0.03}
        d3VelocityDecay={0.3}
      />

      {/* Selected node info panel */}
      {selectedNode && (
        <div className="absolute top-3 right-3 bg-zinc-900/95 border border-zinc-700 rounded-xl p-4 max-w-xs text-xs shadow-xl backdrop-blur-sm">
          <div className="flex items-center gap-2 mb-2">
            <span
              className="w-2.5 h-2.5 rounded-full shrink-0"
              style={{ backgroundColor: NODE_COLOR[selectedNode.type] || "#71717a" }}
            />
            <span className="font-semibold text-zinc-100 truncate">{selectedNode.label}</span>
            <button
              className="ml-auto text-zinc-600 hover:text-zinc-300 shrink-0"
              onClick={() => setSelectedNode(null)}
            >
              ×
            </button>
          </div>
          <div className="space-y-1 text-zinc-400">
            <div className="flex gap-2">
              <span className="text-zinc-600 w-14 shrink-0">Type</span>
              <span className="capitalize">{selectedNode.type}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-zinc-600 w-14 shrink-0">ID</span>
              <span className="font-mono truncate text-zinc-300">{selectedNode.id}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-zinc-600 w-14 shrink-0">Links</span>
              <span>{selectedNode.linkCount ?? 0}</span>
            </div>
            {selectedNode.unit && (
              <div className="flex gap-2">
                <span className="text-zinc-600 w-14 shrink-0">Unit</span>
                <span>{selectedNode.unit}</span>
              </div>
            )}
            {selectedNode.metadata &&
              Object.entries(selectedNode.metadata).slice(0, 4).map(([k, v]) => (
                <div key={k} className="flex gap-2">
                  <span className="text-zinc-600 w-14 shrink-0 truncate">{k}</span>
                  <span className="truncate">{String(v).slice(0, 40)}</span>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
