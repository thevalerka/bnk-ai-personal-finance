import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ExplainPanelProvider, useExplainPanel } from "../ExplainPanel";
import { fetchExplain } from "@/lib/attention";

vi.mock("@/lib/attention", () => ({
  fetchExplain: vi.fn(),
}));

const mockedFetchExplain = vi.mocked(fetchExplain);

function OpenButton({ nodeId }: { nodeId: string }) {
  const { open } = useExplainPanel();
  return (
    <button onClick={() => open(nodeId)}>open</button>
  );
}

describe("ExplainPanel", () => {
  it("shows the decayed score and source events once opened", async () => {
    mockedFetchExplain.mockResolvedValue({
      node_id: "equities.us_large_cap.technology",
      score: 4.2,
      last_updated: "2026-08-13T00:00:00Z",
      muted: false,
      source_events: [
        {
          kind: "click",
          weight: 2.0,
          ts: new Date().toISOString(),
          node_id: "equities.us_large_cap.technology",
          meta: null,
        },
      ],
    });

    render(
      <ExplainPanelProvider>
        <OpenButton nodeId="equities.us_large_cap.technology" />
      </ExplainPanelProvider>,
    );

    fireEvent.click(screen.getByText("open"));

    await waitFor(() => expect(screen.getByText("4.20")).toBeInTheDocument());
    expect(screen.getByRole("heading", { name: "Equities › Us Large Cap › Technology" })).toBeInTheDocument();
    expect(screen.getByText("Clicked into")).toBeInTheDocument();
  });

  it("closes when the overlay is clicked", async () => {
    mockedFetchExplain.mockResolvedValue({
      node_id: "crypto.majors.btc",
      score: 1.0,
      last_updated: null,
      muted: false,
      source_events: [],
    });

    render(
      <ExplainPanelProvider>
        <OpenButton nodeId="crypto.majors.btc" />
      </ExplainPanelProvider>,
    );

    fireEvent.click(screen.getByText("open"));
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("shows a muted badge when the node is muted", async () => {
    mockedFetchExplain.mockResolvedValue({
      node_id: "equities.us_large_cap.energy_sector",
      score: -6,
      last_updated: "2026-08-13T00:00:00Z",
      muted: true,
      source_events: [],
    });

    render(
      <ExplainPanelProvider>
        <OpenButton nodeId="equities.us_large_cap.energy_sector" />
      </ExplainPanelProvider>,
    );

    fireEvent.click(screen.getByText("open"));
    await waitFor(() => expect(screen.getByText("Muted")).toBeInTheDocument());
  });
});
