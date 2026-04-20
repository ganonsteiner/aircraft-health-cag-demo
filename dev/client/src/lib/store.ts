/** Global Zustand store for the Southwest Airlines fleet demo. */

import { create } from "zustand";
import type { AgentEvent, ChatMessage, GraphData } from "./types";

/** Fully instrumented aircraft (all telemetry available). */
export const INSTRUMENTED_TAILS = ["N287WN", "N246WN", "N220WN", "N235WN"] as const;

/** All fleet tails — instrumented planes first, then placeholders. */
export const TAILS = [
  "N287WN", "N246WN", "N220WN", "N235WN",
  "N231WN", "N251WN", "N266WN", "N277WN", "N291WN",
] as const;

export type TailNumber = typeof TAILS[number];

/** Default tail used when a page needs a concrete aircraft but the user hasn't picked one yet. */
export const DEFAULT_TAIL: TailNumber = TAILS[0];

/** Map from tail number → airworthiness string (fetched once from /api/fleet). */
export type FleetStatusMap = Record<string, string>;

interface AppState {
  selectedAircraft: TailNumber | null;
  setSelectedAircraft: (tail: TailNumber | null) => void;

  fleetStatusMap: FleetStatusMap;
  setFleetStatusMap: (map: FleetStatusMap) => void;

  chatMessages: ChatMessage[];
  addChatMessage: (msg: ChatMessage) => void;
  /** Insert a message immediately before the message with `targetId` (e.g. status notice before the typing placeholder). */
  insertChatMessageBefore: (targetId: string, msg: ChatMessage) => void;
  updateChatMessage: (id: string, updates: Partial<ChatMessage>) => void;

  isQuerying: boolean;
  setIsQuerying: (v: boolean) => void;

  traversalEvents: AgentEvent[];
  appendTraversalEvent: (e: AgentEvent) => void;
  clearTraversalEvents: () => void;

  replayNodes: AgentEvent[];
  isReplaying: boolean;
  startReplay: (nodes: AgentEvent[]) => Promise<void>;

  floatingChatOpen: boolean;
  setFloatingChatOpen: (v: boolean) => void;
  toggleFloatingChat: () => void;

  graphDataSnapshot: GraphData | null;
  setGraphDataSnapshot: (d: GraphData | null) => void;
}

export const useStore = create<AppState>((set) => ({
  selectedAircraft: DEFAULT_TAIL,

  setSelectedAircraft: (tail) => set({ selectedAircraft: tail }),

  fleetStatusMap: {},
  setFleetStatusMap: (map) => set({ fleetStatusMap: map }),

  chatMessages: [],
  addChatMessage: (msg) =>
    set((s) => ({ chatMessages: [...s.chatMessages, msg] })),
  insertChatMessageBefore: (targetId, msg) =>
    set((s) => {
      const i = s.chatMessages.findIndex((m) => m.id === targetId);
      if (i < 0) return { chatMessages: [...s.chatMessages, msg] };
      return {
        chatMessages: [...s.chatMessages.slice(0, i), msg, ...s.chatMessages.slice(i)],
      };
    }),
  updateChatMessage: (id, updates) =>
    set((s) => ({
      chatMessages: s.chatMessages.map((m) =>
        m.id === id ? { ...m, ...updates } : m
      ),
    })),

  isQuerying: false,
  setIsQuerying: (v) => set({ isQuerying: v }),

  traversalEvents: [],
  appendTraversalEvent: (e) =>
    set((s) => ({ traversalEvents: [...s.traversalEvents, e] })),
  clearTraversalEvents: () => set({ traversalEvents: [] }),

  replayNodes: [],
  isReplaying: false,
  startReplay: async (nodes: AgentEvent[]) => {
    set({ replayNodes: [], isReplaying: true });
    for (const node of nodes) {
      await new Promise<void>((res) => setTimeout(res, 150));
      set((s) => ({ replayNodes: [...s.replayNodes, node] }));
    }
    set({ isReplaying: false });
  },

  floatingChatOpen: false,
  setFloatingChatOpen: (v) => set({ floatingChatOpen: v }),
  toggleFloatingChat: () =>
    set((s) => ({ floatingChatOpen: !s.floatingChatOpen })),

  graphDataSnapshot: null,
  setGraphDataSnapshot: (d) => set({ graphDataSnapshot: d }),
}));
