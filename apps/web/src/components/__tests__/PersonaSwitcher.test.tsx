import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PersonaSwitcher } from "../PersonaSwitcher";
import { fetchMe, fetchPersonas, viewAsPersona } from "@/lib/attention";

vi.mock("@/lib/attention", () => ({
  fetchMe: vi.fn(),
  fetchPersonas: vi.fn(),
  viewAsPersona: vi.fn(),
  resetProfile: vi.fn(),
}));

const mockedFetchMe = vi.mocked(fetchMe);
const mockedFetchPersonas = vi.mocked(fetchPersonas);
const mockedViewAsPersona = vi.mocked(viewAsPersona);

const PERSONAS = [
  { name: "macro", label: "Macro", description: "Rates and curve-obsessed." },
  { name: "equity_pm", label: "Equity PM", description: "Sector rotation." },
];

describe("PersonaSwitcher", () => {
  it("shows Default until a persona is loaded", async () => {
    mockedFetchMe.mockResolvedValue({ profile_id: "x", persona: null, layout: { blocks: [] } });
    mockedFetchPersonas.mockResolvedValue(PERSONAS);

    render(<PersonaSwitcher />);
    expect(screen.getByText("Default")).toBeInTheDocument();
  });

  it("opens the menu and lists every persona", async () => {
    mockedFetchMe.mockResolvedValue({ profile_id: "x", persona: null, layout: { blocks: [] } });
    mockedFetchPersonas.mockResolvedValue(PERSONAS);

    render(<PersonaSwitcher />);
    await waitFor(() => expect(mockedFetchPersonas).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: /view as/i }));
    expect(screen.getByText("Macro")).toBeInTheDocument();
    expect(screen.getByText("Equity PM")).toBeInTheDocument();
  });

  it("reflects the current persona from /profile/me", async () => {
    mockedFetchMe.mockResolvedValue({ profile_id: "x", persona: "macro", layout: { blocks: [] } });
    mockedFetchPersonas.mockResolvedValue(PERSONAS);

    render(<PersonaSwitcher />);
    await waitFor(() => expect(screen.getByText("Macro")).toBeInTheDocument());
  });

  it("calls viewAsPersona when a persona is selected", async () => {
    mockedFetchMe.mockResolvedValue({ profile_id: "x", persona: null, layout: { blocks: [] } });
    mockedFetchPersonas.mockResolvedValue(PERSONAS);
    mockedViewAsPersona.mockResolvedValue({
      profile_id: "y",
      persona: "macro",
      layout: { blocks: [] },
    });
    // jsdom's location.reload isn't spy-able directly (non-configurable) and
    // a real reload would throw "Not implemented: navigation" anyway.
    const reload = vi.fn();
    Object.defineProperty(window, "location", {
      writable: true,
      value: { ...window.location, reload },
    });

    render(<PersonaSwitcher />);
    await waitFor(() => expect(mockedFetchPersonas).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: /view as/i }));
    fireEvent.click(screen.getByText("Macro"));

    await waitFor(() => expect(mockedViewAsPersona).toHaveBeenCalledWith("macro"));
  });
});
