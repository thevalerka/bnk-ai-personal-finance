import { fetchWorldIndices } from "@/lib/market";
import { Unavailable } from "./Block";
import { COUNTRY_PATHS, WORLD_MAP_WIDTH, WORLD_MAP_HEIGHT } from "@/lib/worldGeo";
import { WorldMapChart, type CountryDatum } from "./WorldMapChart";

// Index view only (docs/STATE.md, ADR-0015): map fill/% label come from
// each country's proxy ETF change_percent. Currency/bond-yield (ADR-0016)
// surface in the click popup instead of the map fill itself — three
// simultaneous choropleth scales on one map would fight each other
// visually, and "if available" degradation reads more honestly in a
// popup's labeled rows than as another map color.
export async function WorldMap() {
  const points = await fetchWorldIndices();

  if (!points || points.length === 0) {
    return <Unavailable reason="World map unavailable — no equity quotes reachable." />;
  }

  const byIso = new Map(points.map((p) => [p.iso_numeric, p]));

  const countries: CountryDatum[] = COUNTRY_PATHS.map((shape) => {
    const point = byIso.get(shape.isoNumeric);
    const tracked = Boolean(point?.quote);
    return {
      isoNumeric: shape.isoNumeric,
      name: point?.name ?? shape.name,
      d: shape.d,
      labelX: shape.labelX,
      labelY: shape.labelY,
      labelArea: shape.labelArea,
      tracked,
      symbol: point?.symbol ?? null,
      price: point?.quote?.price ?? null,
      changePercent: point?.quote?.change_percent ?? null,
      currency: point?.currency ?? null,
      fxLabel: point?.fx_label ?? null,
      bondYieldPct: point?.bond_yield_pct ?? null,
    };
  });

  return <WorldMapChart countries={countries} width={WORLD_MAP_WIDTH} height={WORLD_MAP_HEIGHT} />;
}
