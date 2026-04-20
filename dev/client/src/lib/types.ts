export type Airworthiness = "AIRWORTHY" | "FERRY_ONLY" | "CAUTION" | "NOT_AIRWORTHY" | "UNKNOWN";

export interface HealthStatus {
  status: "ok" | "degraded" | "mock_cdf_offline" | "llm_missing";
  anthropic_api_key_configured: boolean;
  local_llm_configured: boolean;
  /** True when either Anthropic or a local LLM is configured. */
  llm_ready: boolean;
  mock_cdf_reachable: boolean;
  /** False when /health responds but assets/byids returns no fleet (e.g. wrong process on port 4001). */
  mock_cdf_fleet_ready?: boolean;
  store: Record<string, number>;
  checkedAt: string;
}

export interface FleetAircraft {
  tail: string;
  name: string;
  smoh: number;
  tbo: number;
  smohPercent: number;
  engine2SMOH?: number;
  engine2TBO?: number;
  engine2SMOHPercent?: number;
  hobbs: number;
  /** Engine tach (maintenance clock). */
  tach: number;
  airworthiness: Airworthiness;
  isAirworthy: boolean;
  openSquawkCount: number;
  groundingSquawkCount: number;
  /** Tach hours overdue on oil (maintenance clock). */
  oilHoursOverdue: number;
  oilTachHoursOverdue: number;
  oilTachHoursUntilDue: number;
  oilDaysUntilDue: number | null;
  annualDaysRemaining: number | null;
  annualDueDate: string;
  /** Most recent maintenance record calendar date (YYYY-MM-DD), or null if none. */
  lastMaintenanceDate: string | null;
  metadata: Record<string, string>;
}

export interface AircraftStatus {
  tail: string;
  hobbs: number;
  tach: number;
  engineSMOH: number;
  engineTBO: number;
  engineSMOHPercent: number;
  engine2SMOH?: number;
  engine2TBO?: number;
  engine2SMOHPercent?: number;
  annualDueDate: string;
  annualDaysRemaining: number | null;
  openSquawkCount: number;
  groundingSquawkCount: number;
  airworthiness: Airworthiness;
  isAirworthy: boolean;
  oilHoursOverdue: number;
  oilTachHoursOverdue: number;
  oilTachHoursUntilDue: number;
  oilNextDueTach: number;
  oilNextDueDate: string;
  oilDaysUntilDue: number | null;
  oilNextDueHobbs: number;
  lastMaintenanceDate: string | null;
  dataFreshAt: string;
}

export interface Squawk {
  externalId: string;
  description: string;
  component: string;
  severity: "grounding" | "non-grounding" | "cosmetic" | string; // GANON
  status: "open" | "resolved" | "deferred" | string;
  dateIdentified: string;
  tail: string;
  metadata: Record<string, string>;
}

export interface MaintenanceItem {
  component: string;
  summary: string;
  description: string;
  maintenanceType: string;
  nextDueTach: number | null;
  nextDueHobbs: number | null;
  hoursUntilDue: number | null;
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
  /** Calendar years present in history for this aircraft (after component/type filters, before year filter). */
  available_years?: number[];
}

export interface FlightRecord {
  timestamp: string;
  hobbs_start: number;
  hobbs_end: number;
  /** Tach hours at start/end of flight; null if not in event metadata (re-ingest for data). */
  tach_start: number | null;
  tach_end: number | null;
  duration: number;
  route: string;
  /** 737 engine metrics */
  egt_deviation: number | null;
  n1_vibration: number | null;
  oil_pressure_min: number | null;
  oil_pressure_max: number | null;
  oil_temp_max: number | null;
  fuel_flow_kgh: number | null;
  /** Legacy piston fields (may be null for 737 flights) */
  cht_max: number | null;
  egt_max: number | null;
  fuel_used_gal: number | null;
  pilot_notes: string;
  anomalous: boolean;
  year: number;
}

export interface TimeseriesDatapoint {
  timestamp: number;
  value: number;
  flight_index: number;
}

export interface TimeseriesResponse {
  aircraft: string;
  metric: string;
  unit: string;
  caution_threshold: number | null;
  critical_threshold?: number | null;
  datapoints: TimeseriesDatapoint[];
}

export interface Insight {
  id: string;
  title: string;
  summary: string;
  severity: "critical" | "warning" | "info";
  aircraft: string[];
  generated_at: string;
  reasoning: string;
  category: "safety" | "maintenance" | "pattern" | "compliance";
}

export interface InsightsResponse {
  insights: Insight[];
  generated_at: string | null;
  is_fallback: boolean;
}

export interface PredictiveRisk {
  aircraft: string;
  status: "scored" | "insufficient_data";
  risk_score: number | null;
  risk_level: "low" | "moderate" | "high" | "critical" | "failed" | null;
  primary_driver: string | null;
  reasoning: string | null;
  recommended_action: string | null;
  confidence: "high" | "moderate" | "low" | null;
  data_points_analyzed: number | null;
  generated_at: string | null;
}

export interface Suggestion {
  question: string;
  context: string | null;
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
  nextDueTach: number | null;
  nextDueHobbs: number | null;
  nextDueDate: string | null;
  currentHobbs: number;
  currentTach: number;
  hoursUntilDue: number | null;
  status: "ok" | "due_soon" | "overdue";
  maintenanceCount: number;
}

export interface OperationalPolicy {
  externalId: string;
  title: string;
  description: string;
  rule: string;
  category: string;
  references: string;
}

export interface GraphNode {
  id: string;
  label: string;
  type:
    | "asset"
    | "timeseries"
    | "event"
    | "file"
    | "OperationalPolicy";
  group: number;
  linkCount: number;
  unit?: string;
  metadata?: Record<string, string>;
}

export interface GraphLink {
  source: string;
  target: string;
  type: string;
  color?: string;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
  stats: Record<string, number>;
}

// SSE event types from the agent streaming endpoint
export type AgentEventType =
  | "thinking"
  | "status"
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
