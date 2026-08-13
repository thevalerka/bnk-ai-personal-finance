import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Shell } from "../Shell";

describe("Shell", () => {
  it("renders the brand heading", () => {
    render(<Shell />);
    expect(screen.getByRole("heading", { name: /adaptive markets terminal/i })).toBeInTheDocument();
  });

  it("renders the prompt bar disabled, per P2's non-functional scope", () => {
    render(<Shell />);
    expect(screen.getByRole("textbox", { name: /ask the terminal/i })).toBeDisabled();
  });
});
