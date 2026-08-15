import { render, screen, fireEvent } from "@testing-library/react";
import { useEffect } from "react";
import { describe, expect, it, beforeEach } from "vitest";

import { PanelPrefsProvider, useSetPanelState } from "../PanelPrefs";
import { PanelSlot } from "../PanelSlot";

beforeEach(() => {
  window.localStorage.clear();
});

function Driver({ id, state }: { id: string; state: "expanded" | "icon" | "deleted" }) {
  const setState = useSetPanelState();
  // Effect, not a direct render-body call: setState updates the provider's
  // state, and calling it unconditionally during render would re-fire on
  // every resulting re-render (new object identity each time) — an
  // infinite loop. Real callers only ever invoke it from an event handler.
  useEffect(() => {
    setState(id, state);
  }, [id, state, setState]);
  return null;
}

describe("PanelSlot", () => {
  it("renders its children normally by default", () => {
    render(
      <PanelPrefsProvider>
        <PanelSlot id="news" title="News" spanClassName="span-4">
          <p>news content</p>
        </PanelSlot>
      </PanelPrefsProvider>,
    );
    expect(screen.getByText("news content")).toBeInTheDocument();
  });

  it("renders nothing at all when deleted — no empty grid cell left behind", () => {
    const { container } = render(
      <PanelPrefsProvider>
        <Driver id="news" state="deleted" />
        <PanelSlot id="news" title="News" spanClassName="span-4">
          <p>news content</p>
        </PanelSlot>
      </PanelPrefsProvider>,
    );
    expect(screen.queryByText("news content")).not.toBeInTheDocument();
    // Driver itself renders null, so an empty container confirms PanelSlot
    // contributed no DOM node either (not just a hidden/empty div).
    expect(container).toBeEmptyDOMElement();
  });

  it("renders a restorable icon chip instead of its content when minimized", () => {
    render(
      <PanelPrefsProvider>
        <Driver id="news" state="icon" />
        <PanelSlot id="news" title="News" spanClassName="span-4">
          <p>news content</p>
        </PanelSlot>
      </PanelPrefsProvider>,
    );
    expect(screen.queryByText("news content")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /restore news/i })).toBeInTheDocument();
  });

  it("clicking the icon chip restores the panel to normal", () => {
    render(
      <PanelPrefsProvider>
        <Driver id="news" state="icon" />
        <PanelSlot id="news" title="News" spanClassName="span-4">
          <p>news content</p>
        </PanelSlot>
      </PanelPrefsProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: /restore news/i }));
    expect(screen.getByText("news content")).toBeInTheDocument();
  });
});
