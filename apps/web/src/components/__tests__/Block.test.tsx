import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, beforeEach, vi } from "vitest";

import { Block, BlockSkeleton, Unavailable } from "../Block";
import { PanelPrefsProvider } from "../PanelPrefs";

beforeEach(() => {
  window.localStorage.clear();
});

describe("Block", () => {
  it("renders a title and source badge", () => {
    render(
      <PanelPrefsProvider>
        <Block id="quotes" title="Quotes" source="FRED">
          <p>content</p>
        </Block>
      </PanelPrefsProvider>,
    );
    expect(screen.getByRole("heading", { name: "Quotes" })).toBeInTheDocument();
    expect(screen.getByText("FRED")).toBeInTheDocument();
    expect(screen.getByText("content")).toBeInTheDocument();
  });

  it("delete/expand/minimize header controls write to the persisted panel preference", () => {
    render(
      <PanelPrefsProvider>
        <Block id="quotes" title="Quotes">
          <p>content</p>
        </Block>
      </PanelPrefsProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: /expand panel to full width/i }));
    expect(JSON.parse(window.localStorage.getItem("amt-panel-prefs") ?? "{}")).toEqual({
      quotes: "expanded",
    });

    fireEvent.click(screen.getByRole("button", { name: /delete panel/i }));
    expect(JSON.parse(window.localStorage.getItem("amt-panel-prefs") ?? "{}")).toEqual({
      quotes: "deleted",
    });
  });

  it("does not bubble a control click up to an ancestor's onClick (e.g. DynamicGrid's explain-panel trigger)", () => {
    const outerClick = vi.fn();
    render(
      <PanelPrefsProvider>
        <div onClick={outerClick}>
          <Block id="heatmap" title="Sector Heatmap">
            <p>content</p>
          </Block>
        </div>
      </PanelPrefsProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: /expand panel to full width/i }));

    expect(outerClick).not.toHaveBeenCalled();
  });

  it("BlockSkeleton renders the title without content", () => {
    render(<BlockSkeleton title="Loading block" minHeight={180} />);
    expect(screen.getByRole("heading", { name: "Loading block" })).toBeInTheDocument();
  });

  it("Unavailable shows a fallback message, never a fabricated number", () => {
    render(<Unavailable />);
    expect(screen.getByText(/no live data reachable/i)).toBeInTheDocument();
  });
});
