import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Block, BlockSkeleton, Unavailable } from "../Block";

describe("Block", () => {
  it("renders a title and source badge", () => {
    render(
      <Block title="Quotes" source="FRED">
        <p>content</p>
      </Block>,
    );
    expect(screen.getByRole("heading", { name: "Quotes" })).toBeInTheDocument();
    expect(screen.getByText("FRED")).toBeInTheDocument();
    expect(screen.getByText("content")).toBeInTheDocument();
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
