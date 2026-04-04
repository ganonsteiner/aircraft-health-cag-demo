import type {
  HealthStatus,
  AircraftStatus,
  Squawk,
  MaintenanceItem,
  MaintenanceHistoryPage,
  FlightHistoryPage,
  ComponentNode,
  GraphData,
  DemoMode,
} from "./types";

const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => get<HealthStatus>("/health"),
  status: () => get<AircraftStatus>("/status"),
  squawks: () => get<Squawk[]>("/squawks"),
  upcomingMaintenance: () => get<MaintenanceItem[]>("/maintenance/upcoming"),

  maintenanceHistory: (opts: { page?: number; per_page?: number; component?: string; year?: number } = {}) => {
    const params = new URLSearchParams();
    if (opts.page) params.set("page", String(opts.page));
    if (opts.per_page) params.set("per_page", String(opts.per_page));
    if (opts.component) params.set("component", opts.component);
    if (opts.year) params.set("year", String(opts.year));
    return get<MaintenanceHistoryPage>(`/maintenance/history?${params}`);
  },

  flights: (opts: { page?: number; per_page?: number; route?: string; year?: number } = {}) => {
    const params = new URLSearchParams();
    if (opts.page) params.set("page", String(opts.page));
    if (opts.per_page) params.set("per_page", String(opts.per_page));
    if (opts.route) params.set("route", opts.route);
    if (opts.year) params.set("year", String(opts.year));
    return get<FlightHistoryPage>(`/flights?${params}`);
  },

  components: () => get<ComponentNode[]>("/components"),

  graph: () => get<GraphData>("/graph"),

  setDemoState: (state: DemoMode) =>
    post<{ status: string; active_state: string }>("/demo-state", { state }),
};
