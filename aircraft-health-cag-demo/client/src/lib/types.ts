export type DemoMode = "clean" | "caution" | "grounded";

export interface HealthStatus {
  status: "ok" | "degraded" | "mock_cdf_offline" | "api_key_missing" | "api_key_invalid";
  anthropic_api_key_configured: boolean;
  mock_cdf_reachable: boolean;
  store: Record<string, number>;
  checkedAt: string;
}

export interface AircraftStatus {
  hobbs: number;
  tach: number;
  engineSMOH: number;
  engineTBO: number;
  engineSMOHPercent: number;
  annualDueDate: string;
  annualDaysRemaining: number | null;
  openSquawkCount: number;
  groundingSquawkCount: number;
  isAirworthy: boolean;
  oilHoursOverdue?: number;
  lastMaintenanceDate: string | null;
  dataFreshAt: string;
}

export interface Squawk {
  externalId: string;
  description: string;
  component: string;
  severity: "grounding" | "non-grounding" | "cosmetic" | string;
  status: "open" | "resolved" | "deferred" | string;
  dateIdentified: string;
  metadata: Record<string, string>;
}

export interface MaintenanceItem {
  component: string;
  description: string;
  maintenanceType: string;
  nextDueHobbs: number;
  hoursUntilDue: number;
  isOverdue: boolean;
  nextDueDate: string | null;
  daysUntilDue: number | null;
}

export interface MaintenanceRecord {
  externalId: string;
  type: string;
  subtype: string;
  description: string;
  startTime: number | null;
  metadata: Record<string, string>;
}

export interface MaintenanceHistoryPage {
  records: MaintenanceRecord[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface FlightRecord {
  timestamp: string;
  hobbs_start: number;
  hobbs_end: number;
  duration: number;
  cht_max: number | null;
  egt_max: number | null;
  oil_pressure_min: number | null;
  oil_pressure_max: number | null;
  oil_temp_max: number | null;
  fuel_used_gal: number | null;
  year: number;
}

export interface FlightHistoryPage {
  records: FlightRecord[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface ComponentNode {
  externalId: string;
  name: string;
  description: string | null;
  parentExternalId: string | null;
  metadata: Record<string, string>;
  lastMaintenanceDate: string | null;
  nextDueHobbs: number | null;
  nextDueDate: string | null;
  currentHobbs: number;
  hoursUntilDue: number | null;
  status: "ok" | "due_soon" | "overdue";
  maintenanceCount: number;
}

export interface GraphNode {
  id: string;
  label: string;
  type: "asset" | "timeseries" | "event" | "file";
  group: number;
  linkCount: number;
  unit?: string;
  metadata?: Record<string, string>;
}

export interface GraphLink {
  source: string;
  target: string;
  type: string;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
  stats: Record<string, number>;
}

// SSE event types from the agent streaming endpoint
export type AgentEventType =
  | "thinking"
  | "tool_call"
  | "tool_result"
  | "traversal"
  | "final"
  | "error"
  | "done";

export interface AgentEvent {
  type: AgentEventType;
  content?: string;
  tool_name?: string;
  args?: Record<string, unknown>;
  summary?: string;
  node?: string;
  message?: string;
  iteration?: number;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  traversalEvents?: AgentEvent[];
}
