import { AlertTriangle, ServerOff, WifiOff } from "lucide-react";
import { cn } from "../lib/utils";

interface Props {
  apiKeyMissing: boolean;
  mockCdfOffline: boolean;
  mockCdfNoFleetData: boolean;
  connectionError: boolean;
}

export default function SetupBanner({
  apiKeyMissing,
  mockCdfOffline,
  mockCdfNoFleetData,
  connectionError,
}: Props) {
  return (
    <div className="border-b border-yellow-800/50 bg-yellow-950/20">
      <div className="max-w-screen-2xl mx-auto px-4 sm:px-6 py-3 space-y-2">
        {connectionError && (
          <BannerRow
            icon={<WifiOff className="w-4 h-4 shrink-0" />}
            color="yellow"
            title="API server not reachable"
            detail="Start the API: npm run api"
          />
        )}
        {mockCdfOffline && !connectionError && (
          <BannerRow
            icon={<ServerOff className="w-4 h-4 shrink-0" />}
            color="yellow"
            title="Mock CDF server offline (port 4001)"
            detail="Start it: npm run mock-cdf"
          />
        )}
        {mockCdfNoFleetData && !mockCdfOffline && !connectionError && (
          <BannerRow
            icon={<AlertTriangle className="w-4 h-4 shrink-0" />}
            color="yellow"
            title="Mock CDF on port 4001 is not serving this project's fleet data"
            detail={
              <>
                Another process may be using port 4001 (check{" "}
                <code className="font-mono text-yellow-300 bg-yellow-950/60 px-1 rounded">
                  lsof -i :4001
                </code>
                ), stop it, then restart{" "}
                <code className="font-mono text-yellow-300">npm run dev</code> so mock-cdf can start.
              </>
            }
          />
        )}
        {apiKeyMissing && (
          <BannerRow
            icon={<AlertTriangle className="w-4 h-4 shrink-0" />}
            color="yellow"
            title="No LLM configured — AI queries disabled"
            detail={
              <>
                Set{" "}
                <code className="font-mono text-yellow-300 bg-yellow-950/60 px-1 rounded">
                  ANTHROPIC_API_KEY
                </code>{" "}
                (higher performance) or{" "}
                <code className="font-mono text-yellow-300 bg-yellow-950/60 px-1 rounded">
                  LOCAL_LLM_URL
                </code>{" "}
                (Ollama, lower performance) in{" "}
                <code className="font-mono text-yellow-300">.env</code>
              </>
            }
          />
        )}
      </div>
    </div>
  );
}

function BannerRow({
  icon,
  color,
  title,
  detail,
}: {
  icon: React.ReactNode;
  color: string;
  title: string;
  detail: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "flex items-start gap-2 text-sm",
        color === "yellow" ? "text-yellow-400" : "text-red-400"
      )}
    >
      {icon}
      <div>
        <span className="font-medium">{title}</span>
        {detail && <span className="text-slate-500 ml-2">{detail}</span>}
      </div>
    </div>
  );
}
