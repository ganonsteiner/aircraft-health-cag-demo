/**
 * TraversalGraph — shared force-directed knowledge graph visualization.
 *
 * Node fill colors are hardcoded below (Tailwind-400 palette).
 * Edge stroke colors are assigned server-side in `api.py` (`_EDGE_COLORS`).
 *
 * Lifecycle: this component stays mounted while data is available. The parent
 * passes `active` to pause/resume the RAF loop when the KG tab is hidden —
 * preserving node positions and camera without any serialize/restore cache.
 */

import {
  useRef,
  useEffect,
  useCallback,
  useState,
  useMemo,
  forwardRef,
  useImperativeHandle,
} from "react";
import ForceGraph2D from "react-force-graph-2d";
// eslint-disable-next-line @typescript-eslint/ban-ts-comment
// @ts-ignore — d3-force-3d is bundled by react-force-graph-2d; no @types package available
import { forceCollide, forceX, forceY } from "d3-force-3d";
import { graphDataRevision } from "../lib/graphRevision";
import type { GraphData, GraphLink, GraphNode } from "../lib/types";

/** Imperative controls for the knowledge graph canvas (reset layout, zoom-to-fit). */
export interface TraversalGraphHandle {
  /** Ease nodes from their current positions back to the default settled layout, then zoom-to-fit. */
  resetLayout: () => void;
  /** Fit current node positions in view without changing the simulation. */
  recenter: () => void;
}

// Palette tuned for the light canvas background. Medium-saturation -500 shades
// read clearly on white without looking heavy. Hues are spread across the color
// wheel so nothing blends together. The same values are mirrored in the stats
// row and the traversal panel so a color means the same thing everywhere.
const NODE_COLOR: Record<string, string> = {
  asset:       "#3b82f6",  // blue-500    — structural (aircraft, components)
  timeseries:  "#22c55e",  // green-500   — live sensor / telemetry
  event:       "#f97316",  // orange-500  — operational events (squawks, maintenance)
  file:        "#a855f7",  // purple-500  — documents, regulatory files, and policies
};

// Very low-alpha neutral — edges without a type-specific color recede into
// the background rather than adding clutter on the light canvas. Kept
// near-invisible so dense bundles (e.g. fleet-wide doc links) don't stack
// into a dark gray blob through the middle of the graph.
const DEFAULT_LINK = "rgba(148,163,184,0.3)";
// Red-500. Chosen as a hue far from every node color on the wheel
// (blue ~217°, green ~142°, orange ~24°, purple ~271°). Red at ~0° is
// at least ~80° from each, so a traversed-node ring reads clearly against
// any node type. A white separator ring is drawn underneath (see drawNode)
// so the red never shares an edge with the warm orange of Event nodes.
const HIGHLIGHT_COLOR = "#ef4444";

const ZOOM_PADDING_PX = 40;
const FINAL_ZOOM_MS = 320;
const RESIZE_ZOOM_MS = 220;
const RESIZE_DEBOUNCE_MS = 120;
const RESET_TWEEN_MS = 780;
const RESET_LAYOUT_EPS = 3;

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

/** Nudge the camera in place so the force-graph marks the canvas dirty (no layout reheat). */
function forceGraphRedraw(fg: { centerAt: (...args: unknown[]) => unknown } | null | undefined) {
  if (!fg?.centerAt) return;
  const c = fg.centerAt() as { x: number; y: number } | null | undefined;
  if (c && Number.isFinite(c.x) && Number.isFinite(c.y)) {
    fg.centerAt(c.x, c.y, 0);
  }
}

type SimNode = GraphNode & {
  x: number;
  y: number;
  vx?: number;
  vy?: number;
  fx?: number;
  fy?: number;
  /** Aircraft tail this node belongs to; null for shared/document/fleet nodes. */
  __cluster?: string | null;
};

function nodeRadius(node: GraphNode): number {
  const base = 6 + Math.min(10, node.linkCount ?? 0) * 1.4;
  return Math.max(7, Math.min(24, base));
}

/** Regex matches aircraft tail anywhere in an id (e.g. "N287WN", "MAINT-N287WN-...", "N287WN-ENGINE-1"). */
const TAIL_RE = /N\d{3,4}[A-Z]{1,2}/;

