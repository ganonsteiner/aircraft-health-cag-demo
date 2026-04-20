import { useRef, useEffect, useState } from "react";
import { api } from "../lib/api";
import { Send, AlertCircle } from "lucide-react";
import { MenuSelect } from "./MenuSelect";
import ReactMarkdown from "react-markdown";
import {
  cn,
  CARD_SURFACE_B,
  CARD_SURFACE_C,
  MAIN_TAB_CONTENT_FRAME,
  TAB_PAGE_TOP_INSET,
} from "../lib/utils";
import type { AgentEvent, GraphData } from "../lib/types";
import { traversalActivityCounts } from "../lib/traversalGraphIds";
import { useStore, TAILS, INSTRUMENTED_TAILS, type TailNumber } from "../lib/store";
import GraphTraversalPanel from "./GraphTraversalPanel";

interface Props {
  apiKeyMissing: boolean;
  /** When false (e.g. Knowledge Graph popup), chat only — no traversal list. Default true for AI Assistant tab. */
  showTraversalSidebar?: boolean;
  /** When false (floating chat), hide suggested-question chips. */
  showSuggestedQuestions?: boolean;
  /** When true (floating chat on single-aircraft tabs), Fleet is disabled and grayed out. */
  fleetOptionDisabled?: boolean;
  /** Full tab page (selector strip + two cards) vs compact floating dock. */
  layout?: "page" | "embedded";
}

const FLEET_SUGGESTIONS_FALLBACK = [
  "What is the fleet health status?",
  "Which aircraft need attention?",
  "Any upcoming scheduled inspections?",
  "Are there any active safety concerns?",
];

const GENERIC_AIRCRAFT_SUGGESTIONS = [
  "What squawks are open?",
  "When is the next inspection due?",
  "What components does this aircraft have?",
  "Show recent maintenance history.",
];

const INSTRUMENTED_SET = new Set(INSTRUMENTED_TAILS as unknown as string[]);

function airworthinessDotClass(aw: string | undefined): string {
  if (aw === "NOT_AIRWORTHY") return "bg-red-500";
  if (aw === "CAUTION" || aw === "FERRY_ONLY") return "bg-orange-500";
  if (aw === "AIRWORTHY") return "bg-emerald-500";
  return "bg-slate-300";
}

