// Client-side SSE for the Phase 4 agent (apps/api `/agent/stream`,
// docs/PLAN.md section 5.1). Native EventSource can't do a credentialed
// POST with a JSON body, so this parses Server-Sent Events by hand off a
// streamed fetch response — same credentialed-cross-subdomain reasoning as
// lib/attention.ts's NEXT_PUBLIC_API_PUBLIC_URL split from lib/market.ts.

import type { Candle } from "@/lib/market";

const API_PUBLIC_URL = process.env.NEXT_PUBLIC_API_PUBLIC_URL ?? "http://localhost:8100";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChartSpec {
  symbol: string;
  title: string;
  candles: Candle[];
}

export type AgentEvent =
  | { event: "text"; data: { text: string } }
  | { event: "tool_call"; data: { name: string; input: Record<string, unknown> } }
  | { event: "tool_result"; data: { name: string; result: unknown; is_error: boolean } }
  | { event: "chart"; data: ChartSpec }
  | { event: "mutation"; data: Record<string, never> }
  | {
      event: "done";
      data: { stop_reason: string; input_tokens: number; output_tokens: number };
    }
  | { event: "error"; data: { message: string } };

function parseFrame(raw: string): AgentEvent | null {
  let eventType = "";
  const dataLines: string[] = [];
  for (const line of raw.split("\n")) {
    if (line.startsWith("event: ")) eventType = line.slice("event: ".length);
    else if (line.startsWith("data: ")) dataLines.push(line.slice("data: ".length));
  }
  if (!eventType || dataLines.length === 0) return null;
  try {
    return { event: eventType, data: JSON.parse(dataLines.join("\n")) } as AgentEvent;
  } catch {
    return null;
  }
}

export async function* streamAgentTurn(
  message: string,
  history: ChatMessage[],
): AsyncGenerator<AgentEvent> {
  let response: Response;
  try {
    response = await fetch(`${API_PUBLIC_URL}/agent/stream`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, history }),
    });
  } catch {
    yield { event: "error", data: { message: "Could not reach the agent." } };
    return;
  }

  if (!response.ok) {
    const detail =
      response.status === 503
        ? "Agent isn't configured yet."
        : `Request failed (${response.status}).`;
    yield { event: "error", data: { message: detail } };
    return;
  }
  if (!response.body) {
    yield { event: "error", data: { message: "Streaming isn't supported in this browser." } };
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let sepIndex: number;
      while ((sepIndex = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, sepIndex);
        buffer = buffer.slice(sepIndex + 2);
        const parsed = parseFrame(frame);
        if (parsed) yield parsed;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
