import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NewsList } from "../NewsList";
import { fetchNews } from "@/lib/market";

vi.mock("@/lib/market", () => ({
  fetchNews: vi.fn(),
}));

const mockedFetchNews = vi.mocked(fetchNews);

describe("NewsList", () => {
  it("renders headlines with a link to the source", async () => {
    mockedFetchNews.mockResolvedValue([
      {
        id: "1",
        ts: new Date().toISOString(),
        headline: "Fed holds rates steady",
        url: "https://example.com/1",
        source: "finnhub",
        tickers: [],
        topics: [],
      },
    ]);

    render(await NewsList());

    const link = screen.getByRole("link", { name: /fed holds rates steady/i });
    expect(link).toHaveAttribute("href", "https://example.com/1");
  });

  it("shows an unavailable message when no news provider is reachable", async () => {
    mockedFetchNews.mockResolvedValue(null);

    render(await NewsList());

    expect(screen.getByText(/news unavailable/i)).toBeInTheDocument();
  });
});
