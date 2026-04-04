import { useRef, useEffect, useState } from "react";
import { Send, AlertCircle } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { cn } from "../lib/utils";
import type { AgentEvent } from "../lib/types";
import { useStore } from "../lib/store";
import { SUGGESTIONS } from "../lib/suggestions";
import GraphTraversalPanel from "./GraphTraversalPanel";

interface Props {
  apiKeyMissing: boolean;
  compact?: boolean; // used by KnowledgeGraph overlay
}

export default function QueryInterface({ apiKeyMissing, compact = false }: Props) {
  const {
    demoMode,
    chatMessages,
    addChatMessage,
    updateChatMessage,
    isQuerying,
    setIsQuerying,
    clearTraversalEvents,
    appendTraversalEvent,
    traversalEvents,
    startReplay,
    isReplaying,
    replayNodes,
    graphExpanded,
    setGraphExpanded,
  } = useStore();

  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  // The traversal feed shown in the panel — live during query, last session after
  const lastAssistantMsg = [...chatMessages].reverse().find((m) => m.role === "assistant");
  const displayEvents = isQuerying
    ? traversalEvents
    : isReplaying
    ? replayNodes
    : lastAssistantMsg?.traversalEvents ?? [];

  const sendQuery = async (question: string) => {
    if (!question.trim() || isQuerying || apiKeyMissing) return;

    const userMsgId = crypto.randomUUID();
    addChatMessage({
      id: userMsgId,
      role: "user",
      content: question,
      timestamp: new Date(),
    });
    setInput("");
    setIsQuerying(true);
    clearTraversalEvents();

    const assistantMsgId = crypto.randomUUID();
    addChatMessage({
      id: assistantMsgId,
      role: "assistant",
      content: "",
      timestamp: new Date(),
      traversalEvents: [],
    });

    const sessionEvents: AgentEvent[] = [];

    try {
      const res = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        const errMsg =
          typeof err.detail === "object" ? err.detail.error : (err.detail || res.statusText);
        updateChatMessage(assistantMsgId, { content: `**Error:** ${errMsg}` });
        return;
      }

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          const jsonStr = line.slice(5).trim();
          if (!jsonStr) continue;
          try {
            const event: AgentEvent = JSON.parse(jsonStr);
            sessionEvents.push(event);

            // Immediate dispatch — no batching
            appendTraversalEvent(event);

            if (event.type === "final") {
              updateChatMessage(assistantMsgId, {
                content: event.content || "",
                traversalEvents: [...sessionEvents],
              });
            } else if (event.type === "error") {
              updateChatMessage(assistantMsgId, {
                content: `**Error:** ${event.message}`,
                traversalEvents: [...sessionEvents],
              });
            } else if (event.type === "done") {
              break;
            }
          } catch {
            // malformed JSON — skip
          }
        }
      }
    } catch (e) {
      updateChatMessage(assistantMsgId, {
        content: `**Connection error:** ${e instanceof Error ? e.message : String(e)}`,
      });
    } finally {
      setIsQuerying(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendQuery(input);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendQuery(input);
    }
  };

  const suggestions = SUGGESTIONS[demoMode];
  const canReplay =
    !isQuerying && !isReplaying && (lastAssistantMsg?.traversalEvents?.length ?? 0) > 0;

  const chatPanel = (
    <div className="flex-1 flex flex-col min-w-0 bg-zinc-900 rounded-xl border border-zinc-800 overflow-hidden">
      {/* Sample questions — only when chat is empty */}
      {chatMessages.length === 0 && (
        <div className="p-4 border-b border-zinc-800">
          <p className="text-xs text-zinc-500 mb-2 font-medium uppercase tracking-wide">
            Suggested questions
          </p>
          <div className="flex flex-wrap gap-2">
            {suggestions.map((q) => (
              <button
                key={q}
                onClick={() => sendQuery(q)}
                disabled={apiKeyMissing || isQuerying}
                className="text-xs px-2.5 py-1.5 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-300
                  hover:bg-zinc-700 hover:border-zinc-600 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4" style={{ minHeight: 0 }}>
        {chatMessages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center text-zinc-600 py-8">
            <p className="text-sm">Ask anything about N4798E</p>
            <p className="text-xs mt-1">
              The agent traverses the CDF knowledge graph to answer
            </p>
          </div>
        )}

        {chatMessages.map((msg) => (
          <div
            key={msg.id}
            className={cn("flex", msg.role === "user" ? "justify-end" : "justify-start")}
          >
            <div
              className={cn(
                "max-w-[85%] rounded-2xl px-4 py-3 text-sm",
                msg.role === "user"
                  ? "bg-sky-600 text-white rounded-tr-sm"
                  : "bg-zinc-800 text-zinc-100 rounded-tl-sm border border-zinc-700"
              )}
            >
              {msg.role === "user" ? (
                <p>{msg.content}</p>
              ) : msg.content ? (
                <div className="prose prose-sm prose-invert max-w-none">
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                </div>
              ) : (
                <StreamingIndicator />
              )}
              {msg.role === "assistant" &&
                msg.traversalEvents &&
                msg.traversalEvents.length > 0 && (
                  <p className="text-xs text-zinc-600 mt-2 border-t border-zinc-700 pt-2">
                    {msg.traversalEvents.filter((e) => e.type === "traversal").length} nodes
                    traversed ·{" "}
                    {msg.traversalEvents.filter((e) => e.type === "tool_call").length} tool calls
                  </p>
                )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-zinc-800">
        {apiKeyMissing && (
          <div className="flex items-center gap-2 text-xs text-yellow-500 mb-2">
            <AlertCircle className="w-3.5 h-3.5" />
            Add ANTHROPIC_API_KEY to backend/.env to enable queries
          </div>
        )}
        <form onSubmit={handleSubmit} className="flex gap-2 items-end">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={apiKeyMissing ? "API key required..." : "Ask about N4798E..."}
            disabled={apiKeyMissing || isQuerying}
            rows={1}
            className="flex-1 resize-none bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2.5 text-sm
              text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-sky-600 focus:ring-1 focus:ring-sky-600
              disabled:opacity-50 disabled:cursor-not-allowed"
            style={{ minHeight: 44, maxHeight: 120 }}
          />
          <button
            type="submit"
            disabled={!input.trim() || isQuerying || apiKeyMissing}
            className="p-2.5 bg-sky-600 hover:bg-sky-500 rounded-xl text-white transition-colors
              disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );

  if (compact) {
    // KnowledgeGraph overlay — chat only, no traversal panel
    return (
      <div className="flex flex-col h-full">
        {chatPanel}
      </div>
    );
  }

  const traversalPanel = (
    <GraphTraversalPanel
      events={displayEvents}
      isStreaming={isQuerying}
      canReplay={canReplay}
      onReplay={() => {
        if (lastAssistantMsg?.traversalEvents) {
          startReplay(lastAssistantMsg.traversalEvents);
        }
      }}
      isReplaying={isReplaying}
      expanded={graphExpanded}
      onToggleExpand={() => setGraphExpanded(!graphExpanded)}
    />
  );

  return (
    <div className="flex flex-col lg:flex-row gap-4 min-h-[500px]">
      {/* Chat panel — full width on mobile, compressed when graph is expanded on desktop */}
      <div className={cn("flex flex-col min-w-0 min-h-[500px]", graphExpanded ? "lg:w-96 lg:shrink-0" : "flex-1")}>
        {chatPanel}
      </div>

      {/* Graph Traversal Panel — stacks below chat on mobile, side panel on desktop */}
      <div
        className={cn(
          "flex flex-col",
          graphExpanded ? "flex-1 min-h-[500px]" : "lg:w-80 lg:shrink-0"
        )}
      >
        {traversalPanel}
      </div>
    </div>
  );
}

function StreamingIndicator() {
  return (
    <div className="flex items-center gap-1 py-1">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="w-1.5 h-1.5 bg-sky-400 rounded-full animate-bounce"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </div>
  );
}
