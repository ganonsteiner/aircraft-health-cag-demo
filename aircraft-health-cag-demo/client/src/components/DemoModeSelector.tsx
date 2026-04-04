import { cn } from "../lib/utils";
import { useStore } from "../lib/store";
import type { DemoMode } from "../lib/types";

const MODES: { id: DemoMode; label: string; icon: string; activeClass: string; hoverClass: string }[] = [
  {
    id: "clean",
    label: "Clean",
    icon: "✓",
    activeClass: "bg-emerald-600 border-emerald-500 text-white",
    hoverClass: "hover:border-emerald-700 hover:text-emerald-300",
  },
  {
    id: "caution",
    label: "Caution",
    icon: "⚠",
    activeClass: "bg-yellow-600 border-yellow-500 text-white",
    hoverClass: "hover:border-yellow-700 hover:text-yellow-300",
  },
  {
    id: "grounded",
    label: "Grounded",
    icon: "✗",
    activeClass: "bg-red-700 border-red-600 text-white",
    hoverClass: "hover:border-red-700 hover:text-red-300",
  },
];

export default function DemoModeSelector() {
  const { demoMode, setDemoMode } = useStore();

  return (
    <div className="flex items-center gap-1 bg-zinc-900 border border-zinc-700 rounded-lg p-0.5">
      <span className="text-xs text-zinc-600 px-2 hidden sm:inline">Demo</span>
      {MODES.map((mode) => {
        const isActive = demoMode === mode.id;
        return (
          <button
            key={mode.id}
            onClick={() => setDemoMode(mode.id)}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold border transition-all",
              isActive
                ? mode.activeClass
                : cn("border-transparent text-zinc-500", mode.hoverClass)
            )}
          >
            <span>{mode.icon}</span>
            <span className="hidden sm:inline">{mode.label}</span>
          </button>
        );
      })}
    </div>
  );
}
