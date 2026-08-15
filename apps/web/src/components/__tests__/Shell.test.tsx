import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Shell } from "../Shell";
import { PanelPrefsProvider } from "../PanelPrefs";

describe("Shell", () => {
  it("renders the brand heading", () => {
    render(
      <PanelPrefsProvider>
        <Shell />
      </PanelPrefsProvider>,
    );
    expect(screen.getByRole("heading", { name: /adaptive markets terminal/i })).toBeInTheDocument();
  });

  it("renders the prompt bar enabled, now that phase 4's agent backs it", () => {
    render(
      <PanelPrefsProvider>
        <Shell />
      </PanelPrefsProvider>,
    );
    expect(screen.getByRole("textbox", { name: /ask the terminal/i })).toBeEnabled();
  });
});
