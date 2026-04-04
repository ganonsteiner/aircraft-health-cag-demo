import { AlertTriangle, ServerOff, WifiOff } from "lucide-react";
import { cn } from "../lib/utils";

interface Props {
  apiKeyMissing: boolean;
  mockCdfOffline: boolean;
  connectionError: boolean;
}

export default function SetupBanner({ apiKeyMissing, mockCdfOffline, connectionError }: Props) {
  return (
    <div className="border-b border-yellow-800/50 bg-yellow-950/20">
      <div className="max-w-screen-2xl mx-auto px-4 sm:px-6 py-3 space-y-2">
        {connectionError && (
          <BannerRow
            icon={<WifiOff className="w-4 h-4 shrink-0" />}
            color="yellow"
            title="API server not reachable"
            detail="Start the backend: npm run api"
          />
        )}
        {mockCdfOffline && !connectionError && (
          <BannerRow
            icon={<ServerOff className="w-4 h-4 shrink-0" />}
            color="yellow"
            title="Mock CDF server offline (port 4000)"
            detail="Start it: npm run mock-cdf"
          />
        )}
        {apiKeyMissing && (
          <BannerRow
            icon={<AlertTriangle className="w-4 h-4 shrink-0" />}
            color="yellow"
            title="ANTHROPIC_API_KEY not configured — AI queries disabled"
            detail={
              <>
                Add your key to{" "}
                <code className="font-mono text-yellow-300 bg-yellow-950/60 px-1 rounded">
                  backend/.env
                </code>
                : <code className="font-mono text-yellow-300">ANTHROPIC_API_KEY=sk-ant-...</code>
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
        {detail && <span className="text-zinc-400 ml-2">{detail}</span>}
      </div>
    </div>
  );
}
