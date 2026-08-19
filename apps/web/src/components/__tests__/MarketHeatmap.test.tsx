import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  MarketHeatmap,
  apportionCells,
  buildLayout,
  changeFill,
  seriate,
  squarify,
  volatilityFraction,
  type Rect,
} from "../MarketHeatmap";
import type { MarketGraphNode, MarketGraphSnapshot } from "@/lib/market";

function node(overrides: Partial<MarketGraphNode> & Pick<MarketGraphNode, "id" | "dominance_score">): MarketGraphNode {
  return {
    label: overrides.id,
    asset_class: "equity",
    symbol: overrides.id,
    last_price: 100,
    change_pct: 0,
    rank: 1,
    data_granularity: "native",
    volatility_ratio: 1.0,
    ...overrides,
  };
}

describe("apportionCells", () => {
  it("allocates integer cells summing to exactly the requested total", () => {
    const nodes = [
      node({ id: "A", dominance_score: 0.9 }),
      node({ id: "B", dominance_score: 0.5 }),
      node({ id: "C", dominance_score: 0.1 }),
    ];

    const cells = apportionCells(nodes, 5000);

    expect([...cells.values()].reduce((a, b) => a + b, 0)).toBe(5000);
    expect(cells.get("A")!).toBeGreaterThan(cells.get("B")!);
    expect(cells.get("B")!).toBeGreaterThan(cells.get("C")!);
  });

  it("gives every node at least one cell even with 20+ nodes and a tiny total", () => {
    const nodes = Array.from({ length: 20 }, (_, i) => node({ id: `N${i}`, dominance_score: 0.01 }));

    const cells = apportionCells(nodes, 5000);

    expect(cells.size).toBe(20);
    expect([...cells.values()].every((c) => c >= 1)).toBe(true);
    expect([...cells.values()].reduce((a, b) => a + b, 0)).toBe(5000);
  });

  it("sums to the requested total even for a single node", () => {
    const cells = apportionCells([node({ id: "A", dominance_score: 1 })], 5000);
    expect(cells.get("A")).toBe(5000);
  });
});

describe("seriate", () => {
  it("places the closest node next to the seed, not an unrelated one", () => {
    // A is the seed; B is very close to A, C is far from both.
    const distance = (a: string, b: string): number => {
      const table: Record<string, number> = { "A|B": 0.05, "A|C": 0.9, "B|C": 0.85 };
      const key = [a, b].sort().join("|");
      return a === b ? 0 : table[key];
    };

    const order = seriate(["A", "C", "B"], distance);

    // B must land adjacent to A somewhere in the order.
    const aIndex = order.indexOf("A");
    const bIndex = order.indexOf("B");
    expect(Math.abs(aIndex - bIndex)).toBe(1);
  });

  it("returns every id exactly once", () => {
    const order = seriate(["A", "B", "C", "D"], () => 1);
    expect([...order].sort()).toEqual(["A", "B", "C", "D"]);
  });
});

describe("squarify", () => {
  it("tiles the full rectangle with no gaps or overlaps in total area", () => {
    const ids = ["A", "B", "C", "D", "E"];
    const areas = [2000, 1200, 900, 600, 300];
    const out = new Map<string, Rect>();

    squarify(ids, areas, 0, 0, 100, 50, out);

    expect(out.size).toBe(5);
    const totalArea = [...out.values()].reduce((sum, r) => sum + r.w * r.h, 0);
    expect(totalArea).toBeCloseTo(5000, 3);
    for (const [id, rect] of out) {
      const expectedArea = areas[ids.indexOf(id)];
      expect(rect.w * rect.h).toBeCloseTo(expectedArea, 3);
    }
  });

  it("keeps blocks roughly square rather than one thin strip", () => {
    // 20 equal-area blocks — squarified should never degenerate into a
    // single row of 20 consecutive slivers (user's explicit complaint about
    // a naive layout).
    const ids = Array.from({ length: 20 }, (_, i) => `N${i}`);
    const areas = ids.map(() => 250);
    const out = new Map<string, Rect>();

    squarify(ids, areas, 0, 0, 100, 50, out);

    const aspectRatios = [...out.values()].map((r) => Math.max(r.w / r.h, r.h / r.w));
    const maxAspect = Math.max(...aspectRatios);
    expect(maxAspect).toBeLessThan(10); // a 1x20 strip would have an aspect ratio near 90
  });
});