/** True if the id refers to the aircraft hub itself (tail with no suffix). */
const AIRCRAFT_HUB_RE = /^N\d{3,4}[A-Z]{1,2}$/;

/**
 * Build one gravity well per aircraft, arranged on a ring around origin.
 * Ring radius scales with fleet size so petals stay separated.
 */
function buildClusterCenters(data: GraphData): Map<string, { x: number; y: number }> {
  const tails = data.nodes
    .filter((n) => AIRCRAFT_HUB_RE.test(n.id))
    .map((n) => n.id)
    .sort();
  const centers = new Map<string, { x: number; y: number }>();
  const count = tails.length;
  if (count === 0) return centers;
  // Big enough that each petal (hub + 8–18 leaves) has breathing room.
  const R = Math.max(260, 120 + count * 36);
  tails.forEach((tail, i) => {
    const angle = (2 * Math.PI * i) / count - Math.PI / 2;
    centers.set(tail, { x: R * Math.cos(angle), y: R * Math.sin(angle) });
  });
  return centers;
}

/** Lookup an id's cluster tail, or null for shared/document nodes. */
function clusterForId(id: string, centers: Map<string, { x: number; y: number }>): string | null {
  const m = id.match(TAIL_RE);
  if (m && centers.has(m[0])) return m[0];
  return null;
}

/**
 * Seed nodes inside their cluster petal (aircraft hub at center, leaves scattered
 * within a small radius). Shared nodes are placed on an inner ring around the
 * origin so they form a visible "shared documents" zone rather than piling up
 * in a single knot. Placing each node close to its eventual position
 * dramatically reduces convergence jitter.
 */
function graphDataWithCenteredSeed(
  data: GraphData,
  centers: Map<string, { x: number; y: number }>
): GraphData {
  const sharedIndexById = new Map<string, number>();
  let sharedCount = 0;
  for (const n of data.nodes) {
    if (clusterForId(n.id, centers) === null) {
      sharedIndexById.set(n.id, sharedCount++);
    }
  }
  const R_SHARED = Math.max(110, 60 + sharedCount * 6);

  const nodes = data.nodes.map((node, i) => {
    const cluster = clusterForId(node.id, centers);
    if (cluster === null) {
      const si = sharedIndexById.get(node.id) ?? 0;
      const angle = (2 * Math.PI * si) / Math.max(sharedCount, 1) - Math.PI / 2;
      const jitter = ((si * 2654435761) % 1000) / 1000 - 0.5;
      const r = R_SHARED * (0.85 + 0.3 * jitter);
      const x = r * Math.cos(angle);
      const y = r * Math.sin(angle);
      return {
        ...node,
        __cluster: null as string | null,
        __seedX: x,
        __seedY: y,
        x,
        y,
      };
    }
    const c = centers.get(cluster)!;
    const isHub = node.id === cluster;
    const angle = i * 2.39996;
    const r = isHub ? 0 : 55 + (i % 6) * 8;
    return {
      ...node,
      __cluster: cluster,
      x: c.x + r * Math.cos(angle),
      y: c.y + r * Math.sin(angle),
    };
  });
  return {
    ...data,
    nodes,
    links: data.links.map((l) => ({ ...l })),
  };
}

interface SelectedNode extends GraphNode {
  x?: number;
  y?: number;
}

interface Props {
  /** False when the KG tab is in the background — pauses the canvas loop without resetting layout. */
  active?: boolean;
  data: GraphData;
  traversedIds?: Set<string>;
  onNodeClick?: (node: GraphNode) => void;
  /** Viewport width in px; must be > 0 before mount. */
  width: number;
  /** Viewport height in px; must be > 0 before mount. */
  height: number;
}

