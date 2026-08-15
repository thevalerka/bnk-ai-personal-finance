// Country outlines for WorldMap, server-side only. No geo-rendering library
// (deliberate, mirrors ADR-0009's hand-rolled-SVG-charts precedent) — just
// world-atlas's pre-built topology (data) + topojson-client's tiny
// topology->geometry conversion, then a hand-rolled equirectangular
// projection straight to SVG path strings. All of this runs once at module
// load (pure geometry, no per-request cost) and only the resulting path
// strings ever reach the client.
import { feature } from "topojson-client";
import type { Topology, GeometryCollection } from "topojson-specification";
import type { Geometry, Position } from "geojson";
// 50m (not 110m) resolution: the coarser atlas drops small-area countries
// like Singapore/Hong Kong entirely (no shape at all, not just simplified) —
// both are in WORLD_COUNTRIES. Only the derived path strings below ever
// reach the client, so the extra ~650KB of source topology has no bundle cost.
import worldTopology from "world-atlas/countries-50m.json";

export const WORLD_MAP_WIDTH = 960;
export const WORLD_MAP_HEIGHT = 460;

// Crops Antarctica (nothing in WORLD_COUNTRIES lives there) so the
// populated world fills more of the box instead of leaving a blank band.
const LAT_MIN = -56;
const LAT_MAX = 84;

export interface CountryPath {
  isoNumeric: string;
  name: string;
  d: string;
  // Center of the country's largest landmass (by projected bounding-box
  // area, not a true area-weighted centroid — good enough to anchor a %
  // label without the shoelace-formula machinery a real centroid needs).
  // A small/thin country's label can still land outside its own shape;
  // that's an accepted trade-off of the cheap approach, not a bug.
  labelX: number;
  labelY: number;
  // Bounding-box area (px²) of that same largest-landmass ring — lets a
  // renderer skip drawing a text label on a country too small to hold one
  // legibly (WorldMapChart.tsx), without needing its own geometry math.
  labelArea: number;
}

function project([lon, lat]: Position): [number, number] {
  const x = ((lon + 180) / 360) * WORLD_MAP_WIDTH;
  const y = ((LAT_MAX - lat) / (LAT_MAX - LAT_MIN)) * WORLD_MAP_HEIGHT;
  return [x, y];
}

function projectRing(ring: Position[]): [number, number][] {
  return ring.map(project);
}

function ringToPath(points: [number, number][]): string {
  return (
    points.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ") +
    "Z"
  );
}

function ringBBox(points: [number, number][]): { cx: number; cy: number; area: number } {
  const xs = points.map(([x]) => x);
  const ys = points.map(([, y]) => y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  return { cx: (minX + maxX) / 2, cy: (minY + maxY) / 2, area: (maxX - minX) * (maxY - minY) };
}

interface RingsResult {
  path: string;
  labelX: number;
  labelY: number;
  labelArea: number;
}

function geometryToRings(geometry: Geometry): RingsResult {
  const outerRings: Position[][] =
    geometry.type === "Polygon"
      ? [geometry.coordinates[0]]
      : geometry.type === "MultiPolygon"
        ? geometry.coordinates.map((polygon) => polygon[0])
        : [];
  const allRings: Position[][] =
    geometry.type === "Polygon"
      ? geometry.coordinates
      : geometry.type === "MultiPolygon"
        ? geometry.coordinates.flat()
        : [];

  const path = allRings.map((ring) => ringToPath(projectRing(ring))).join(" ");

  let best = { cx: WORLD_MAP_WIDTH / 2, cy: WORLD_MAP_HEIGHT / 2, area: 0 };
  for (const ring of outerRings) {
    const bbox = ringBBox(projectRing(ring));
    if (bbox.area > best.area) best = bbox;
  }
  return { path, labelX: best.cx, labelY: best.cy, labelArea: best.area };
}

export const COUNTRY_PATHS: CountryPath[] = (() => {
  const topology = worldTopology as unknown as Topology;
  const countries = topology.objects.countries as GeometryCollection;
  const collection = feature(topology, countries);

  // The atlas isn't strictly one feature per ISO code: small territories
  // (e.g. "Ashmore and Cartier Is.") share their parent country's code as a
  // separate feature, and a handful of disputed regions (Kosovo, Somaliland,
  // N. Cyprus, ...) carry no ISO code at all. Merge same-code features into
  // one path (both landmasses render, one fill; the label anchors to
  // whichever merged part has the largest bounding box) and drop the
  // codeless ones — they can't match anything in WORLD_COUNTRIES and would
  // otherwise collide on React key `undefined`.
  const byIso = new Map<
    string,
    { name: string; parts: string[]; labelX: number; labelY: number; labelArea: number }
  >();
  for (const f of collection.features) {
    const isoNumeric = f.id === undefined || f.id === null ? null : String(f.id);
    if (!isoNumeric) continue;
    const name = (f.properties as { name?: string } | null)?.name ?? "";
    const { path, labelX, labelY, labelArea } = geometryToRings(f.geometry);
    const existing = byIso.get(isoNumeric);
    if (existing) {
      existing.parts.push(path);
      if (labelArea > existing.labelArea) {
        existing.labelX = labelX;
        existing.labelY = labelY;
        existing.labelArea = labelArea;
      }
    } else {
      byIso.set(isoNumeric, { name, parts: [path], labelX, labelY, labelArea });
    }
  }

  return Array.from(
    byIso.entries(),
  ).map(([isoNumeric, { name, parts, labelX, labelY, labelArea }]) => ({
    isoNumeric,
    name,
    d: parts.join(" "),
    labelX,
    labelY,
    labelArea,
  }));
})();
