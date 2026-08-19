import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

import { ResetViewButton } from "../ResetViewButton";
import { resetProfile } from "@/lib/attention";

vi.mock("@/lib/attention", () => ({
  resetProfile: vi.fn(),
}));

const mockedResetProfile = vi.mocked(resetProfile);

describe("ResetViewButton", () => {
  beforeEach(() => {
    window.localStorage.setItem("amt-panel-prefs", JSON.stringify({ heatmap: "deleted" }));
  });

  it("resets the profile, clears saved panel prefs, and reloads on success", async () => {
    mockedResetProfile.mockResolvedValue({ profile_id: "y", persona: null, layout: { blocks: [] } });
    const reload = vi.fn();
    Object.defineProperty(window, "location", {
      writable: true,
      value: { ...window.location, reload },
    });

    render(<ResetViewButton />);
    fireEvent.click(screen.getByRole("button", { name: /reset view/i }));

    await waitFor(() => expect(mockedResetProfile).toHaveBeenCalled());
    expect(window.localStorage.getItem("amt-panel-prefs")).toBeNull();
    await waitFor(() => expect(reload).toHaveBeenCalled());
  });

  it("clears local panel prefs but does not reload when the backend reset fails", async () => {
    mockedResetProfile.mockResolvedValue(null);
    const reload = vi.fn();
    Object.defineProperty(window, "location", {
      writable: true,
      value: { ...window.location, reload },
    });

    render(<ResetViewButton />);
    fireEvent.click(screen.getByRole("button", { name: /reset view/i }));

    await waitFor(() => expect(mockedResetProfile).toHaveBeenCalled());
    expect(window.localStorage.getItem("amt-panel-prefs")).toBeNull();
    expect(reload).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByRole("button", { name: /reset view/i })).not.toBeDisabled());
  });
});
