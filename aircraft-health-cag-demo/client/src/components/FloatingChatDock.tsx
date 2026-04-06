import { MessageSquare, X } from "lucide-react";
import { useStore } from "../lib/store";
import QueryInterface from "./QueryInterface";

interface Props {
  visible: boolean;
  apiKeyMissing: boolean;
  graphContext: boolean;
  /** Gray out Fleet in chat; store should hold a tail on these tabs (see App). */
  fleetOptionDisabled: boolean;
}

/**
 * Fixed FAB + chat-only popup for every tab except AI Assistant.
 * Open state lives in Zustand so it survives tab changes.
 */
export default function FloatingChatDock({
  visible,
  apiKeyMissing,
  graphContext,
  fleetOptionDisabled,
}: Props) {
  const floatingChatOpen = useStore((s) => s.floatingChatOpen);
  const setFloatingChatOpen = useStore((s) => s.setFloatingChatOpen);
  const toggleFloatingChat = useStore((s) => s.toggleFloatingChat);

  if (!visible) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => toggleFloatingChat()}
        className="fixed bottom-6 right-6 w-12 h-12 bg-sky-600 hover:bg-sky-500 rounded-full
          shadow-lg flex items-center justify-center transition-colors z-40"
        title={floatingChatOpen ? "Close chat" : "Open chat"}
      >
        {floatingChatOpen ? (
          <X className="w-5 h-5 text-white" />
        ) : (
          <MessageSquare className="w-5 h-5 text-white" />
        )}
      </button>

      {floatingChatOpen && (
        <div
          className="fixed right-4 bottom-20 w-[min(28rem,92vw)] bg-zinc-900 border border-zinc-700 rounded-2xl
            shadow-2xl overflow-hidden z-40 flex flex-col"
          style={{ height: "70vh" }}
        >
          <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-700 bg-zinc-900/90 backdrop-blur-sm">
            <div className="flex items-center gap-2 min-w-0">
              <MessageSquare className="w-4 h-4 text-sky-400 shrink-0" />
              <span className="text-sm font-semibold text-zinc-200 shrink-0">Chat</span>
              {graphContext ? (
                <span className="text-xs text-zinc-600 hidden sm:inline truncate">
                  · graph animates as the agent runs
                </span>
              ) : (
                <span className="text-xs text-zinc-600 hidden sm:inline truncate">
                  · same thread as AI Assistant
                </span>
              )}
            </div>
            <button
              type="button"
              onClick={() => setFloatingChatOpen(false)}
              className="text-zinc-600 hover:text-zinc-300 transition-colors shrink-0"
              aria-label="Close chat"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="flex-1 min-h-0 overflow-hidden">
            <QueryInterface
              apiKeyMissing={apiKeyMissing}
              showTraversalSidebar={false}
              showSuggestedQuestions={false}
              fleetOptionDisabled={fleetOptionDisabled}
            />
          </div>
        </div>
      )}
    </>
  );
}
