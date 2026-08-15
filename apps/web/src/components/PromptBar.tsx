"use client";

import { useState, type FormEvent } from "react";
import { streamAgentTurn, type ChartSpec, type ChatMessage } from "@/lib/agent";
import { PriceHistoryChart } from "./PriceHistoryChart";
import styles from "./PromptBar.module.css";

interface Turn {
  role: "user" | "assistant";
  content: string;
  toolCalls?: string[];
  chart?: ChartSpec;
  isError?: boolean;
}

const MAX_HISTORY = 20;

// The agent loop itself lives entirely server-side (apps/api/app/agent/,
// docs/PLAN.md section 5.1) — this component is only a streaming SSE
// client + renderer. add_block/set_focus mutating the dashboard is
// reflected here by asking DynamicGrid to refetch /profile/layout
// immediately (a "mutation" event) rather than waiting out its normal 30s
// poll — see the matching listener in DynamicGrid.tsx.
export function PromptBar() {
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isOpen, setIsOpen] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const message = input.trim();
    if (!message || isStreaming) return;

    const history: ChatMessage[] = turns
      .slice(-MAX_HISTORY)
      .map((t) => ({ role: t.role, content: t.content }));

    setInput("");
    setIsOpen(true);
    setIsStreaming(true);
    setTurns((prev) => [...prev, { role: "user", content: message }, { role: "assistant", content: "" }]);

    const toolCalls: string[] = [];
    let chart: ChartSpec | undefined;

    const updateLastTurn = (patch: Partial<Turn>) => {
      setTurns((prev) => {
        const next = [...prev];
        next[next.length - 1] = { ...next[next.length - 1], ...patch };
        return next;
      });
    };

    for await (const evt of streamAgentTurn(message, history)) {
      switch (evt.event) {
        case "text":
          setTurns((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            next[next.length - 1] = { ...last, content: last.content + evt.data.text };
            return next;
          });
          break;
        case "tool_call":
          toolCalls.push(evt.data.name);
          break;
        case "chart":
          chart = evt.data;
          break;
        case "mutation":
          window.dispatchEvent(new CustomEvent("amt:layout-refresh"));
          break;
        case "error":
          updateLastTurn({ content: evt.data.message, isError: true });
          break;
        case "done":
          updateLastTurn({
            toolCalls: toolCalls.length > 0 ? [...toolCalls] : undefined,
            chart,
          });
          break;
      }
    }
    setIsStreaming(false);
  }

  function handleClear() {
    setTurns([]);
    setIsOpen(false);
  }

  return (
    <div className={styles.wrapper}>
      <form className={styles.promptBar} onSubmit={handleSubmit}>
        <svg
          className={styles.promptIcon}
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M11 4a7 7 0 1 0 4.9 12.02l4.54 4.54 1.41-1.41-4.54-4.54A7 7 0 0 0 11 4Zm-5 7a5 5 0 0 1 10 0 5 5 0 0 1-10 0Z"
            fill="currentColor"
          />
        </svg>
        <input
          aria-label="Ask the terminal"
          className={styles.promptInput}
          placeholder="Ask the terminal — e.g. &quot;why is the curve steepening?&quot;"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onFocus={() => turns.length > 0 && setIsOpen(true)}
          disabled={isStreaming}
        />
      </form>

      {isOpen && turns.length > 0 && (
        <div className={styles.panel} role="log" aria-live="polite">
          <div className={styles.panelHeader}>
            <span>Terminal</span>
            <div className={styles.panelActions}>
              <button type="button" className={styles.panelButton} onClick={handleClear}>
                Clear
              </button>
              <button
                type="button"
                className={styles.panelButton}
                aria-label="Close"
                onClick={() => setIsOpen(false)}
              >
                ×
              </button>
            </div>
          </div>
          <div className={styles.messages}>
            {turns.map((turn, i) => (
              <div
                key={i}
                className={turn.role === "user" ? styles.userTurn : styles.assistantTurn}
              >
                <div className={turn.isError ? styles.errorText : styles.turnText}>
                  {turn.content || (isStreaming && i === turns.length - 1 ? "…" : "")}
                </div>
                {turn.chart && (
                  <div className={styles.chartWrap}>
                    <div className={styles.chartTitle}>{turn.chart.title}</div>
                    <PriceHistoryChart candles={turn.chart.candles} />
                  </div>
                )}
                {turn.toolCalls && turn.toolCalls.length > 0 && (
                  <div className={styles.sources}>via {turn.toolCalls.join(", ")}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