const TraversalGraph = forwardRef<TraversalGraphHandle, Props>(function TraversalGraph(
  { active = true, data, traversedIds = new Set(), onNodeClick, width, height },
  ref
) {
  const fgRef = useRef<any>(null);
  const [selectedNode, setSelectedNode] = useState<SelectedNode | null>(null);
  const hasInitialFitRef = useRef(false);
  const revisionRef = useRef<string>("");
  const resizeDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevViewportRef = useRef<{ w: number; h: number }>({ w: 0, h: 0 });
  /** Node positions after the first layout settle for this graph revision (the "default" layout). */
  const defaultPositionsRef = useRef<Map<string, { x: number; y: number }>>(new Map());
  const resetTweenRafRef = useRef<number | null>(null);
  const snapshotRafRef = useRef<number | null>(null);
  /** Bumped on graph revision so deferred layout snapshots never overwrite a newer graph. */
  const layoutEpochRef = useRef(0);

  const clusterCenters = useMemo(() => buildClusterCenters(data), [data]);

  const seededData = useMemo(
    () => graphDataWithCenteredSeed(data, clusterCenters),
    [data, clusterCenters]
  );

  const revision = useMemo(() => graphDataRevision(data), [data]);

  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;

    // Per-node charge: leaves (deg ~1) repel lightly; hubs repel harder so
    // neighbors within a petal don't pile up. Shared nodes (documents,
    // policies, fleet owner, engine model) get an extra repulsion kicker so
    // they spread across the middle zone rather than clumping.
    fg.d3Force("charge")
      ?.strength((n: GraphNode) => {
        const deg = n.linkCount ?? 1;
        const hub = Math.min(25, deg) * 18;
        const sharedBonus = (n as SimNode).__cluster ? 0 : 180;
        return -(70 + hub + sharedBonus);
      })
      .distanceMin(8)
      .distanceMax(320);

    // Link distance: short for intra-cluster (leaf hugging parent), long for
    // cross-cluster / shared-to-cluster (so shared docs don't pull petals in).
    // Link strength: intra-cluster uses d3's inverse-degree default (firm for
    // leaves); cross-cluster is near zero so petals stay separated.
    fg.d3Force("link")
      ?.distance((l: any) => {
        const s = typeof l.source === "object" ? l.source : null;
        const t = typeof l.target === "object" ? l.target : null;
        const sc = (s as SimNode | null)?.__cluster ?? null;
        const tc = (t as SimNode | null)?.__cluster ?? null;
        if (sc && tc && sc === tc) return 42;
        return 180;
      })
      .strength((l: any) => {
        const s = typeof l.source === "object" ? l.source : null;
        const t = typeof l.target === "object" ? l.target : null;
        const sc = (s as SimNode | null)?.__cluster ?? null;
        const tc = (t as SimNode | null)?.__cluster ?? null;
        if (sc && tc && sc !== tc) return 0.02;
        if (!sc || !tc) return 0.04;
        const minDeg = Math.min(s?.linkCount ?? 1, t?.linkCount ?? 1);
        return 1 / Math.max(1, minDeg);
      });

    fg.d3Force(
      "collide",
      forceCollide((n: GraphNode) => {
        const deg = n.linkCount ?? 0;
        const sharedPad = (n as SimNode).__cluster ? 0 : 10;
        return nodeRadius(n) + 6 + Math.min(18, deg) * 1.2 + sharedPad;
      }).strength(1)
    );

    // Cluster gravity:
    //   - Clustered leaves are pulled to their aircraft's ring position.
    //   - Shared nodes are pulled to their SEED position on the inner ring
    //     (not (0,0)), so they hold their fan-out and don't collapse inward.
    const clusterX = (n: any) => {
      const sn = n as SimNode;
      if (sn.__cluster) return clusterCenters.get(sn.__cluster)!.x;
      // Seed x is set on initial mount and preserved through the sim by d3.
      return Number.isFinite((sn as any).__seedX) ? (sn as any).__seedX : sn.x ?? 0;
    };
    const clusterY = (n: any) => {
      const sn = n as SimNode;
      if (sn.__cluster) return clusterCenters.get(sn.__cluster)!.y;
      return Number.isFinite((sn as any).__seedY) ? (sn as any).__seedY : sn.y ?? 0;
    };
    const clusterStrength = (n: any) => ((n as SimNode).__cluster ? 0.22 : 0.04);

    fg.d3Force("x", forceX(clusterX).strength(clusterStrength));
    fg.d3Force("y", forceY(clusterY).strength(clusterStrength));
  }, [clusterCenters]);

  useEffect(() => {
    if (revision === revisionRef.current) return;
    revisionRef.current = revision;
    layoutEpochRef.current += 1;
    hasInitialFitRef.current = false;
    defaultPositionsRef.current = new Map();
    if (snapshotRafRef.current != null) {
      cancelAnimationFrame(snapshotRafRef.current);
      snapshotRafRef.current = null;
    }
  }, [revision]);

  const runZoomToFit = useCallback((durationMs: number) => {
    const fg = fgRef.current;
    if (!fg || data.nodes.length === 0) return;
    fg.zoomToFit(durationMs, ZOOM_PADDING_PX);
  }, [data.nodes.length]);

  const captureDefaultLayout = useCallback(() => {
    const m = new Map<string, { x: number; y: number }>();
    for (const n of seededData.nodes) {
      const nn = n as SimNode;
      if (Number.isFinite(nn.x) && Number.isFinite(nn.y)) {
        m.set(n.id, { x: nn.x, y: nn.y });
      }
    }
    return m;
  }, [seededData]);

  const onEngineStop = useCallback(() => {
    if (data.nodes.length === 0) return;
    if (!hasInitialFitRef.current) {
      hasInitialFitRef.current = true;
      defaultPositionsRef.current = captureDefaultLayout();
      runZoomToFit(FINAL_ZOOM_MS);
      if (snapshotRafRef.current != null) cancelAnimationFrame(snapshotRafRef.current);
      const epoch = layoutEpochRef.current;
      snapshotRafRef.current = requestAnimationFrame(() => {
        snapshotRafRef.current = requestAnimationFrame(() => {
          snapshotRafRef.current = null;
          if (epoch !== layoutEpochRef.current) return;
          defaultPositionsRef.current = captureDefaultLayout();
        });
      });
    }
  }, [data.nodes.length, runZoomToFit, captureDefaultLayout]);

  /** Pause RAF while tab hidden (saves work); resume when visible so zoom/pan still redraw. */
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;
    if (active) fg.resumeAnimation?.();
    else fg.pauseAnimation?.();
  }, [active]);

  const resetLayout = useCallback(() => {
    if (data.nodes.length === 0) return;
    if (resetTweenRafRef.current != null) {
      cancelAnimationFrame(resetTweenRafRef.current);
      resetTweenRafRef.current = null;
    }
    setSelectedNode(null);

    const targets = defaultPositionsRef.current;
    const fg = fgRef.current;

    const releasePinsZeroVelocity = () => {
      for (const n of seededData.nodes) {
        const node = n as SimNode;
        delete node.fx;
        delete node.fy;
        node.vx = 0;
        node.vy = 0;
      }
    };

    if (targets.size === 0) {
      releasePinsZeroVelocity();
      hasInitialFitRef.current = false;
      fg?.d3ReheatSimulation?.();
      return;
    }

    let maxDelta = 0;
    for (const n of seededData.nodes) {
      const end = targets.get(n.id);
      if (!end) continue;
      const nn = n as SimNode;
      if (!Number.isFinite(nn.x) || !Number.isFinite(nn.y)) continue;
      const d = Math.hypot(nn.x - end.x, nn.y - end.y);
      if (d > maxDelta) maxDelta = d;
    }

    if (maxDelta <= RESET_LAYOUT_EPS) {
      releasePinsZeroVelocity();
      return;
    }

    const starts = new Map<string, { x: number; y: number }>();
    for (const n of seededData.nodes) {
      const end = targets.get(n.id);
      if (!end) continue;
      const nn = n as SimNode;
      if (Number.isFinite(nn.x) && Number.isFinite(nn.y)) {
        starts.set(n.id, { x: nn.x, y: nn.y });
      }
    }

    for (const n of seededData.nodes) {
      const nn = n as SimNode;
      if (!Number.isFinite(nn.x) || !Number.isFinite(nn.y)) continue;
      const s0 = starts.get(n.id);
      nn.fx = s0 ? s0.x : nn.x;
      nn.fy = s0 ? s0.y : nn.y;
      nn.vx = 0;
      nn.vy = 0;
    }

    fg?.resumeAnimation?.();

    const t0 = performance.now();
    const step = () => {
      const elapsed = performance.now() - t0;
      const t = Math.min(1, elapsed / RESET_TWEEN_MS);
      const e = easeOutCubic(t);

      for (const n of seededData.nodes) {
        const end = targets.get(n.id);
        const s0 = starts.get(n.id);
        if (!end || !s0) continue;
        const node = n as SimNode;
        const ix = s0.x + (end.x - s0.x) * e;
        const iy = s0.y + (end.y - s0.y) * e;
        node.fx = ix;
        node.fy = iy;
        // Update render coords directly — the canvas reads x/y, not fx/fy.
        // D3 only copies fx→x during a simulation tick; if the simulation has
        // stopped (cooldown exhausted), x/y must be set here to avoid a freeze.
        node.x = ix;
        node.y = iy;
      }

      forceGraphRedraw(fgRef.current);

      if (t < 1) {
        resetTweenRafRef.current = requestAnimationFrame(step);
      } else {
        resetTweenRafRef.current = null;
        for (const n of seededData.nodes) {
          const end = targets.get(n.id);
          if (!end) continue;
          const node = n as SimNode;
          node.x = end.x;
          node.y = end.y;
          delete node.fx;
          delete node.fy;
          node.vx = 0;
          node.vy = 0;
        }
        runZoomToFit(FINAL_ZOOM_MS);
      }
    };
    resetTweenRafRef.current = requestAnimationFrame(step);
  }, [data.nodes.length, seededData, runZoomToFit]);

  useEffect(() => {
    return () => {
      if (resetTweenRafRef.current != null) {
        cancelAnimationFrame(resetTweenRafRef.current);
        resetTweenRafRef.current = null;
      }
      if (snapshotRafRef.current != null) {
        cancelAnimationFrame(snapshotRafRef.current);
        snapshotRafRef.current = null;
      }
    };
  }, []);

  useImperativeHandle(
    ref,
    () => ({
      resetLayout,
      recenter: () => runZoomToFit(FINAL_ZOOM_MS),
    }),
    [resetLayout, runZoomToFit]
  );

  useEffect(() => {
    if (width <= 0 || height <= 0) return;
    const prev = prevViewportRef.current;
    const isFirstSize = prev.w === 0 && prev.h === 0;
    prevViewportRef.current = { w: width, h: height };
    if (isFirstSize) return;

    if (resizeDebounceRef.current) clearTimeout(resizeDebounceRef.current);
    resizeDebounceRef.current = setTimeout(() => {
      resizeDebounceRef.current = null;
      if (!fgRef.current || !hasInitialFitRef.current) return;
      runZoomToFit(RESIZE_ZOOM_MS);
    }, RESIZE_DEBOUNCE_MS);
    return () => {
      if (resizeDebounceRef.current) clearTimeout(resizeDebounceRef.current);
    };
  }, [width, height, runZoomToFit]);

  const drawNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const gNode = node as SimNode;
      if (!Number.isFinite(gNode.x) || !Number.isFinite(gNode.y)) return;
      const r = nodeRadius(gNode);
      const isHighlighted = traversedIds.has(gNode.id);
      const isSelected = selectedNode?.id === gNode.id;

      // Fill
      ctx.beginPath();
      ctx.arc(gNode.x, gNode.y, r, 0, 2 * Math.PI);
      ctx.fillStyle = NODE_COLOR[gNode.type] || "#71717a";
      ctx.globalAlpha = isHighlighted ? 1 : 0.85;
      ctx.fill();
      ctx.globalAlpha = 1;

      // Highlight: soft red halo → white separator → thick red stroke.
      // The white ring breaks contact between the node fill and the red
      // stroke, so the highlight reads clearly even when it sits on top
      // of a warm-hued node (e.g. orange Event).
      if (isHighlighted || isSelected) {
        // Outer glow halo
        ctx.beginPath();
        ctx.arc(gNode.x, gNode.y, r + 7, 0, 2 * Math.PI);
        ctx.fillStyle = isSelected ? "rgba(239,68,68,0.32)" : "rgba(239,68,68,0.22)";
        ctx.fill();
        // White separator ring (draws over node fill, under colored stroke)
        ctx.beginPath();
        ctx.arc(gNode.x, gNode.y, r + 3.5, 0, 2 * Math.PI);
        ctx.strokeStyle = "#ffffff";
        ctx.lineWidth = 2.5;
        ctx.stroke();
        // Colored traversal stroke
        ctx.beginPath();
        ctx.arc(gNode.x, gNode.y, r + 5, 0, 2 * Math.PI);
        ctx.strokeStyle = HIGHLIGHT_COLOR;
        ctx.lineWidth = 3;
        ctx.stroke();
      }

      // Label: always show aircraft hubs (tail-only ids) and other big hubs;
      // show smaller nodes only when zoomed in.
      const gs = Number.isFinite(globalScale) && globalScale > 1e-6 ? globalScale : 1;
      const isAircraftHub = AIRCRAFT_HUB_RE.test(gNode.id);
      const isSouthwestNode =
        gNode.id === "Southwest Airlines" || (gNode.label || "").trim() === "Southwest Airlines";
      const showLabel = isAircraftHub || isSouthwestNode || gs > 2.2 || r >= 18;
      if (showLabel) {
        const fontSize = isAircraftHub || isSouthwestNode
          ? Math.max(11 / gs, 4)
          : 10 / gs;
        const rawLabel = isAircraftHub ? gNode.id : gNode.label;
        const label = rawLabel.length > 18 ? rawLabel.slice(0, 16) + "…" : rawLabel;
        ctx.font = `${isAircraftHub || isSouthwestNode ? "600 " : ""}${fontSize}px ui-sans-serif, system-ui, sans-serif`;
        if (isAircraftHub || isSouthwestNode) {
          const pad = 3 / gs;
          const metrics = ctx.measureText(label);
          const w = metrics.width + pad * 2;
          const h = fontSize + pad * 2;
          ctx.fillStyle = "rgba(255,255,255,0.92)";
          ctx.fillRect(gNode.x - w / 2, gNode.y + r + fontSize * 0.3, w, h);
          ctx.fillStyle = "rgba(15,23,42,0.95)";
        } else {
          ctx.fillStyle = "rgba(15,23,42,0.85)";
        }
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillText(label, gNode.x, gNode.y + r + fontSize * 0.5);
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

  const linkColor = useCallback((link: GraphLink) => (link as GraphLink).color || DEFAULT_LINK, []);

  const linkWidth = useCallback(() => 1.5, []);

  return (
    <div className="relative h-full w-full" style={{ width, height }}>
      <ForceGraph2D
        ref={fgRef}
        graphData={seededData as any}
        width={width}
        height={height}
        backgroundColor="#f8fafc"
        nodeCanvasObject={drawNode}
        nodeCanvasObjectMode={() => "replace"}
        linkColor={linkColor as any}
        linkWidth={linkWidth as any}
        linkDirectionalParticles={1}
        linkDirectionalParticleWidth={2}
        linkDirectionalParticleSpeed={0.004}
        linkDirectionalParticleColor={linkColor as any}
        onNodeClick={handleNodeClick}
        onEngineStop={onEngineStop}
        cooldownTicks={400}
        d3AlphaDecay={0.015}
        d3VelocityDecay={0.45}
      />

      {selectedNode && (
        <div className="absolute top-3 right-3 bg-white/95 border border-slate-200 rounded-xl p-4 max-w-xs text-xs shadow-xl backdrop-blur-sm">
          <div className="flex items-center gap-2 mb-2">
            <span
              className="w-2.5 h-2.5 rounded-full shrink-0"
              style={{ backgroundColor: NODE_COLOR[selectedNode.type] || "#71717a" }}
            />
            <span className="font-semibold text-slate-900 truncate">{selectedNode.label}</span>
            <button
              className="ml-auto text-slate-400 hover:text-slate-700 shrink-0"
              onClick={() => setSelectedNode(null)}
            >
              ×
            </button>
          </div>
          <div className="space-y-1 text-slate-500">
            <div className="flex gap-2">
              <span className="text-slate-400 w-14 shrink-0">Type</span>
              <span className="capitalize">{selectedNode.type}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-slate-400 w-14 shrink-0">ID</span>
              <span className="font-mono truncate text-slate-700">{selectedNode.id}</span>
            </div>
            <div className="flex gap-2">
              <span className="text-slate-400 w-14 shrink-0">Links</span>
              <span>{selectedNode.linkCount ?? 0}</span>
            </div>
            {selectedNode.unit && (
              <div className="flex gap-2">
                <span className="text-slate-400 w-14 shrink-0">Unit</span>
                <span>{selectedNode.unit}</span>
              </div>
            )}
            {selectedNode.metadata &&
              Object.entries(selectedNode.metadata).slice(0, 4).map(([k, v]) => (
                <div key={k} className="flex gap-2">
                  <span className="text-slate-400 w-14 shrink-0 truncate">{k}</span>
                  <span className="truncate">{String(v).slice(0, 40)}</span>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
});

TraversalGraph.displayName = "TraversalGraph";

export default TraversalGraph;
