import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { DynamicGrid } from "../DynamicGrid";
import { ExplainPanelProvider } from "../ExplainPanel";
import { PanelPrefsProvider } from "../PanelPrefs";
import { fetchLayout } from "@/lib/attention";

vi.mock("@/lib/attention", () => ({
  fetchLayout: vi.fn(),
}));

const mockedFetchLayout = vi.mocked(fetchLayout);

beforeEach(() => {
  window.localStorage.clear();
});

function renderGrid() {
  return render(
    <PanelPrefsProvider>
      <ExplainPanelProvider>
        <div style={{ display: "grid" }}>
          <DynamicGrid
            quotes={<div data-testid="quotes-content">quotes</div>}
            yieldCurve={<div data-testid="yield-curve-content">yield curve</div>}
            heatmap={<div data-testid="heatmap-content">heatmap</div>}
          />
        </div>
      </ExplainPanelProvider>
    </PanelPrefsProvider>,
  );
}

describe("DynamicGrid", () => {
  it("renders all three blocks with the even default split before layout loads", () => {
    mockedFetchLayout.mockResolvedValue(null);
    renderGrid();

    expect(screen.getByTestId("quotes-content")).toBeInTheDocument();
    expect(screen.getByTestId("yield-curve-content")).toBeInTheDocument();
    expect(screen.getByTestId("heatmap-content")).toBeInTheDocument();

    const quotesWrapper = screen.getByTestId("quotes-content").parentElement;
    expect(quotesWrapper).toHaveStyle({ gridColumn: "span 4" });
  });

  it("applies the fetched layout's column spans once it resolves", async () => {
    mockedFetchLayout.mockResolvedValue({
      blocks: [
        { block_type: "quotes", nodes: [], raw_score: 0, area_weight: 0.1, columns: 2, priority: 3 },
        {
          block_type: "yield_curve",
          nodes: [],
          raw_score: 10,
          area_weight: 0.8,
          columns: 8,
          priority: 1,
        },
        { block_type: "heatmap", nodes: [], raw_score: 0, area_weight: 0.1, columns: 2, priority: 2 },
      ],
    });

    renderGrid();

    await waitFor(() => {
      const yieldCurveWrapper = screen.getByTestId("yield-curve-content").parentElement;
      expect(yieldCurveWrapper).toHaveStyle({ gridColumn: "span 8" });
    });
    expect(screen.getByTestId("quotes-content").parentElement).toHaveStyle({ gridColumn: "span 2" });
    expect(screen.getByTestId("heatmap-content").parentElement).toHaveStyle({ gridColumn: "span 2" });
  });

  it("skips a block entirely once the user deletes it, rather than leaving an empty cell", () => {
    mockedFetchLayout.mockResolvedValue(null);
    window.localStorage.setItem("amt-panel-prefs", JSON.stringify({ heatmap: "deleted" }));

    renderGrid();

    expect(screen.getByTestId("quotes-content")).toBeInTheDocument();
    expect(screen.queryByTestId("heatmap-content")).not.toBeInTheDocument();
  });

  it("overrides the attention-driven span with a full-width one once the user manually expands a block", () => {
    mockedFetchLayout.mockResolvedValue(null);
    window.localStorage.setItem("amt-panel-prefs", JSON.stringify({ quotes: "expanded" }));

    renderGrid();

    expect(screen.getByTestId("quotes-content").parentElement).toHaveStyle({
      gridColumn: "1 / -1",
    });
  });
});
