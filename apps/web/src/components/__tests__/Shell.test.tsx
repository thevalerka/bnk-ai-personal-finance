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

  it("renders the prompt bar disabled, per P2's non-functional scope", () => {
    render(
      <PanelPrefsProvider>
        <Shell />
      </PanelPrefsProvider>,
    );
    expect(screen.getByRole("textbox", { name: /ask the terminal/i })).toBeDisabled();
  });
});