function AircraftSelector({
  value,
  onChange,
  fleetDisabled = false,
  variant = "bar",
  dense = false,
}: {
  value: TailNumber | null;
  onChange: (t: TailNumber | null) => void;
  fleetDisabled?: boolean;
  variant?: "inline" | "bar";
  dense?: boolean;
}) {
  const fleetStatusMap = useStore((s) => s.fleetStatusMap);
  const barPad = dense ? "px-2 py-1.5" : "px-3 py-2";

  return (
    <div
      className={cn(
        "flex items-center gap-2",
        variant === "bar" && cn("border-b border-slate-200", barPad)
      )}
    >
      {/* Fleet button */}
      <button
        type="button"
        disabled={fleetDisabled}
        onClick={() => { if (!fleetDisabled) onChange(null); }}
        title={fleetDisabled ? "Fleet scope not available on this page" : undefined}
        className={cn(
          "inline-flex items-center rounded-lg border bg-slate-100 px-3 py-1.5 text-left text-sm transition-colors focus:outline-none",
          fleetDisabled
            ? "cursor-not-allowed opacity-45 border-slate-200 text-slate-400 pointer-events-none"
            : value === null
              ? "border-[#304cb2] text-[#304cb2]"
              : "border-slate-200 text-slate-700 hover:border-slate-300 hover:bg-slate-100/90 focus:border-[#304cb2]"
        )}
      >
        Fleet
      </button>

      {/* Aircraft dropdown */}
      <MenuSelect
        value={value ?? ""}
        options={[
          { value: "", label: "Select aircraft…" },
          ...TAILS.map((t) => ({
            value: t,
            label: (
              <span className="flex items-center gap-1.5">
                <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${airworthinessDotClass(fleetStatusMap[t])}`} />
                {t}
              </span>
            ),
          })),
        ]}
        onChange={(v) => {
          if (v === "") onChange(null);
          else onChange(v as TailNumber);
        }}
        ariaLabel="Select aircraft"
        className={dense ? "text-xs" : ""}
        active={value !== null}
      />
    </div>
  );
}

function isGraphTraversalEvent(e: AgentEvent): boolean {
  return e.type === "tool_call" || e.type === "tool_result" || e.type === "traversal";
}

function formatTraversalActivityLine(events: AgentEvent[], graphData: GraphData | null): string {
  const { toolCount, stepCount, graphNodeCount } = traversalActivityCounts(events, graphData);
  const toolLabel = `${toolCount} tool${toolCount === 1 ? "" : "s"}`;
  const nodeOrStepLabel =
    graphNodeCount !== null
      ? `${graphNodeCount} node${graphNodeCount === 1 ? "" : "s"}`
      : `${stepCount} step${stepCount === 1 ? "" : "s"}`;
  return `${toolLabel} · ${nodeOrStepLabel}`;
}

export default function QueryInterface({
  apiKeyMissing,
  showTraversalSidebar = true,
  showSuggestedQuestions = true,
  fleetOptionDisabled = false,
  layout = "page",
}: Props) {
  const {
    selectedAircraft,
    setSelectedAircraft,
    chatMessages,
    addChatMessage,
    insertChatMessageBefore,
    updateChatMessage,
    isQuerying,
    setIsQuerying,
    clearTraversalEvents,
    appendTraversalEvent,
    traversalEvents,
    startReplay,
    isReplaying,
    replayNodes,
    graphDataSnapshot,
  } = useStore();
  const setGraphDataSnapshot = useStore((s) => s.setGraphDataSnapshot);

  const [dynamicFleetSuggestions, setDynamicFleetSuggestions] = useState<string[]>([]);
  const [dynamicAircraftSuggestions, setDynamicAircraftSuggestions] = useState<string[]>([]);

  useEffect(() => {
    api.graph().then(setGraphDataSnapshot).catch(() => {});
  }, [setGraphDataSnapshot]);

  // Fleet suggestions: fetch on mount, then poll every 10s for up to ~2 minutes so
  // that once the background LLM generation completes, we pick up the dynamic prompts
  // without requiring a page reload.
  useEffect(() => {
    let cancelled = false;
    const deadline = Date.now() + 150_000;
    const tick = () => {
      if (cancelled) return;
      api.suggestions()
        .then((s) => {
          if (cancelled) return;
          setDynamicFleetSuggestions(s.map((x) => x.question).slice(0, 6));
          if (Date.now() < deadline) setTimeout(tick, 10_000);
        })
        .catch(() => { if (!cancelled && Date.now() < deadline) setTimeout(tick, 10_000); });
    };
    tick();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!selectedAircraft || !INSTRUMENTED_SET.has(selectedAircraft)) {
      setDynamicAircraftSuggestions([]);
      return;
    }
    let cancelled = false;
    const tail = selectedAircraft;
    const deadline = Date.now() + 150_000;
    const tick = () => {
      if (cancelled) return;
      api.suggestions(tail)
        .then((s) => {
          if (cancelled) return;
          setDynamicAircraftSuggestions(s.map((x) => x.question).slice(0, 4));
          if (Date.now() < deadline) setTimeout(tick, 10_000);
        })
        .catch(() => {
          if (!cancelled) setDynamicAircraftSuggestions([]);
          if (!cancelled && Date.now() < deadline) setTimeout(tick, 10_000);
        });
    };
    tick();
    return () => { cancelled = true; };
  }, [selectedAircraft]);

  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  const lastAssistantMsg = [...chatMessages].reverse().find((m) => m.role === "assistant");
  const displayEvents = isQuerying
    ? traversalEvents
    : isReplaying
    ? replayNodes
    : lastAssistantMsg?.traversalEvents ?? [];

  const suggestions = selectedAircraft
    ? INSTRUMENTED_SET.has(selectedAircraft)
      ? dynamicAircraftSuggestions.length > 0
        ? dynamicAircraftSuggestions
        : GENERIC_AIRCRAFT_SUGGESTIONS
      : GENERIC_AIRCRAFT_SUGGESTIONS
    : dynamicFleetSuggestions.length > 0
    ? dynamicFleetSuggestions
    : FLEET_SUGGESTIONS_FALLBACK;

  const compact = layout === "embedded";

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
    let noticeInserted = false;

    try {
      const res = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, aircraft: selectedAircraft }),
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

            if (event.type === "status" && !noticeInserted && event.content?.trim()) {
              insertChatMessageBefore(assistantMsgId, {
                id: crypto.randomUUID(),
                role: "assistant",
                content: event.content,
                timestamp: new Date(),
              });
              noticeInserted = true;
            }

            if (isGraphTraversalEvent(event)) {
              sessionEvents.push(event);
              appendTraversalEvent(event);
            }

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
    if (e.key !== "Enter" || e.shiftKey) return;
    if (isQuerying) {
      e.preventDefault();
      return;
    }
    e.preventDefault();
    sendQuery(input);
  };

  const canReplay =
    !isQuerying && !isReplaying && (lastAssistantMsg?.traversalEvents?.length ?? 0) > 0;

  const placeholderText = apiKeyMissing
    ? "API key required..."
    : selectedAircraft
    ? `Ask about ${selectedAircraft}...`
    : "Ask about the fleet...";

  const chatBody = (
    <>
      {/* Suggested questions — full AI Assistant tab only, when empty */}
      {showSuggestedQuestions && chatMessages.length === 0 && (
        <div className="shrink-0 flex min-h-[6.75rem] flex-col justify-start border-b border-slate-200 px-4 pt-2.5 pb-2.5">
          <p className="text-xs text-slate-400 mb-1.5 shrink-0 font-semibold uppercase tracking-widest">
            Suggested questions for {selectedAircraft ? `${selectedAircraft}` : "Fleet"}
          </p>
          <div className="flex flex-wrap content-start gap-2">
            {suggestions.map((q) => (
              <button
                key={q}
                onClick={() => sendQuery(q)}
                disabled={apiKeyMissing || isQuerying}
                className={cn(
                  "text-xs px-2.5 py-1.5 rounded-lg text-slate-700 hover:border-slate-300 transition-colors disabled:opacity-40 disabled:cursor-not-allowed text-left",
                  CARD_SURFACE_C
                )}
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Messages */}
      <div
        className={cn("flex-1 overflow-y-auto", compact ? "p-2.5 space-y-2" : "p-4 space-y-4")}
        style={{ minHeight: 0 }}
      >
        {chatMessages.length === 0 && (
          <div
            className={cn(
              "flex flex-col items-center justify-center h-full text-center text-slate-400",
              compact ? "py-4 text-xs" : "py-8"
            )}
          >
            <p className={cn(compact ? "text-xs" : "text-sm")}>
              {selectedAircraft ? `Ask about ${selectedAircraft}` : "Ask about the Southwest fleet"}
            </p>
            <p className={cn(compact ? "text-xs mt-0.5" : "text-xs mt-1")}>
              The agent will traverse the knowledge graph for context
            </p>
          </div>
        )}

        {chatMessages.map((msg) => {
          const isStreamingAssistant =
            isQuerying &&
            msg.role === "assistant" &&
            !msg.content &&
            msg.id === chatMessages[chatMessages.length - 1]?.id;

          return (
          <div key={msg.id} className={cn("flex", msg.role === "user" ? "justify-end" : "justify-start")}>
            <div
              className={cn(
                "max-w-[85%]",
                compact ? "text-xs" : "text-sm",
                msg.role === "user"
                  ? cn(
                      "bg-[#304cb2] text-white rounded-tr-sm",
                      compact ? "rounded-xl px-3 py-2" : "rounded-2xl px-4 py-3"
                    )
                  : cn(
                      "bg-slate-100 text-slate-900 border border-slate-200 rounded-tl-sm",
                      compact ? "rounded-xl px-3 py-2" : "rounded-2xl px-4 py-3"
                    )
              )}
            >
              {msg.role === "user" ? (
                <p>{msg.content}</p>
              ) : msg.content ? (
                <div
                  className={cn(
                    "prose  max-w-none",
                    compact
                      ? cn(
                          "text-xs prose-headings:text-xs prose-headings:font-medium prose-headings:leading-snug",
                          "prose-headings:mt-0 prose-headings:mb-0",
                          "prose-p:text-xs prose-p:!my-0 prose-p:leading-snug",
                          "prose-li:text-xs prose-li:my-0 prose-li:py-0 prose-li:leading-snug",
                          "prose-ul:my-0 prose-ul:mt-1 prose-ul:!mb-0 prose-ol:my-0 prose-ol:mt-1 prose-ol:!mb-0",
                          "prose-code:text-[11px]",
                          "prose-hr:!my-1 prose-hr:!border-slate-300",
                          "prose-blockquote:my-1 prose-blockquote:py-0",
                          "[&>*:first-child]:!mt-0 [&>*:last-child]:!mb-0",
                          "[&_hr]:!my-1 [&_p+hr]:!mt-1 [&_hr+p]:!mt-1 [&_ul+hr]:!mt-1 [&_ol+hr]:!mt-1 [&_hr+ul]:!mt-1 [&_hr+ol]:!mt-1"
                        )
                      : "prose-sm"
                  )}
                >
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                </div>
              ) : isStreamingAssistant ? (
                <StreamingIndicator compact={compact} />
              ) : null}
              {msg.role === "assistant" && msg.traversalEvents && msg.traversalEvents.length > 0 && (
                <p
                  className={cn(
                    "text-slate-400 border-t border-slate-200",
                    compact ? "text-[11px] mt-1.5 pt-1.5" : "text-xs mt-2 pt-2"
                  )}
                >
                  {formatTraversalActivityLine(msg.traversalEvents, graphDataSnapshot)}
                </p>
              )}
            </div>
          </div>
          );
        })}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className={cn("border-t border-slate-200 shrink-0", compact ? "p-2" : "p-3")}>
        {apiKeyMissing && (
          <div
            className={cn(
              "flex items-center gap-2 text-xs text-yellow-500",
              compact ? "mb-1.5" : "mb-2"
            )}
          >
            <AlertCircle className="w-3.5 h-3.5 shrink-0" />
            Set ANTHROPIC_API_KEY (higher performance) or LOCAL_LLM_URL (Ollama, lower performance) in .env to enable queries
          </div>
        )}
        <form
          onSubmit={handleSubmit}
          className={cn("flex", compact ? "items-center gap-1.5" : "items-end gap-2")}
        >
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholderText}
            disabled={apiKeyMissing}
            rows={1}
            className={cn(
              "flex-1 m-0 resize-none bg-slate-100 border border-slate-200 text-slate-900 placeholder-slate-400 focus:outline-none focus:border-[#304cb2] focus:ring-1 focus:ring-[#304cb2] disabled:opacity-50 disabled:cursor-not-allowed box-border max-h-[7.5rem]",
              compact
                ? "rounded-lg px-2.5 text-xs leading-4 min-h-9 py-[calc((2.25rem-1rem-2px)/2)]"
                : "rounded-xl px-3 text-sm leading-5 min-h-11 py-[calc((2.75rem-1.25rem-2px)/2)]"
            )}
          />
          <button
            type="submit"
            disabled={!input.trim() || isQuerying || apiKeyMissing}
            className={cn(
              "shrink-0 flex items-center justify-center bg-[#304cb2] hover:bg-blue-700 text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed",
              compact ? "h-9 w-9 rounded-lg" : "h-11 w-11 rounded-xl"
            )}
            aria-label="Send message"
          >
            <Send className={cn(compact ? "w-4 h-4" : "w-5 h-5")} aria-hidden />
          </button>
        </form>
      </div>
    </>
  );

  if (layout === "embedded") {
    return (
      <div
        className={cn(
          "h-full gap-0 overflow-hidden flex flex-col",
          showTraversalSidebar && "md:flex-row"
        )}
      >
        <div
          className={cn(
            "flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden",
            showTraversalSidebar && "md:border-r md:border-slate-200"
          )}
        >
          <AircraftSelector
            value={selectedAircraft}
            onChange={setSelectedAircraft}
            fleetDisabled={fleetOptionDisabled}
            variant="bar"
            dense
          />
          {chatBody}
        </div>

        {showTraversalSidebar && (
          <div className="w-full md:w-80 xl:w-96 shrink-0 flex flex-col min-h-0 overflow-hidden border-t md:border-t-0 border-slate-200">
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
            />
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-1 min-h-0 flex-col overflow-y-auto w-full">
      <div className={cn("flex flex-1 min-h-0 flex-col pb-6", MAIN_TAB_CONTENT_FRAME, TAB_PAGE_TOP_INSET)}>
      <div className="shrink-0 mb-3">
        <AircraftSelector
          value={selectedAircraft}
          onChange={setSelectedAircraft}
          fleetDisabled={fleetOptionDisabled}
          variant="inline"
        />
      </div>

      <div
        className={cn(
          "flex-1 min-h-0 flex flex-col gap-4 overflow-hidden",
          showTraversalSidebar && "md:flex-row"
        )}
      >
        <div className={cn("flex-1 min-w-0 min-h-0 flex flex-col rounded-xl overflow-hidden", CARD_SURFACE_B)}>
          {chatBody}
        </div>

        {showTraversalSidebar && (
          <div className="w-full md:w-80 xl:w-96 shrink-0 flex flex-col min-h-[280px] md:min-h-0 min-w-0 overflow-hidden rounded-xl">
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
            />
          </div>
        )}
      </div>
      </div>
    </div>
  );
}

function StreamingIndicator({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-0.5 py-0.5" aria-label="Assistant is typing">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className={cn(
            "bg-slate-400 rounded-full animate-bounce",
            compact ? "w-1 h-1" : "w-1.5 h-1.5"
          )}
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </div>
  );
}
