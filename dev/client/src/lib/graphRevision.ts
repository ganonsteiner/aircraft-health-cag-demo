import type { GraphData } from "./types";

/** Stable fingerprint of graph topology for layout cache invalidation. */
export function graphDataRevision(data: GraphData): string {
  return `${data.nodes.length}:${data.links.map((l) => `${l.source}>${l.target}:${l.type}`).join("|")}`;
}
