import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, expect, it, beforeEach } from "vitest";

import { PanelPrefsProvider, usePanelState, useDeletedPanels } from "../PanelPrefs";

function Probe({ id }: { id: string }) {
  const { state, setState } = usePanelState(id);
  return (
    <div>
      <span data-testid="state">{state}</span>
      <button onClick={() => setState("deleted")}>delete</button>
      <button onClick={() => setState("expanded")}>expand</button>
      <button onClick={() => setState("normal")}>restore</button>
    </div>
  );
}

function DeletedList() {
  const deleted = useDeletedPanels();
  return <span data-testid="deleted">{deleted.map((p) => p.id).join(",")}</span>;
}

beforeEach(() => {
  window.localStorage.clear();
});

describe("PanelPrefs", () => {
  it("defaults to normal for a panel with no saved preference", () => {
    render(
      <PanelPrefsProvider>
        <Probe id="quotes" />
      </PanelPrefsProvider>,
    );
    expect(screen.getByTestId("state")).toHaveTextContent("normal");
  });

  it("persists a choice across a fresh provider mount (simulating a reload)", () => {
    const { unmount } = render(
      <PanelPrefsProvider>
        <Probe id="news" />
      </PanelPrefsProvider>,
    );
    fireEvent.click(screen.getByText("delete"));
    expect(screen.getByTestId("state")).toHaveTextContent("deleted");
    unmount();

    render(
      <PanelPrefsProvider>
        <Probe id="news" />
      </PanelPrefsProvider>,
    );
    // The provider hydrates from localStorage in an effect, not on the
    // first render (server/client-mismatch-safe, same as ThemeToggle) —
    // flush effects before asserting.
    act(() => {});
    expect(screen.getByTestId("state")).toHaveTextContent("deleted");
  });

  it("setting back to normal removes the saved override rather than storing it", () => {
    render(
      <PanelPrefsProvider>
        <Probe id="calendar" />
      </PanelPrefsProvider>,
    );
    fireEvent.click(screen.getByText("expand"));
    expect(JSON.parse(window.localStorage.getItem("amt-panel-prefs") ?? "{}")).toEqual({
      calendar: "expanded",
    });

    fireEvent.click(screen.getByText("restore"));
    expect(JSON.parse(window.localStorage.getItem("amt-panel-prefs") ?? "{}")).toEqual({});
  });

  it("useDeletedPanels lists only panels currently in the deleted state", () => {
    render(
      <PanelPrefsProvider>
        <Probe id="heatmap" />
        <DeletedList />
      </PanelPrefsProvider>,
    );
    expect(screen.getByTestId("deleted")).toHaveTextContent("");

    fireEvent.click(screen.getByText("delete"));
    expect(screen.getByTestId("deleted")).toHaveTextContent("heatmap");
  });
});
