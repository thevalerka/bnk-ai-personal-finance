import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(cleanup);

// jsdom doesn't implement IntersectionObserver (every real browser does) —
// useAttentionTracking uses it for impression/dwell tracking. A no-op stub
// is enough: tests care that observing a block doesn't crash, not that
// jsdom actually computes real intersection geometry (it can't; there's no
// layout engine).
class StubIntersectionObserver implements IntersectionObserver {
  readonly root = null;
  readonly rootMargin = "";
  readonly thresholds: ReadonlyArray<number> = [];
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }
}
(window as unknown as { IntersectionObserver: unknown }).IntersectionObserver ??=
  StubIntersectionObserver;

// jsdom doesn't implement ResizeObserver either — CandleChart.tsx uses it
// to keep the lightweight-charts instance sized to its container. Same
// no-op-stub reasoning as IntersectionObserver above: tests care that
// observing doesn't crash, not that jsdom computes real layout.
class StubResizeObserver implements ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(window as unknown as { ResizeObserver: unknown }).ResizeObserver ??= StubResizeObserver;

// jsdom doesn't implement matchMedia either — DynamicGrid uses it to gate
// the attention engine's dynamic column spans to desktop widths. jsdom's
// default viewport is 1024x768, so "matches: true" mirrors what a real
// browser would report at that width; tests don't need to actually respond
// to a resize, just get a stable, realistic answer.
(window as unknown as { matchMedia: unknown }).matchMedia ??= (query: string) => ({
  matches: true,
  media: query,
  onchange: null,
  addListener: () => {},
  removeListener: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => false,
});
