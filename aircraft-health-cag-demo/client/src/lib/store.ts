/**
 * Global Zustand store for the aircraft health demo app.
 *
 * Manages:
 *   - demoMode: active demo state (clean / caution / grounded)
 *   - chatMessages: full conversation history, persisted across tab changes
 *   - isQuerying: whether the agent is currently streaming a response
 *   - traversalNodes: CDF graph nodes traversed by the most recent query
 *   - replayNodes: subset of traversal nodes used for replay animation
 *
 * The demoMode setter calls POST /api/demo-state on the backend so the mock
 * CDF server switches its active event/datapoint store before any subsequent
 * queries are made.
 */

import { create } from "zustand";
import type { AgentEvent, ChatMessage } from "./types";

export type DemoMode = "clean" | "caution" | "grounded";

interface AppState {
  // Demo mode
  demoMode: DemoMode;
  setDemoMode: (mode: DemoMode) => Promise<void>;

  // Chat state — persists across tab navigation
  chatMessages: ChatMessage[];
  addChatMessage: (msg: ChatMessage) => void;
  updateChatMessage: (id: string, updates: Partial<ChatMessage>) => void;
  clearChat: () => void;

  // Query state
  isQuerying: boolean;
  setIsQuerying: (v: boolean) => void;

  // Graph traversal — current live session
  traversalEvents: AgentEvent[];
  appendTraversalEvent: (e: AgentEvent) => void;
  clearTraversalEvents: () => void;

  // Replay state
  replayNodes: AgentEvent[];
  isReplaying: boolean;
  startReplay: (nodes: AgentEvent[]) => Promise<void>;

  // Graph expanded mode on QueryInterface
  graphExpanded: boolean;
  setGraphExpanded: (v: boolean) => void;

  // Refresh trigger: increment to signal data-fetching components to refresh
  refreshKey: number;
  triggerRefresh: () => void;
}

export const useStore = create<AppState>((set, get) => ({
  demoMode: "clean",

  setDemoMode: async (mode: DemoMode) => {
    // Tell the backend to switch its active data store BEFORE updating local
    // state. If we update Zustand first, components immediately re-fetch and
    // receive stale data because the mock CDF server hasn't switched yet.
    try {
      await fetch("/api/demo-state", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ state: mode }),
      });
    } catch {
      // Non-fatal — proceed with the local switch regardless
    }
    get().clearChat();
    set({ demoMode: mode });
    get().triggerRefresh();
  },

  chatMessages: [],
  addChatMessage: (msg) =>
    set((s) => ({ chatMessages: [...s.chatMessages, msg] })),
  updateChatMessage: (id, updates) =>
    set((s) => ({
      chatMessages: s.chatMessages.map((m) =>
        m.id === id ? { ...m, ...updates } : m
      ),
    })),
  clearChat: () => set({ chatMessages: [], traversalEvents: [] }),

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
      await new Promise<void>((res) => setTimeout(res, 300));
      set((s) => ({ replayNodes: [...s.replayNodes, node] }));
    }
    set({ isReplaying: false });
  },

  graphExpanded: false,
  setGraphExpanded: (v) => set({ graphExpanded: v }),

  refreshKey: 0,
  triggerRefresh: () => set((s) => ({ refreshKey: s.refreshKey + 1 })),
}));
