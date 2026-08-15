"use client";

import Link from "next/link";
import { useState, type KeyboardEvent } from "react";
import styles from "./WorldMap.module.css";

// Deliberately NOT imported from "@/lib/worldGeo" here: that module also
// pulls in world-atlas's ~650KB topology JSON at module scope, and this is
// a "use client" component — importing anything from worldGeo.ts, even
// just these two constants, would drag the whole raw atlas into the
// client bundle (confirmed: it did, first-load JS jumped 119KB -> 351KB
// before this fix). WorldMap.tsx (Server Component) still imports the
// real constants and passes them down as props instead.

export interface CountryDatum {
  isoNumeric: string;
  name: string;
  d: string;
  labelX: number;
  labelY: number;
  labelArea: number;
  tracked: boolean;
  symbol: string | null;
  price: number | null;
  changePercent: number | null;
  currency: string | null;
  fxLabel: string | null;
  bondYieldPct: number | null;
}

const CLAMP_PCT = 4;

// A landmass smaller than this (projected px², at the 960x460 viewBox) is
// too small to hold a legible label without colliding with a neighbor —
// several small European/East Asian countries (Netherlands, Switzerland,
// Hong Kong, Taiwan, South Korea) sit close enough to bigger ones that
// their % labels overlapped illegibly before this cutoff. The color fill,
// hover tooltip, and click popup are unaffected — only the always-on text
// label is skipped, per country size, not per the value it would show.
const MIN_LABEL_AREA = 150;

function countryFill(pct: number | null): string {
  if (pct === null) return "var(--surface-2)";
  const clamped = Math.max(-CLAMP_PCT, Math.min(CLAMP_PCT, pct));
  const intensity = Math.abs(clamped) / CLAMP_PCT;
  // rgba(var(--x-rgb), alpha): a raw custom property, substituted by the
  // browser at paint time — stays theme-reactive regardless of when this
  // string was built (globals.css: --positive-rgb/--negative-rgb).
  const rgbVar = clamped >= 0 ? "var(--positive-rgb)" : "var(--negative-rgb)";
  return `rgba(${rgbVar}, ${(0.25 + intensity * 0.65).toFixed(2)})`;
}

function formatPct(pct: number | null): string | null {
  if (pct === null) return null;
  return `${pct > 0 ? "+" : ""}${pct.toFixed(1)}%`;
}

export function WorldMapChart({
  countries,
  width,
  height,
}: {
  countries: CountryDatum[];
  width: number;
  height: number;
}) {
  const [selectedIso, setSelectedIso] = useState<string | null>(null);
  const selected = countries.find((c) => c.isoNumeric === selectedIso) ?? null;

  function select(country: CountryDatum) {
    if (!country.tracked) return;
    setSelectedIso(country.isoNumeric);
  }

  function onKeyDown(event: KeyboardEvent<SVGPathElement>, country: CountryDatum) {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      select(country);
    }
  }

  return (
    <div className={styles.wrap}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className={styles.svg}
        role="img"
        aria-label="World map, tracked countries colored and labeled by proxy-index daily change; click a country for details"
      >
        <defs>
          {/* The tiled backdrop (graph-paper grid) — visible behind every
              country shape, most noticeably over open ocean. */}
          <pattern id="worldMapTile" width="24" height="24" patternUnits="userSpaceOnUse">
            <rect width="24" height="24" className={styles.tileCell} />
            <path d="M24 0.5H0.5V24" className={styles.tileLine} fill="none" />
          </pattern>
        </defs>
        <rect x={0} y={0} width={width} height={height} fill="url(#worldMapTile)" />

        {countries.map((country) => {
          const label = country.tracked
            ? `${country.name} (${country.symbol}): ${formatPct(country.changePercent) ?? "no change data"}${
                country.price !== null
                  ? ` — ${country.price.toLocaleString("en-US", { maximumFractionDigits: 2 })}`
                  : ""
              }`
            : `${country.name}: not tracked`;
          const pctLabel =
            country.tracked && country.labelArea >= MIN_LABEL_AREA
              ? formatPct(country.changePercent)
              : null;
          return (
            <g key={country.isoNumeric}>
              <path
                d={country.d}
                className={country.tracked ? styles.countryTracked : styles.country}
                style={{ fill: countryFill(country.tracked ? country.changePercent : null) }}
                tabIndex={country.tracked ? 0 : -1}
                role={country.tracked ? "button" : undefined}
                aria-label={country.tracked ? label : undefined}
                onClick={() => select(country)}
                onKeyDown={(e) => onKeyDown(e, country)}
              >
                <title>{label}</title>
              </path>
              {pctLabel ? (
                <text
                  x={country.labelX}
                  y={country.labelY}
                  className={
                    country.changePercent !== null && country.changePercent < 0
                      ? styles.pctLabelNegative
                      : styles.pctLabelPositive
                  }
                  textAnchor="middle"
                  dominantBaseline="middle"
                  pointerEvents="none"
                >
                  {pctLabel}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>

      <div className={styles.legend} aria-hidden="true">
        <span>−{CLAMP_PCT}%</span>
        <div className={styles.legendBar} />
        <span>+{CLAMP_PCT}%</span>
        <span className={styles.legendNote}>Proxied by each country&apos;s largest US-listed index ETF</span>
      </div>

      {selected ? (
        <div className={styles.popupOverlay} onClick={() => setSelectedIso(null)}>
          <div
            className={styles.popup}
            role="dialog"
            aria-label={`${selected.name} details`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className={styles.popupHeader}>
              <span className={styles.popupEyebrow}>{selected.name}</span>
              <button
                type="button"
                className={styles.popupClose}
                onClick={() => setSelectedIso(null)}
                aria-label="Close"
              >
                ×
              </button>
            </div>

            <div className={styles.popupRow}>
              <span className={styles.popupLabel}>Index ETF</span>
              <span className={styles.popupValue}>
                {selected.symbol}
                {selected.price !== null ? (
                  <>
                    {" "}
                    <span className="tabular-nums">
                      {selected.price.toLocaleString("en-US", { maximumFractionDigits: 2 })}
                    </span>
                  </>
                ) : null}
                {selected.changePercent !== null ? (
                  <span
                    className={`${styles.popupDelta} ${
                      selected.changePercent >= 0 ? styles.popupDeltaUp : styles.popupDeltaDown
                    } tabular-nums`}
                  >
                    {formatPct(selected.changePercent)}
                  </span>
                ) : null}
              </span>
            </div>

            <div className={styles.popupRow}>
              <span className={styles.popupLabel}>Currency vs USD</span>
              <span className={styles.popupValue}>
                {selected.fxLabel ?? <span className={styles.popupUnavailable}>Not available</span>}
              </span>
            </div>

            <div className={styles.popupRow}>
              <span className={styles.popupLabel}>Govt bond yield</span>
              <span className={styles.popupValue}>
                {selected.bondYieldPct !== null ? (
                  <span className="tabular-nums">{selected.bondYieldPct.toFixed(2)}%</span>
                ) : (
                  <span className={styles.popupUnavailable}>Not available</span>
                )}
              </span>
            </div>

            <Link href={`/country/${selected.isoNumeric}`} className={styles.popupDetailLink}>
              View full details, indices &amp; treasury →
            </Link>
          </div>
        </div>
      ) : null}
    </div>
  );
}
