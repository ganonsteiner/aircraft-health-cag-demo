import { useEffect, useRef, useState } from "react";
import {
  Plane,
  Activity,
  Wrench,
  MessageSquare,
  GitBranch,
  Plane as PlaneIcon,
  History,
  Loader2,
} from "lucide-react";
import { cn } from "./lib/utils";
import { api } from "./lib/api";
import { useStore } from "./lib/store";
import type { HealthStatus } from "./lib/types";
import SetupBanner from "./components/SetupBanner";
import StatusDashboard from "./components/StatusDashboard";
import QueryInterface from "./components/QueryInterface";
import MaintenanceTimeline from "./components/MaintenanceTimeline";
import DemoModeSelector from "./components/DemoModeSelector";
import AircraftComponents from "./components/AircraftComponents";
import FlightHistory from "./components/FlightHistory";
import KnowledgeGraph from "./components/KnowledgeGraph";

type Tab = "dashboard" | "query" | "maintenance" | "aircraft" | "flights" | "graph";

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>("dashboard");
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [healthError, setHealthError] = useState(false);
  const { isQuerying, demoMode } = useStore();

  // Re-check health when demo mode changes (store counts may differ)
  const prevDemoMode = useRef(demoMode);
  useEffect(() => {
    if (prevDemoMode.current !== demoMode) {
      prevDemoMode.current = demoMode;
    }
    api
      .health()
      .then(setHealth)
      .catch(() => setHealthError(true));
  }, [demoMode]);

  const apiKeyMissing = health ? !health.anthropic_api_key_configured : false;
  const mockCdfOffline = health ? !health.mock_cdf_reachable : false;

  const tabs: { id: Tab; label: string; icon: React.ReactNode }[] = [
    { id: "dashboard", label: "Aircraft Status", icon: <Activity className="w-4 h-4 shrink-0" /> },
    {
      id: "query",
      label: "AI Assistant",
      icon: isQuerying ? (
        <Loader2 className="w-4 h-4 shrink-0 animate-spin text-sky-400" />
      ) : (
        <MessageSquare className="w-4 h-4 shrink-0" />
      ),
    },
    { id: "maintenance", label: "Maintenance", icon: <Wrench className="w-4 h-4 shrink-0" /> },
    { id: "aircraft", label: "Aircraft", icon: <PlaneIcon className="w-4 h-4 shrink-0" /> },
    { id: "flights", label: "Flights", icon: <History className="w-4 h-4 shrink-0" /> },
    { id: "graph", label: "Knowledge Graph", icon: <GitBranch className="w-4 h-4 shrink-0" /> },
  ];

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col">
      {/* Header */}
      <header className="border-b border-zinc-800 bg-zinc-900/90 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-screen-2xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between gap-4">
          {/* Left: aircraft identity */}
          <div className="flex items-center gap-3 shrink-0">
            <div className="p-2 bg-sky-500/10 rounded-lg border border-sky-500/20">
              <Plane className="w-5 h-5 text-sky-400" />
            </div>
            <div>
              <h1 className="text-sm font-semibold text-zinc-100 tracking-wide">N4798E</h1>
              <p className="text-xs text-zinc-500 hidden sm:block">
                1978 Cessna 172N · KPHX · Lycoming O-320-H2AD
              </p>
            </div>
          </div>

          {/* Center: demo mode selector */}
          <div className="flex-1 flex justify-center">
            <DemoModeSelector />
          </div>

          {/* Right: system status */}
          <div className="flex items-center gap-2 shrink-0">
            {health && (
              <div
                className={cn(
                  "flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border",
                  health.status === "ok"
                    ? "text-emerald-400 bg-emerald-950/40 border-emerald-800/50"
                    : "text-yellow-400 bg-yellow-950/40 border-yellow-800/50"
                )}
              >
                <span
                  className={cn(
                    "w-1.5 h-1.5 rounded-full",
                    health.status === "ok" ? "bg-emerald-400" : "bg-yellow-400"
                  )}
                />
                <span className="hidden sm:inline">
                  {health.status === "ok" ? "Systems Online" : "Degraded"}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Nav tabs */}
        <div className="max-w-screen-2xl mx-auto px-4 sm:px-6 flex gap-0 overflow-x-auto scrollbar-hide border-t border-zinc-800/50">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 whitespace-nowrap transition-colors shrink-0",
                activeTab === tab.id
                  ? "border-sky-500 text-sky-400"
                  : "border-transparent text-zinc-500 hover:text-zinc-300 hover:border-zinc-600"
              )}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>
      </header>

      {/* Setup banners */}
      {(apiKeyMissing || mockCdfOffline || healthError) && (
        <SetupBanner
          apiKeyMissing={apiKeyMissing}
          mockCdfOffline={mockCdfOffline}
          connectionError={healthError}
        />
      )}

      {/* Main content — all tabs rendered but hidden when inactive to preserve state */}
      <main className="flex-1 max-w-screen-2xl mx-auto w-full px-4 sm:px-6 py-6">
        <div className={activeTab === "dashboard" ? "block" : "hidden"}>
          <StatusDashboard />
        </div>
        <div className={activeTab === "query" ? "block" : "hidden"}>
          <QueryInterface apiKeyMissing={apiKeyMissing} />
        </div>
        <div className={activeTab === "maintenance" ? "block" : "hidden"}>
          <MaintenanceTimeline active={activeTab === "maintenance"} />
        </div>
        <div className={activeTab === "aircraft" ? "block" : "hidden"}>
          <AircraftComponents active={activeTab === "aircraft"} />
        </div>
        <div className={activeTab === "flights" ? "block" : "hidden"}>
          <FlightHistory active={activeTab === "flights"} />
        </div>
        <div className={activeTab === "graph" ? "block" : "hidden"}>
          <KnowledgeGraph active={activeTab === "graph"} />
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-zinc-800 py-3 px-6 text-center">
        <p className="text-xs text-zinc-600">
          N4798E Aircraft Health Assistant · CAG Demo ·{" "}
          <span className="text-zinc-700">
            Context from knowledge graph traversal, not vector search
          </span>
        </p>
      </footer>
    </div>
  );
}
