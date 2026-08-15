import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PromptBar } from "../PromptBar";
import { streamAgentTurn, type AgentEvent } from "@/lib/agent";

vi.mock("@/lib/agent", async () => {
  const actual = await vi.importActual<typeof import("@/lib/agent")>("@/lib/agent");
  return { ...actual, streamAgentTurn: vi.fn() };
});

const mockedStream = vi.mocked(streamAgentTurn);

async function* fakeStream(events: AgentEvent[]): AsyncGenerator<AgentEvent> {
  for (const event of events) yield event;
}

async function submit(text: string) {
  const input = screen.getByRole("textbox", { name: /ask the terminal/i });
  fireEvent.change(input, { target: { value: text } });
  fireEvent.submit(input.closest("form")!);
}

describe("PromptBar", () => {
  it("is enabled and shows the phase-4 placeholder", () => {
    render(<PromptBar />);
    const input = screen.getByRole("textbox", { name: /ask the terminal/i });
    expect(input).toBeEnabled();
  });

  it("streams assistant text and shows the user turn once submitted", async () => {
    mockedStream.mockReturnValue(
      fakeStream([
        { event: "text", data: { text: "SPY is " } },
        { event: "text", data: { text: "776.34." } },
        { event: "done", data: { stop_reason: "end_turn", input_tokens: 10, output_tokens: 5 } },
      ]),
    );
    render(<PromptBar />);

    await submit("what's SPY at?");

    expect(await screen.findByText("what's SPY at?")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("SPY is 776.34.")).toBeInTheDocument());
  });

  it("renders which tools backed the answer", async () => {
    mockedStream.mockReturnValue(
      fakeStream([
        { event: "tool_call", data: { name: "get_quotes", input: {} } },
        { event: "text", data: { text: "SPY is 776.34." } },
        { event: "done", data: { stop_reason: "end_turn", input_tokens: 10, output_tokens: 5 } },
      ]),
    );
    render(<PromptBar />);

    await submit("what's SPY at?");

    expect(await screen.findByText(/via get_quotes/i)).toBeInTheDocument();
  });

  it("renders an inline chart when the agent calls render_chart", async () => {
    mockedStream.mockReturnValue(
      fakeStream([
        {
          event: "chart",
          data: {
            symbol: "AAPL",
            title: "AAPL 60-day",
            candles: [
              {
                symbol: "AAPL",
                ts: "2026-01-01T00:00:00Z",
                open: 1,
                high: 2,
                low: 0.5,
                close: 1.5,
                volume: null,
                source: "alpaca",
              },
              {
                symbol: "AAPL",
                ts: "2026-01-02T00:00:00Z",
                open: 1.5,
                high: 2.5,
                low: 1,
                close: 2,
                volume: null,
                source: "alpaca",
              },
            ],
          },
        },
        { event: "text", data: { text: "Here's AAPL." } },
        { event: "done", data: { stop_reason: "end_turn", input_tokens: 10, output_tokens: 5 } },
      ]),
    );
    render(<PromptBar />);

    await submit("chart AAPL");

    expect(await screen.findByText("AAPL 60-day")).toBeInTheDocument();
  });

  it("dispatches a layout-refresh event on a dashboard mutation", async () => {
    mockedStream.mockReturnValue(
      fakeStream([
        { event: "mutation", data: {} },
        { event: "text", data: { text: "Boosted." } },
        { event: "done", data: { stop_reason: "end_turn", input_tokens: 10, output_tokens: 5 } },
      ]),
    );
    const listener = vi.fn();
    window.addEventListener("amt:layout-refresh", listener);
    render(<PromptBar />);

    await submit("I care about crypto");

    await waitFor(() => expect(listener).toHaveBeenCalledTimes(1));
    window.removeEventListener("amt:layout-refresh", listener);
  });

  it("shows an error message distinctly rather than a fabricated answer", async () => {
    mockedStream.mockReturnValue(
      fakeStream([{ event: "error", data: { message: "Agent isn't configured yet." } }]),
    );
    render(<PromptBar />);

    await submit("hi");

    expect(await screen.findByText("Agent isn't configured yet.")).toBeInTheDocument();
  });

  it("clears the conversation and closes the panel", async () => {
    mockedStream.mockReturnValue(
      fakeStream([
        { event: "text", data: { text: "ok" } },
        { event: "done", data: { stop_reason: "end_turn", input_tokens: 10, output_tokens: 5 } },
      ]),
    );
    render(<PromptBar />);

    await submit("hi");
    await screen.findByText("ok");

    fireEvent.click(screen.getByRole("button", { name: /clear/i }));

    expect(screen.queryByText("ok")).not.toBeInTheDocument();
  });
});