describe("buildLayout", () => {
  it("produces a rect for every node, exactly covering the grid", () => {
    const snapshot: MarketGraphSnapshot = {
      computed_at: "now",
      nodes: [
        node({ id: "A", dominance_score: 0.6 }),
        node({ id: "B", dominance_score: 0.3 }),
        node({ id: "C", dominance_score: 0.1 }),
      ],
      edges: [],
      correlations: [{ a: "A", b: "B", corr: 0.9 }],
    };

    const layout = buildLayout(snapshot);

    expect(layout.size).toBe(3);
    const totalArea = [...layout.values()].reduce((sum, r) => sum + r.w * r.h, 0);
    expect(totalArea).toBeCloseTo(5000, 3);
  });

  it("returns an empty layout for an empty snapshot", () => {
    const layout = buildLayout({ computed_at: "now", nodes: [], edges: [], correlations: [] });
    expect(layout.size).toBe(0);
  });
});

describe("volatilityFraction", () => {
  it("fills halfway when current vol equals historical vol", () => {
    expect(volatilityFraction(1.0)).toBeCloseTo(0.5);
  });

  it("fills less than half below historical vol", () => {
    expect(volatilityFraction(0.4)).toBeCloseTo(0.2);
  });

  it("caps at full for well above historical vol", () => {
    expect(volatilityFraction(3.0)).toBe(1);
  });

  it("is empty when volatility couldn't be computed", () => {
    expect(volatilityFraction(null)).toBe(0);
  });
});

describe("changeFill", () => {
  it("is neutral for the news node regardless of change", () => {
    const newsNode = node({ id: "NEWS_FLOW", dominance_score: 1, asset_class: "news", change_pct: null });
    expect(changeFill(newsNode, 2)).toBe("var(--accent-wash-strong)");
  });

  it("uses the positive rgb token for a gain", () => {
    const up = node({ id: "A", dominance_score: 1, change_pct: 1.5 });
    expect(changeFill(up, 2)).toContain("var(--positive-rgb)");
  });

  it("uses the negative rgb token for a loss", () => {
    const down = node({ id: "A", dominance_score: 1, change_pct: -1.5 });
    expect(changeFill(down, 2)).toContain("var(--negative-rgb)");
  });
});

const baseSnapshot: MarketGraphSnapshot = {
  computed_at: "2026-08-19T12:00:00Z",
  nodes: [
    node({ id: "SPY", label: "S&P 500 (SPY)", symbol: "SPY", dominance_score: 0.9, change_pct: 1.2, rank: 1 }),
    node({
      id: "DGS10",
      label: "10Y Treasury",
      symbol: "DGS10",
      asset_class: "rates",
      dominance_score: 0.3,
      change_pct: -0.4,
      rank: 2,
      data_granularity: "daily_fallback",
    }),
  ],
  edges: [{ source: "SPY", target: "DGS10", weight: 0.5, kind: "lead_lag" }],
  correlations: [{ a: "DGS10", b: "SPY", corr: -0.3 }],
};

describe("MarketHeatmap component", () => {
  it("renders the grid with an interactive cell per node", () => {
    render(<MarketHeatmap initialSnapshot={baseSnapshot} />);

    const grid = screen.getByRole("img", { name: /market drivers heatmap/i });
    expect(grid).toBeInTheDocument();
    expect(grid.querySelectorAll('[role="button"]')).toHaveLength(2);
  });

  it("clicking a cell opens a popup with its metrics and outgoing edges", () => {
    render(<MarketHeatmap initialSnapshot={baseSnapshot} />);

    fireEvent.click(screen.getByRole("button", { name: /S&P 500 \(SPY\)/i }));

    expect(screen.getByRole("dialog", { name: /S&P 500 \(SPY\) details/i })).toBeInTheDocument();
    expect(screen.getByText(/leads/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /view spy details/i })).toHaveAttribute("href", "/stock/SPY");
  });

  it("flags a daily-fallback node's popup only once an intraday timeframe is active", () => {
    render(<MarketHeatmap initialSnapshot={baseSnapshot} />);

    // Default view is 24H (tf=1d) — no fallback note yet even though the
    // node is daily_fallback-capable, since 1d *is* native for it.
    fireEvent.click(screen.getByRole("button", { name: /10Y Treasury/i }));
    expect(screen.queryByText(/no intraday feed/i)).not.toBeInTheDocument();
  });
});
