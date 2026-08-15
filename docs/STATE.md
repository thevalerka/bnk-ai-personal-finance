# State

Running log of what's done and what's next. Update at the end of every session.
Newest entry first.

---

## 2026-08-15 — Housekeeping: committed and pushed several days of uncommitted work

User re-requested the four features from the entry directly below (earnings
calendar/Polymarket, World Map → country detail pages, Forex, more news
sources) — turned out all four, plus everything back through P3 (attention
engine), were already built, tested, and previously verified live, but had
never been `git commit`ed. `git status` showed 135 files of accumulated
work sitting in the working tree.

Re-verified `make test` (137 api + 1 worker + 57 web) and `make lint`
(ruff, mypy ×2, eslint) still green on the snapshot, then committed it all
in one checkpoint (`6b20a7f`) and pushed to `origin/main`. Excluded two
untracked scratch screenshots (`last.png`, `Screenshot 2026-08-09
125844.png`) not referenced anywhere in code/docs — kept `design-dark.png`
since it's a real cited design reference (`globals.css`, ADR-0014).

Rebuilt and restarted both `amt-api`/`amt-web`; re-confirmed live via curl:
`/market/quote?capability=macro_series` (Forex), `/market/predictions`,
`/market/world`, `/market/news` (now includes `rss_media` alongside
`finnhub`), homepage, and `/country/392` all returning real data / 200s.

**Not done:** no attempt to retroactively split this into per-feature
commits matching each STATE.md entry below — the diffs are too
cross-cutting (e.g. `market.py`/`schemas.py` touched by nearly every entry)
to separate cleanly after the fact. If a clean bisectable history matters
later, it doesn't exist for this range.

**Next:** unchanged — Phase 4, Agent (`docs/PLAN.md` section 7, P4).

---

## 2026-08-14 — Prediction Markets, World Map country pages, Forex panel, CNBC/MarketWatch news

Ninth same-day follow-up, four asks in one message. Full detail in
`docs/DECISIONS.md` ADR-0023/0024/0025.

- **News:** `rss_media` provider (CNBC + MarketWatch RSS, keyless, verified
  live) merged into the news chain.
- **Forex:** new homepage panel, 7 major currency pairs — zero new backend,
  reuses FRED's H.10 FX series already wired for the World Map (ADR-0016).
  `FredProvider.quote()` doesn't compute `change_percent`, so trend/% change
  are computed client-side from the last two candle closes instead.
- **Prediction Markets:** new `PolymarketProvider` + `GET /market/predictions`.
  Checked live first whether Polymarket actually has per-company earnings
  markets — it doesn't, at any real volume. Built the honest version
  instead: real Fed-rate-decision and S&P-direction markets, matching
  `sources.yaml`'s own original macro/FOMC-focused design for this
  provider. Generalized the ADR-0021 cache/budget-bypass helper so
  `fundamentals()` and this new `probability()` share one implementation.
- **World Map → country detail pages:** `/country/[iso]`, one per tracked
  nation — index price history, FX rate, government bond yield (full US
  Treasury curve for the US, reusing the existing `<YieldCurve />`
  component; single OECD benchmark point for everyone else), and a
  sorted list of all 23 tracked countries' indices. Needed **zero new
  backend** — entirely built from `/market/world` + the existing candles
  endpoint. Extracted the stock detail page's CSS into a shared
  `app/detail.module.css` so both drill-down pages match.

**Found and fixed one thing during this pass:** the country page's
"currently viewing" row highlight (`background: var(--surface-2)`) was
nearly invisible against the section's own gradient background — caught
via screenshot before shipping, fixed with a left accent border + bold
accent text instead of relying on a background-color difference alone.

**Known quirk, not fixed (pre-existing, not caused by this session's
changes):** the very first request to a freshly-started `next start`
process sometimes 500s with a generic "Cannot read properties of
undefined" Server Components error; every request after the first succeeds
normally. Reproduced identically on three unrelated pages across today's
sessions, always exactly once right after a cold start, never on a warm
server — looks like a Turbopack/Next warm-up race, not an application bug.
Worth a real restart-time healthcheck before pointing traffic at a fresh
deploy if this ever matters for a real user (a caching layer / load
balancer with a startup probe would absorb it); not chased further here.

**Verified locally:** `make test` (137 api + 1 worker + 57 web, up from
129/1/55) / `make lint` / `make typecheck` / `next build` all green.

**Verified live** (vespersoul.com): predictions/forex/news all confirmed
serving real data via `api.vespersoul.com`; clicked Japan on the real map,
followed the new "View full details" link to `/country/392`, confirmed
real index history/FX/yield and the full indices list.

**Not done / deliberately deferred:** no CPI/jobs/GDP Polymarket markets
found at real volume (keyword list covers them for whenever one appears);
odds aren't attached onto `/market/calendar`'s FOMC entries (a standalone
panel was shipped instead, per `sources.yaml`'s original `attach_to`
design — revisit later if wanted); no per-country news/filings section on
the country page (EDGAR filings are US-ticker-only).

**Next:** unchanged — Phase 4, Agent (`docs/PLAN.md` section 7, P4). Do not
start until the user has reviewed this pass.

---

## 2026-08-14 — Fundamentals expanded: quarterly earnings + ~20 line items; fixed a live stale-cache crash

Eighth same-day follow-up. User asked to also cover quarterly earnings and
report a lot more data than the prior pass's 5-line annual table. Full
detail in `docs/DECISIONS.md` ADR-0022.

**Backend:** `SecEdgarProvider.fundamentals()` now returns both annual
(5 fiscal years) and quarterly (8 quarters) periods in one call —
`FinancialPeriod` grew to ~24 fields: R&D/SG&A/opex, gross/operating/net
margins, EPS diluted+basic, operating cash flow/capex/free cash flow, and
balance sheet (assets/liabilities/equity/cash/long-term debt). Balance-sheet
concepts are "instant" XBRL facts (point-in-time, no duration) — needed a
separate lookup helper from the income-statement figures. Verified live
across all 10 curated tickers which tags exist before adding any of them.

**Found and fixed a real bug live:** restarting `amt-api` with the new
schema crashed `/market/stock/{symbol}` outright — the 24h Redis cache from
the prior pass held `FinancialPeriod` payloads in the old shape, and
`model_validate` threw on the missing new required fields. Fixed with a
cache-key version bump (stale entries just age out, never read again) plus
a `ValidationError`-as-cache-miss guard so the *next* schema change can't
repeat this.

**Frontend:** `CompanyFinancials.tsx` rewritten as a transposed table
(metrics as rows, periods as columns — the standard financial-statement
layout) grouped into Income Statement/Per Share/Cash Flow/Balance Sheet,
rendered as two tables (Annual, Quarterly).

**Verified locally:** `make test` (129 api + 1 worker + 52 web) / `make
lint` / `make typecheck` / `next build` all green.

**Verified live** (vespersoul.com): MSFT — 13 real periods, correct margins,
an honest all-null `interest_expense` (MSFT doesn't tag that concept under
the expected name — a real gap, not a bug); GOOGL spot-checked fresh after
deploy, 13 periods, 200 OK.

**Not done / deliberately deferred:** no derived standalone-Q4 figure (FY
already covers it at the annual grain); no YoY/QoQ delta column;
`Liabilities` stays null for the 2/10 tickers that don't report it rather
than being derived from Assets − Equity.

**Next:** unchanged — Phase 4, Agent (`docs/PLAN.md` section 7, P4). Do not
start until the user has reviewed this pass.

---

## 2026-08-14 — Company financial profile (EDGAR XBRL) on the stock detail page + Tape banner click-through

Seventh same-day follow-up. User asked for a corporate financial profile
(revenue, gross margin, operating expenses, operating income) using EDGAR
filing data, plus click-through from the header's Tape banner (not just the
Quotes/Most-Traded tiles from the pass below). Full detail in
`docs/DECISIONS.md` ADR-0021.

**Backend:** `SecEdgarProvider.fundamentals()` (new) pulls 5 years of annual
(10-K only) revenue/gross-profit/opex/operating-income/net-income from
EDGAR's XBRL `companyfacts` endpoint, with tag fallback chains verified live
against 5 real companies first (AAPL/NVDA/TSLA/SOFI/PLTR — us-gaap tag names
genuinely vary; SOFI has no gross-profit/opex concept at all, a real gap,
not a bug). Deliberately bypasses Router (doesn't fit quote/candles/news/
calendar) via a new narrow `FundamentalsProvider` Protocol, but still gets a
manual cache (24h)+budget check so it doesn't skip the same discipline every
other vendor call gets. `StockDetail` gained a `financials` field.

**Frontend:** new `CompanyFinancials.tsx` table on the stock detail page
(Fiscal Year/Revenue/Gross Margin/Opex/Operating Income/Operating Margin/Net
Income, `null` renders "—"). `Tape.tsx`'s equity items now link to
`/stock/{symbol}` too (same equity-only restriction as `QuoteGrid.tsx`);
handled the marquee's duplicated-for-seamless-scroll content correctly
(`tabIndex={-1}` on the hidden copy's links, so it's not an invisible
keyboard tab stop).

**Verified locally:** `make test` (129 api + 1 worker + 52 web, up from
125/1/51) / `make lint` / `make typecheck` / `next build` all green. Real
fixture data pulled from AAPL's live companyfacts response, including an
actual same-period restatement case to test the dedup logic.

**Verified live** (vespersoul.com): rebuilt/restarted both `amt-api`/
`amt-web`. AAPL's 5-year gross margin (41.8%→46.9%) and MSFT's (68.4%→
67.9%) both match public knowledge; MSFT's FY2022 opex genuinely shows "—"
in production (that filing didn't tag it) — confirmed as the honest-gap
path, not a bug. Clicked MSFT from the real Tape banner through to its
stock page with live data, zero console errors.

**Not done / deliberately deferred:** quarterly financials view; SEC budget
consumption is enforced per-call-site (news vs. fundamentals) rather than
centrally, sharing the same Redis budget key — fine at this traffic scale.

**Next:** unchanged — Phase 4, Agent (`docs/PLAN.md` section 7, P4). Do not
start until the user has reviewed this pass.

---

## 2026-08-14 — Stock detail page (click-through from equity tiles) + live deploy of today's 4 new sources

Sixth same-day follow-up. Two asks: deploy the day's source additions live,
and build a per-stock detail page reachable by clicking a stock. Full detail
in `docs/DECISIONS.md` ADR-0020.

**Deploy:** `amt-api` restarted (picks up `federal_reserve`/`treasury`/
`regional_feds`/`sec_edgar` from earlier today) — verified live via
`api.vespersoul.com/market/news` and `/market/calendar` actually returning
entries from all four new sources, not just the pre-existing ones.

**Backend:** `GET /market/stock/{symbol}` (new, `apps/api/app/api/market.py`)
bundles quote + 180-day candles + SEC filings + 30-day company news into one
response (`StockDetail` schema), each piece independently degrading.
`SecEdgarProvider.news()` gained per-ticker scoping via `topics` so this
endpoint doesn't pull all 10 curated companies just to show one.

**Frontend:** First dynamic route in the repo, `apps/web/src/app/
stock/[symbol]/page.tsx` — price header, hand-rolled `PriceHistoryChart.tsx`
(hover crosshair + tooltip, same discipline as `YieldCurveChart`), SEC
filings list, recent news list. New `QuoteTile.tsx` client component makes
`QuoteGrid` tiles clickable (`<Link>` + `stopPropagation` against
`DynamicGrid`'s existing card-level explain-panel click) — scoped to
`equity_quote` tiles only, so BTC/VIX/2Y tiles stay non-clickable. Both the
Most Traded panel and DynamicGrid's Quotes block get this for free; Tape's
marquee was deliberately left alone.

**Found and fixed 2 real bugs live** (via rebuilt-server Playwright
screenshots, not just unit tests): unbounded filings/news lists blew the
page out to ~16000px for a heavily-covered ticker (capped at 15/10, matching
`NewsList.tsx`'s existing precedent); the chart's min-price label collided
with the last x-axis date label at the bottom-right corner (moved price
labels to the left edge). Also fixed a small pre-existing cosmetic bug
`sec_edgar`'s name surfaced: source badges with an underscore (`sec_edgar`,
`federal_reserve`) rendered as `"Sec_edgar"` under the shared `.source`
CSS's `capitalize` (which doesn't split on `_`) — fixed in both the new page
and `NewsList.tsx`.

**Verified locally:** `make test` (125 api + 1 worker + 51 web, up from
121/1/51) / `make lint` / `make typecheck` / `next build` all green.

**Verified live** (vespersoul.com): rebuilt and restarted `amt-web`;
clicked PLTR from the real homepage, landed on `/stock/PLTR` with real
price/chart/filings/news, zero console errors. Also spot-checked AAPL, NVDA,
and JPM (outside the SEC-curated 10 — confirmed the honest "no SEC filings
tracked for this ticker" message rather than an error, with real
quote/chart/news still showing).

**Not done / deliberately deferred:** Tape marquee stays non-clickable; no
SEO metadata on the new route; filings list caps at the most recent 15, no
pagination.

**Next:** unchanged — Phase 4, Agent (`docs/PLAN.md` section 7, P4). Do not
start until the user has reviewed this pass.

---

## 2026-08-14 — SEC EDGAR 8-K filings added, scoped to the 10-ticker equity universe already tracked live

Fifth same-day follow-up. Resolved ADR-0017's original blocker on SEC EDGAR
("needs a curated CIK list — a real scope decision") the same way
`config/taxonomy.yaml` was scoped: reused the equity tickers this app
already shows real quotes for (Tape + Most Traded, minus SPY/QQQ/DIA/IWM
since ETFs don't file 8-Ks) rather than inventing new coverage. Full detail
in `docs/DECISIONS.md` ADR-0019.

**Backend** (`apps/api/app/market/providers/sec_edgar.py`, new):
`SecEdgarProvider.news()` — 10 tickers (AAPL/MSFT/NVDA/AMZN/GOOGL/META/
TSLA/AMD/PLTR/SOFI), CIKs resolved live from SEC's `company_tickers.json`,
each company's `submissions/CIK{cik}.json` fetched sequentially with the
required descriptive `User-Agent`, filtered to `form == "8-K"` and `since`,
item codes (`2.02`, `5.02`, ...) mapped to a plain-English headline label.
`calendar()`/`quote()`/`candles()` raise `NotImplementedError` — this is a
pure news source. Wired into `dependencies.py`, a new `sec_filings_news`
capability in `config/providers.yaml` (merged into `NEWS_CAPABILITIES` in
`apps/api/app/api/market.py`), and a self-imposed budget in
`config/budgets.yaml` (60/60s).

**Verified locally:** `make test` (121 api, up from 118) / `make lint` /
`make typecheck` all green.

**Verified live:** direct unmocked provider call against the real EDGAR
API — 45 real 8-K filings surfaced across the 10 tickers over a 120-day
window, correctly clustered around late-July/early-August Q2 earnings
season, item labels and filing-document URLs all correct. Not yet deployed
to vespersoul.com (no rebuild/restart this pass).

**Not done / deliberately deferred:** tier-1 aggregators needing new API
keys (Marketaux/Alpha Vantage/FMP/Benzinga), Polymarket/Kalshi (needs a
persistent events table), White House and 4 of 5 regional-Fed banks (no
working feed — ADR-0018); deploy/restart of `amt-api`.

**Next:** unchanged — Phase 4, Agent (`docs/PLAN.md` section 7, P4). Do not
start until the user has reviewed this pass.

---

## 2026-08-14 — Regional Fed speeches added (Atlanta only); White House and 4 of 5 regional feeds found dead

Fourth same-day follow-up. User asked to keep adding sources from `sources.yaml`
beyond the Fed/Treasury pair below. Full detail in `docs/DECISIONS.md` ADR-0018.

Probed all 6 remaining keyless tier-0 candidates live before writing any code
(the two candidates needing new API keys — Marketaux/FMP/etc. — and the ones
needing real scope decisions — SEC EDGAR's CIK list, Polymarket's events table
— stay deferred, unchanged from ADR-0017): NY Fed, St. Louis Fed, and White
House have no working RSS feed at all anymore (404s across every URL tried,
including several guessed alternates); Chicago Fed's feed 200s but is stale
and mislabeled (2022-2023 CFNAI releases, not speeches); SF Fed's feed 200s
but is their general blog, not a speeches feed. Only **Atlanta Fed**'s held up
— real, current speeches through Feb 2026.

**Backend** (`apps/api/app/market/providers/regional_feds.py`, new):
`RegionalFedsProvider.news()` — same shape as `federal_reserve.py` (dict of
feed → tag, stdlib `ElementTree`, `since`-filtered), just one member (`atl`)
today, structured so a bank can be added back if its feed is ever fixed.
Wired into `dependencies.py`, a new `regional_fed_news` capability in
`config/providers.yaml` (merged into `NEWS_CAPABILITIES` in
`apps/api/app/api/market.py`), and a budget block in `config/budgets.yaml`
(60/hour). Root `sources.yaml` updated with per-member live-probe findings
(`status: dead`/`stable` notes) so it stays honest rather than aspirational.

**Found and fixed a real bug live:** Atlanta Fed's titles carry embedded
literal markup (e.g. `...at <cite>Farm Journal</cite>'s Top Producer
Summit`, confirmed via a live, unmocked provider call) that would have
rendered as raw angle-bracket text in a headline — added a tag-stripping
regex before writing the corresponding test fixture.

**Verified locally:** `make test` (118 api, up from 115) / `make lint` /
`make typecheck` all green. Not yet deployed to vespersoul.com (no rebuild/
restart done this pass) — the live-verification done here was a direct,
unmocked call to the new provider against the real Atlanta Fed feed, not a
full app+Redis smoke test.

**Not done / deliberately deferred:** White House and 4 of 5 regional-Fed
banks (no working feed exists to adapt — see ADR-0018 for the exact probe
results); everything ADR-0017 already deferred (SEC EDGAR, tier-1
aggregators needing new keys, Polymarket/Kalshi); deploy/restart of
`amt-api`.

**Next:** unchanged — Phase 4, Agent (`docs/PLAN.md` section 7, P4). Do not
start until the user has reviewed this pass.

---

## 2026-08-14 — Two new primary sources: Federal Reserve (news), Treasury FiscalData (calendar)

Third same-day follow-up. User supplied `SOURCES.md`/`sources.yaml` at the
repo root — a much larger aspirational source registry than this app
currently has — and asked to add some news/calendar sources from it. Full
scoping rationale in docs/DECISIONS.md ADR-0017; this is a deliberately
small slice of that document, not the whole system.

**Backend** (`apps/api/app/market/providers/{federal_reserve,treasury}.py`,
both new, both keyless, both verified live before any code was written):

- `FederalReserveProvider.news()` — FOMC statements + official speeches via
  plain RSS (`press_monetary.xml`, `speeches.xml`), parsed with stdlib
  `xml.etree.ElementTree` (no new dependency). `calendar()`/`quote()`/
  `candles()` raise `NotImplementedError` — FOMC *dates* specifically would
  need scraping an HTML page, deliberately not attempted here.
- `TreasuryProvider.calendar()` — Treasury FiscalData's `auctions_query`,
  filtered server-side to `auction_date` within the requested window;
  confirmed live this really is forward-looking (an auction 6 days out
  showed up in testing), not historical results.
- `/market/news` (`apps/api/app/api/market.py`) changed from a single
  `capability` query param (always `equity_news` in practice — no real
  caller ever varied it) to always merging `equity_news` + a new
  `macro_news` chain, same merge-not-fallback pattern `/market/calendar`
  already used for `earnings_calendar` + `macro_calendar`.
  `CALENDAR_CAPABILITIES` gained `auction_calendar`.
- New provider budgets (self-imposed, no vendor-documented limit for either
  keyless government source): `federal_reserve` 60/hour, `treasury` 120/min.

**Frontend:** `EconomicCalendar.tsx` gained a third categorical dot
(`auction` → the neutral/muted token, no new hex value).

**Found and fixed a real bug live:** the new sources were technically
wired correctly but invisible in the actual UI — Finnhub's earnings
calendar returns *every* public company reporting same-day (481 entries
on one day, verified), and a pure chronological top-10 slice buried all 7
new non-Finnhub events every time. Fixed with `selectVisible()`
(`EconomicCalendar.tsx`): reserve slots for non-earnings kinds first, then
backfill with the earliest earnings, re-sorted chronologically for
display. Confirmed via Playwright against the live page (not just the API
response) that this actually surfaced the new sources — an ISR/Data-Cache
interaction (`next: { revalidate: 3600 }` on the calendar fetch,
independent of the page's own 15s revalidate window) served one stale
snapshot along the way, resolved by a fresh `next build` + restart, a good
reminder that "the API returns it" and "the deployed page shows it" are
different claims to verify separately.

**Verified locally:** `make test` (115 api + 1 worker + 51 web, up from
107/1/50) / `make lint` / `make typecheck` all green.

**Verified live** (vespersoul.com): `/market/news` and `/market/calendar`
both confirmed serving real `federal_reserve`/`treasury` entries end-to-end;
Playwright-rendered DOM (not just curl) confirmed both FRED macro releases
and all 5 Treasury auctions visible in the Calendar block's top 10, above
same-day earnings clutter.

**Not done / deliberately deferred** (see ADR-0017 for the full list):
SEC EDGAR filings (needs a curated CIK list first), every tier-1
aggregator needing a new API key (Marketaux/Alpha Vantage/FMP/Benzinga),
Polymarket/Kalshi odds-attachment, and `sources.yaml`'s full tiers/dedup/
provenance/importance-scoring/cron-schedule architecture — real P5-scale
work that needs a persistent events table first.

**Next:** unchanged — Phase 4, Agent (`docs/PLAN.md` section 7, P4). Do not
start until the user has reviewed this pass.

---

## 2026-08-14 — Map resized to 50%; every panel gets expand/minimize/delete, persisted

Second same-day follow-up. Two asks: shrink the world map's default
footprint, and give every dashboard panel a generic expand-to-100%/
minimize-to-icon/delete control set, remembered across visits.

- **World map default width:** `page.module.css`'s `.worldMap` — `span 12`
  → `span 6` (50% on desktop's 12-column grid), `span 6` again at the
  tablet breakpoint (6-column grid there, so still 100%), unchanged at
  the mobile breakpoint (already 100%).
- **Panel state system** (new files: `PanelPrefs.tsx`, `PanelControls.tsx`,
  `PanelSlot.tsx`, `PanelRestoreTray.tsx`): a `PanelPrefsProvider` Context
  (same pattern as `ExplainPanelProvider`) holds `Record<panelId,
  "normal"|"expanded"|"icon"|"deleted">`, persisted as one JSON blob to
  `localStorage` (`amt-panel-prefs"` — "normal" isn't stored, only actual
  overrides are, so the blob only ever holds real customizations).
  `Block.tsx`'s header gained three controls (expand/minimize/delete,
  `PanelControls.tsx`) that write to this context; `PanelSlot.tsx` (wraps
  the 4 static panels — News/Calendar/Most-Traded/World-Map) and
  `DynamicGrid.tsx` (the 3 attention-engine panels — inlined rather than
  reusing `PanelSlot`, since these need their own ref/FLIP/attention-
  tracking wiring on the same element that also needs to react to panel
  state) both read it to decide: **deleted** → render nothing at all (the
  actual grid item disappears, so the grid genuinely reflows around the
  gap — not just an empty cell); **icon** → swap the full panel for a
  small `PanelIconChip` (own grid slot, `span 2`, click to restore);
  **expanded** → override the grid-column to `1 / -1` (full width, right
  where the panel already sits, not a fullscreen overlay); **normal** →
  unchanged existing behavior (static CSS class span, or the attention
  engine's computed span for the 3 dynamic ones — a manual expand/icon
  choice overrides that, not the other way around). A deleted panel has no
  visible affordance left to restore it from, so `PanelRestoreTray.tsx`
  (Shell header, next to `ThemeToggle`) lists currently-hidden panels by
  name for one-click restore; renders nothing when none are hidden.
- **Found and fixed a real bug while testing this live:** clicking a
  control on the Quotes or Heatmap panel (the two DynamicGrid blocks with
  their own `onClick` for the attention engine's "why am I seeing this"
  explain panel) also popped that panel open — the click event bubbled up
  from the control button to the card's own click handler. Fixed with
  `event.stopPropagation()` on all four control buttons
  (`PanelControls.tsx`); added a regression test asserting an ancestor's
  `onClick` never fires from a control click.

**Verified locally:** `make test` (107 api + 1 worker + 49 web, up from
106/1/33 at the start of today) / `make lint` / `make typecheck` all
green. `next build` first-load JS 123KB (was 119KB baseline).

**Verified live** (vespersoul.com): rebuilt/restarted `amt-web`.
Screenshotted via a scratch Playwright script — map at 50% width beside
Quotes; deleted News (grid reflowed with no gap, "Hidden: News +" chip
appeared in the header); minimized Calendar to an icon chip and restored
it by clicking; expanded Sector Heatmap to full width with **no** stray
explain-panel popup (confirmed the bug above was actually fixed, not just
patched blind); reloaded the page and confirmed the expanded state
survived. Confirmed the map is 100% width at a 390px mobile viewport.

**Not done / deliberately deferred:** none — both asks shipped in full
this pass.

**Next:** unchanged — Phase 4, Agent (`docs/PLAN.md` section 7, P4). Do not
start until the user has reviewed this pass.

---

## 2026-08-14 — World map follow-up: repositioned, tiled, always-visible %, click popup (FX/yield)

Same-day follow-up to the entry below, driven by user feedback on the
just-shipped world map. Full detail in docs/DECISIONS.md ADR-0016.

- **Repositioned top-left:** `WorldMap` moved from the last row to the
  first thing in `.dashboard` (`page.tsx`), ahead of the attention-engine's
  3-block row — still full-width (`grid-column: span 12`), just first in
  DOM/reading order.
- **Tiled background:** an SVG `<pattern>` (graph-paper grid, `--surface-1`/
  `--gridline` tokens) sits behind every country shape, most visible over
  open ocean — `WorldMapChart.tsx`.
- **Always-visible % labels:** each tracked country now renders its
  `change_percent` as real SVG `<text>` at a computed label anchor, not
  just in the hover title. `worldGeo.ts` gained `labelX`/`labelY`/
  `labelArea` per country (center and bbox area of its *largest* landmass
  ring — avoids Alaska/Hawaii/island parts skewing a country's label off
  its mainland). Found a real legibility bug while screenshotting this:
  small, closely-packed countries (Netherlands, Switzerland, Hong Kong,
  Taiwan, South Korea) overlapped their neighbors' labels into an
  unreadable cluster — added a `MIN_LABEL_AREA` cutoff that skips the
  on-map text for anything too small to hold one legibly (color fill,
  hover title, and click popup are unaffected, only the always-on label).
  Europe's bigger economies (UK/Germany/France/Italy/Spain) still crowd
  each other somewhat at default zoom — a full label-collision-avoidance
  algorithm would fix it properly but was out of scope for this pass.
- **Fixed the "black square" on click:** globals.css's `:focus-visible`
  rule draws an outline around an element's bounding *client rect* — on an
  irregular country `<path>`, that rendered as a large stray rectangle.
  Explicit `outline: none` on `.countryTracked` (both states), keeping the
  existing brightness/stroke hover treatment as the focus indicator
  instead.
- **Click popup (ETF / currency vs USD / bond yield):** re-checked ADR-0015's
  "no FX or bond provider" assumption before building UI for data that
  might not exist — turned out FRED already carries both, no new provider
  needed (ADR-0016). Verified live against the real FRED API before
  hardcoding anything: the Fed's H.10 daily FX release (`DEXUSEU`,
  `DEXJPUS`, ...) covers 20 of 22 non-US countries (missing: Indonesia,
  Saudi Arabia — no series exists); FRED's OECD-mirrored long-term
  government bond yield series (`IRLTLT01<CC>M156N`) covers 15 (missing:
  China, India, Brazil, Taiwan, Singapore, Hong Kong; US uses the existing
  `DGS10`). `GET /market/world` (`apps/api/app/api/market.py`) now also
  queries `macro_series` for the deduplicated FX/yield series, each in its
  own try/except so a FRED hiccup degrades only those two popup rows to
  "not available," never the ETF-driven map fill. `WORLD_INDEX_SPEC` (a
  3-tuple) became `WORLD_COUNTRIES: list[WorldCountrySpec]` (a small
  dataclass) to hold the extra fields legibly; `WorldIndexPoint` schema
  gained `currency`/`fx_label`/`bond_yield_pct`. `WorldMap.tsx` split into
  a server fetch (unchanged pattern) + new client `WorldMapChart.tsx`
  (click state, popup, keyboard `Enter`/`Space` activation) — same
  server/client split precedent as `YieldCurve`/`YieldCurveChart`.
- **Found and fixed a real bundle-size bug while doing that split:**
  `WorldMapChart.tsx` initially imported `WORLD_MAP_WIDTH`/`WORLD_MAP_HEIGHT`
  from `lib/worldGeo.ts` for convenience — since that's a `"use client"`
  component, webpack pulled the *entire* module in, including its top-level
  `import` of world-atlas's ~650KB raw topology JSON (meant to be
  server-only per ADR-0015). First-load JS jumped 119KB → 351KB. Fixed by
  passing both constants down as plain props from the server component
  instead; confirmed back to 121KB post-fix. Worth remembering for any
  future client component near `worldGeo.ts`: never import from it.

**Verified locally:** `make test` (107 api + 1 worker + 37 web, up from
106/1/33) / `make lint` / `make typecheck` all green.

**Verified live** (vespersoul.com): rebuilt/restarted both units;
`/market/world` confirmed returning real `fx_label`/`bond_yield_pct`
end-to-end via curl. Screenshotted via a scratch Playwright script — map
top-left with tiled background and always-visible labels in both themes,
US popup (ETF price/delta, "Not available" for its own currency row since
the US has no FX-vs-itself entry, real 4.68% `DGS10` yield), confirmed no
stray focus-outline box on click.

**Not done / deliberately deferred:**

- Full label-collision avoidance for Europe's still-crowded cluster — the
  size-based cutoff helps but doesn't fully solve it.
- Indonesia/Saudi Arabia have no FX data and no bond-yield data available
  from any wired provider; their popups correctly show "Not available" for
  both rather than a fabricated number.

**Next:** unchanged — Phase 4, Agent (`docs/PLAN.md` section 7, P4). Do not
start until the user has reviewed this pass.

---

## 2026-08-14 — Alpaca live, banner/labels/Most-Traded, world map, light-default theme

Not a PLAN.md phase — a scoped set of user-requested enhancements on top of
the already-shipped P1-P3 surface, deployed live. Full detail in
docs/DECISIONS.md ADR-0014/0015.

**Alpaca (`apps/api/app/market/providers/alpaca.py`):** wired real keys into
`apps/api/.ratx` (were blank since the P1 deploy) and found/fixed two real
bugs surfaced only once live traffic hit them: `/bars` returns a literal
`"bars": null` (not an empty list) without an explicit `start` date, which
crashed `.get("bars", [])`'s list comprehension with a 500 instead of
degrading — fixed with a computed trading-day-aware `start`/`end` window
plus a null-safe `(...).get("bars") or []`. Separately, this account's
default (SIP) feed 403s on anything from roughly the last month
("subscription does not permit querying recent SIP data"); added
`feed=iex`, which is free-tier-accessible. Regression test added
(`test_candles_handles_null_bars`). Equity candles now serve real Alpaca
bars end-to-end; `equity_quote`'s finnhub→alpaca fallback is live-verified.

**Banner/labels:** `TAPE_SPEC` (`apps/api/app/api/market.py`) grew from
2 equities to 11 (+ DIA/IWM/AAPL/MSFT/NVDA/AMZN/GOOGL/META/TSLA) and BTC→
BTC+ETH. `Tape.tsx` gained a `SYMBOL_LABELS` map so FRED series codes render
as VIX/WTI/2Y/10Y instead of VIXCLS/DCOILWTICO/DGS2/DGS10 (YieldCurve.tsx
already did this for its own tenors — DGS10 is a real series, "DGS" alone
isn't).

**Most Traded:** new fixed-span block (`page.tsx`/`page.module.css`,
outside DynamicGrid's 3-block attention-engine scope per ADR-0012) —
reuses `QuoteGrid` as-is with a curated high-volume symbol list
(NVDA/AAPL/TSLA/AMD/AMZN/MSFT/META/GOOGL/PLTR/SOFI). No new component, no
new backend endpoint — real quotes via the existing `equity_quote` chain.

**World map (`WorldMap.tsx`, `lib/worldGeo.ts`, `GET /market/world`):**
index view only (ADR-0015) — 23 countries proxied by their largest
US-listed single-country ETF, quoted for real through `equity_quote`.
Geometry via `world-atlas` + `topojson-client` (two small packages, first
non-Next/React deps in `apps/web`) processed entirely server-side into SVG
path strings — a hand-rolled equirectangular projection, no geo-rendering
library, same discipline as ADR-0009's hand-rolled charts. Found and fixed
a real data bug along the way: the atlas has small territories sharing
their parent country's ISO code as a separate feature (Ashmore and Cartier
Is. under Australia's `036`) and five disputed regions with no ISO code at
all (Kosovo, Somaliland, N. Cyprus, Indian Ocean Ter., Siachen Glacier) —
both caused React key collisions until `worldGeo.ts` started merging
same-code features and dropping codeless ones (regression-tested).
Currency/treasury-yield toggles are deliberately not built — no FX or
per-country bond provider exists yet.

**Light-default theme (`globals.css`, `ThemeToggle.tsx`, ADR-0014):**
supersedes ADR-0009's dark-only call. Light is now the bare `:root`
(bright, WCAG-AA-checked text/status colors on white); dark moved to
`[data-theme="dark"]` and was redesigned per the user's reference image —
bluer near-black surfaces, brighter/neon status colors, stronger gradients,
and `--font-sans` repointed at the monospace face so dark-theme body copy
reads as technical rather than humanist. `ThemeToggle.tsx` persists the
choice to `localStorage`; a blocking inline script in `layout.tsx` applies
it before first paint (no flash, unlike ADR-0013's accepted SSR-personalization
flash — this one didn't need the same trade-off). Found a real cross-theme
bug while wiring this: `Heatmap.tsx`/`WorldMap.tsx` are Server Components
that compute a data-driven fill color at render time, before the client's
theme choice is knowable — hardcoded RGB literals baked into their inline
styles couldn't react to a theme switch. Fixed by adding `--accent-rgb`/
`--positive-rgb`/`--negative-rgb` tokens and building `rgba(var(--x-rgb),
alpha)` strings instead — the browser substitutes the custom property at
paint time regardless of when the string was assembled server-side.

**Verified locally:** `make test` (106 api + 1 worker + 33 web, up from 104/
1/30) / `make lint` / `make typecheck` all green. `next build` still 119KB
first load (world-atlas's ~650KB raw topology is server-only, never
bundled).

**Verified live** (vespersoul.com, post-deploy): rebuilt and restarted both
`amt-api`/`amt-web`; `/market/world`, `/market/candles?capability=
equity_candles`, and `/market/tape` all confirmed returning real data
end-to-end via curl. Screenshotted both themes and the world map via a
scratch Playwright script at desktop width — light theme legible
(heatmap/map fills correctly flipped to dark-on-light text), dark theme
matches the bluish/gradient/mono reference, map shows real red/green by
country.

**Not done / deliberately deferred:**

- World map currency and treasury-yield toggles — no FX or multi-country
  bond provider is wired; US Treasury (FRED) is the only yield curve this
  stack can reach.
- Singapore/Hong Kong needed the atlas's 50m (not 110m) resolution to have
  a shape at all — fine for now, but worth knowing if map performance ever
  becomes a concern.
- `api_keys.ratx` at the repo root (the plaintext scratch file the keys
  above were copied from) is now redundant — added `*.ratx` to the root
  `.gitignore` as a safety net either way, but flagged for the user to
  delete it since `apps/api/.ratx` is now the live copy.

**Next:** Phase 4 — Agent (`docs/PLAN.md` section 7, P4), unchanged from
before this session. Do not start until the user has reviewed this pass.

---

## 2026-08-13 — P3: Attention engine, deployed

Full phase per `docs/PLAN.md` section 4/7 (P3), with one deliberate scope
cut logged as ADR-0012: the layout solver reallocates space between the
three P2 blocks that map cleanly onto disjoint taxonomy nodes (Quotes,
Yield Curve, Sector Heatmap), not a fully dynamic per-node treemap. News/
Calendar keep a fixed span. The math itself (decay, DAG propagation,
softmax, clamping) is exactly per spec — nothing about the scope cut
touches correctness, only how many block types exist to receive it.

**Backend (`apps/api/app/attention/`, first real Postgres usage —
ADR-0011):**

- `config/taxonomy.yaml` + `taxonomy.py`: asset_class → bucket → node →
  instrument DAG, built from exactly the symbols the P1/P2 blocks already
  query for real (no aspirational instruments). Cold-start weights
  (equities 35/fixed_income 25/macro 15/crypto 10/commodities 8/fx 7) sum
  to 1.0; `fx`/`derivatives` are structurally present but instrument-less
  until a provider exists for them.
- `decay.py`: exponential decay (7-day half-life) via the decay-on-read
  trick — `(score, last_updated)` decayed forward at read time rather than
  replaying event history; proven equal to from-scratch summation in
  `test_decay.py`. DAG propagation at child 1.0/parent 0.6/grandparent 0.3.
  Full event/weight table from the plan; MUTE gets an extra score ceiling
  (`MUTE_CEILING`) so ambient engagement can't quietly out-accumulate an
  explicit mute — only a PIN on the same node lifts it.
- `db/schema.sql` + `db.py`: raw asyncpg, not an ORM (ADR-0011) — three
  tables (`profiles`, `events`, `interest_scores`), applied idempotently at
  startup.
- `layout.py`: softmax(s/τ, τ=1.5) → clamp (6%/40%, rescaled to 2/8
  columns for a 3-block row — ADR-0012) → largest-remainder apportionment
  into integer grid-column spans that always sum to exactly 12.
- `identity.py` + `/profile/*` API: HMAC-signed anonymous `profile_id`
  cookie (no email/password), `POST /events` (batched ingest),
  `GET /vector`, `GET /layout`, `GET /explain?node_id=`,
  `GET/POST /personas`, `/persona/{name}`, `/reset`. CORS added
  (`WEB_ORIGIN`, credentialed) — `/profile/*` is the first API surface
  called directly from the browser rather than only server-side (ADR-0013).
- `config/personas/*.yaml` + `personas.py` + `scripts/simulate_user.py`:
  the 4 personas from the plan (macro, equity_pm, options_trader,
  crypto_native), each a scripted event sequence over a simulated week —
  replayed through the *real* decay pipeline, not hand-tuned final scores.
  Same replay function backs both `make simulate PERSONA=` and the live
  "View as" switcher. Verified: macro → yield_curve dominates,
  equity_pm → heatmap+quotes dominate. options_trader/crypto_native center
  on `macro.cross_asset.volatility`/`crypto.majors.btc`, neither wired to a
  P3 block yet, so their real vector doesn't show up as dramatically in the
  layout — visible via `/profile/vector`/explain regardless (noted in the
  persona YAML itself).
- 103 backend tests (was 66 pre-P3), including a golden test matching the
  DoD's literal example ("5 rates clicks over 3 days" → yield_curve
  dominates) and a vector/explain reconciliation test for the same DoD line.

**Frontend (`apps/web/src/`):**

- `lib/attention.ts`: client-side (browser) fetch layer, `credentials:
  "include"`, hitting a new `NEXT_PUBLIC_API_PUBLIC_URL` — deliberately
  separate from the existing server-side `NEXT_PUBLIC_API_BASE_URL`, which
  is a same-box loopback address unreachable from a real visitor's browser
  (ADR-0013).
- `hooks/useAttentionTracking.ts` + `lib/eventQueue.ts`: IntersectionObserver-based
  impression (>1s)/dwell (+5s increments)/hover/click tracking, batched and
  flushed via `fetch(..., {keepalive: true})` every ~2s (sendBeacon doesn't
  reliably support a credentialed JSON cross-subdomain POST — noted in
  code). `YieldCurveChart` (already a client component) gets its own
  finer-grained per-tenor-segment tracking (`chart_interaction` on
  crosshair move, `click` → explain) rather than the generic block-level
  hook.
- `components/DynamicGrid.tsx`: replaces P2's fixed Quotes(5)/YieldCurve(7)
  two-block row with all three dynamic blocks sharing one row, sized from
  `/profile/layout` (polled every 30s). FLIP animation (capture rect before
  a layout-changing render, invert the transform, transition it away over
  400ms) turns the instant column-span jump into a smooth reflow. Gated to
  desktop widths (`useIsDesktop`) — the solver's spans are computed against
  a 12-column row and don't translate proportionally onto the existing
  tablet/mobile stacked breakpoints, so those keep their P2 CSS-only
  fallback untouched.
- `components/ExplainPanel.tsx`: "why am I seeing this" — Context-based
  (trigger lives arbitrarily deep in the tree, several levels inside Server
  Components that can't hold client callback state), shows decayed score,
  mute state, and source events with weight/timestamp.
- `components/PersonaSwitcher.tsx`: real "View as" in the header, replacing
  P2's static label. Switching always mints a *fresh* profile (doesn't mix
  a persona's seeded history into whatever the visitor already had) and
  reloads the page so every part of it (currently just DynamicGrid) picks
  up the new cookie consistently.
- `vitest.setup.ts` gained `IntersectionObserver`/`matchMedia` stubs — jsdom
  implements neither; every real browser does.
- 29 frontend tests (was 20), all passing; `make test`/`lint`/`typecheck`
  green across api/worker/web (133 total tests).

**Verified live** (vespersoul.com, post-deploy): fresh visitor gets an even
4/4/4 column split; clicking the yield-curve chart opens a real explain
panel (0.00 score, "no recorded interactions yet" for a first visit, as it
should be); switching "View as: Macro" mints a new profile, replays the
persona, and visibly reshapes the row (yield_curve grows to dominate) —
screenshotted via a scratch Playwright script, zero console errors. Test
profiles created during backend curl checks and the Playwright smoke test
were deleted from the (pre-launch, no real visitors yet) production DB
afterward.

**Not done / deliberately deferred:**

- Per-node dynamic block rendering (ADR-0012) — the fully generic
  treemap-of-arbitrary-blocks vision from the plan. Current scope reshapes
  3 existing blocks; a 4th+ block type appearing dynamically per taxonomy
  node is a real next step, not implemented.
- The plan's literal ε=10% "exploration" mechanism (sample an unengaged
  adjacent node) has no 4th block to allocate into with a fixed 3-block
  candidate set — substituted with the MIN_AREA/MIN_COLUMNS floor, noted in
  `layout.py`'s docstring.
- Nightly compaction of raw events older than 30 days (plan section 4.3) —
  not part of the P3 DoD, full event history is retained uncompacted for
  now.
- Per-cell tracking/explain on Heatmap sector cells and individual
  QuoteGrid tiles (SPY vs. QQQ vs. BTC) — currently block-level with one
  representative node each; each sector already has its own leaf node
  (`equities.us_large_cap.technology` etc.) so per-cell wiring is a
  contained follow-up, not a redesign.
- The initial page load shows the default 4/4/4 split for a beat before
  the real personalized layout fetch resolves (ADR-0013's trade-off for
  keeping the page static/ISR rather than SSR-personalizing it).

**Next:** Phase 4 — Agent (`docs/PLAN.md` section 7, P4). Do not start
until the user has reviewed the live attention engine.

---

## 2026-08-13 — Font-loading bug fix + layout dead-space fixes

User reported the redesign was still rendering Times New Roman and looked
"unbelievably ugly" despite the font/gradient/squared-corner pass below
already being live. Verified via a headless Playwright check (computed
`getComputedStyle`, not just a screenshot) rather than trusting the visual
— confirmed the complaint was real, not client-side cache:

- **Root cause**: `app/layout.tsx` put the `next/font/google` variable
  classes (`--font-display`/`--font-data`) on `<body>`, while
  `globals.css`'s `:root { --font-sans: var(--font-display), … }` lives on
  `<html>`. `getComputedStyle(document.body).getPropertyValue('--font-sans')`
  came back **empty** even though `--font-display` resolved fine on body —
  a nested `var()` reference across two different elements in the
  inheritance chain (defined on the ancestor, substituted variable set on
  the descendant) resolved to a guaranteed-invalid value in Chromium,
  which collapsed the whole `font-family` declaration to the UA default
  (serif → Times New Roman). Fix: moved both variable classes onto
  `<html>` so `:root` and the variables live on the same element — no
  more cross-element indirection. Verified post-fix: `document.fonts`
  shows `Space Grotesk`/`JetBrains Mono` status `loaded` and computed
  `fontFamily` matches the declared stack.
- While investigating, also fixed two real layout bugs the screenshots
  surfaced (not part of the font bug, but contributing to "ugly"):
  - `Block.module.css`'s `.block` never filled its CSS Grid cell — `Block`
    sits one DOM level inside `page.module.css`'s grid-item wrappers
    (`.quoteGrid`, `.yieldCurve`, …) since `Suspense` renders no element of
    its own, so it never inherited the grid row's stretch and sized to its
    own content instead. A short Quotes card next to a tall Yield Curve
    card left a dead gap before the next row started. Fixed with
    `.block { height: 100% }` + `QuoteGrid`'s tile grid getting
    `align-content: center` so the now-taller card centers its tiles
    rather than pinning them to the top.
  - That same fix would have made `Heatmap`/`Calendar` stretch to match
    `News`'s open-ended (article-count-dependent) height, blowing them up
    into mostly-empty cards — opted them out via `align-self: start` in
    `page.module.css` so only the Quotes/Yield-Curve pairing (a modest,
    intentional-looking gap) stretches.
  - `Heatmap.module.css`'s sector grid used CSS Grid `auto-fill`, which
    left a ragged, non-full-width last row when the sector count didn't
    divide evenly into a row. Switched to `display: flex; flex-wrap: wrap`
    with `flex: 1 1 88px` cells, so a partial last row stretches to fill
    instead of leaving empty grid tracks.

**Verified:** `make test`/`lint`/`typecheck`/`build` all green. Rebuilt,
restarted `amt-web`, and this time verified with a headless-browser
computed-style check (not just a screenshot) before declaring it fixed —
screenshot-only verification is what let the font bug ship in the first
place.

**Next:** Phase 3 — Attention engine (`docs/PLAN.md` section 7, P3). Do
not start until the user has reviewed the live site.

---

## 2026-08-13 — Font/gradient/squared-corner pass, deployed

**Done:**

- User feedback on the live redesign: fonts were rendering as Times New
  Roman (font failed to apply on their end), wanted a more modern
  typeface, gradiented backgrounds, and squared (not rounded) borders.
- Swapped `Geist`/`Geist_Mono` for `Space_Grotesk` (`--font-display`) and
  `JetBrains_Mono` (`--font-data`) in `app/layout.tsx` — same
  `next/font/google` self-hosting pattern as before, just a more
  distinctive geometric sans + a mono with more character for figures.
- `--radius-sm`/`--radius`/`--radius-pill` all dropped to 2px (effectively
  square; not a literal 0 so hairline borders don't alias into a jagged
  corner). Applies everywhere automatically since every component already
  consumed the radius tokens rather than hardcoding values — only the two
  literal `border-radius: 50%` circles (header status dot, calendar
  kind-dot) were left round, deliberately: they're semantic indicator
  dots, not panel chrome.
- Added decorative gradient tokens — `--panel-gradient`, `--tile-gradient`,
  `--header-gradient`, `--brand-gradient` — and wired them into `Block`
  (every card), `Shell` (header bar, prompt input, "Terminal" wordmark now
  gradient-text), `QuoteGrid` tiles, and `Tape`. Body background gained a
  diagonal linear-gradient sweep under the existing radial accent bloom.
  Scoped to chrome only, per the dataviz skill: sparkline fills, the
  heatmap legend bar, and the yield-curve line keep their existing flat/
  validated-palette treatment untouched — a decorative gradient on a data
  mark would distort the value encoding.
- No new hex values — gradients compose from the same validated palette
  slots (accent, series-2, surface-1/2), so no re-validation needed.

**Verified locally:** `make test`/`lint`/`typecheck`/`build` all green (20
web tests, same 115KB first load). Rebuilt and restarted `amt-web`;
confirmed live via a scratch Playwright screenshot at desktop (1440px)
and mobile (390px) widths — new font renders, gradients visible on
panels/header/tiles, corners square throughout, no label collisions, and
the yield-curve mobile tenor-thinning still holds.

**Next:** Phase 3 — Attention engine (`docs/PLAN.md` section 7, P3). Do
not start until the user has reviewed the live redesign.

---

## 2026-08-13 — Dataviz-skill redesign pass, deployed

**Done:**

- Applied the dataviz skill's procedure across every P2 block (commit
  `ebe26dd`, merged `413b28f`): new design tokens (elevation shadows,
  pill/sm radii, transitions), sticky glass header with a live-status
  pulse, a true auto-scrolling marquee `Tape` (duplicated track, seamless
  CSS loop, pauses on hover, respects `prefers-reduced-motion`), card
  hover elevation, and a shared `Unavailable` component (icon + message)
  now wired into every block instead of five ad-hoc inline-styled `<p>`
  fallbacks.
- `YieldCurve` got the hover layer P2 deferred (ADR-0009): split into a
  server component (fetch only) + new client component
  `YieldCurveChart` with a crosshair, snap-to-nearest tooltip, soft
  accent-wash area fill, and a narrow-viewport rule thinning 11 tenor
  labels to 6 so they don't collide on phone width. `QuoteGrid` tiles are
  bigger with a proportional-figure price, a pill delta badge, and a
  trend-colored `Sparkline` with matching area wash. `Heatmap` gained a
  diverging-scale legend + hover/focus lift. `EconomicCalendar` got
  fixed-order categorical dots. `NewsList` got a hover-revealed
  external-link icon.
- All hex values reused existing validated palette slots — no new colors,
  no re-validation needed.
- **Deployed to production**: the redesign was merged after `amt-web`'s
  last build/restart, so the live site was still serving the pre-redesign
  build. Rebuilt (`npm run build`, 115KB first load, same static-prerender
  profile as before) and restarted the `amt-web` systemd unit. Confirmed
  the new CSS (marquee keyframes, `prefers-reduced-motion` rule) is
  present in the served static chunks and `https://vespersoul.com`
  returns 200 post-restart.

**Verified locally:** `make test` / `make lint` / `make typecheck` all
green (48 api + 1 worker + 20 web tests — `Tape.test.tsx` updated since
the marquee legitimately renders each quote twice, once `aria-hidden`).
Screenshotted the rebuild via a scratch Playwright script at desktop/
tablet/mobile widths plus a forced yield-curve hover state; fixed a
mobile tenor-label collision that surfaced before considering it done.

**Not done / deliberately deferred:**

- No Lighthouse run against the now-live redesign yet — worth doing now
  that there's a real URL, to confirm the ≥90 target still holds with the
  new elevation/animation CSS.
- Provider keys (Finnhub/FRED/Alpaca) still not deployed — SPY/QQQ/yield-
  curve/heatmap/news/calendar still correctly show "unavailable" on the
  live redesign, same gap as before this pass.

**Next:** Phase 3 — Attention engine (`docs/PLAN.md` section 7, P3). Do
not start until the user has reviewed the live redesign.

---

## 2026-08-13 — Deploy to vespersoul.com + `.env` → `.ratx` rename

**Done:**

- Deployed the P2 build live: `amt-api` (uvicorn, 127.0.0.1:8100) and
  `amt-web` (`next start`, 127.0.0.1:3000) as systemd units, nginx
  reverse-proxying `vespersoul.com` → web and `api.vespersoul.com` → api
  (existing Certbot cert/vhost reused, previously a static placeholder).
  Reused the already-running dev-compose Postgres/Redis (5433/6380) — no
  key/secret code currently touches Postgres.
- Repo pushed to a new GitHub remote: `thevalerka/bnk-ai-personal-finance`
  (public).
- User preference: no `.env`-named files, even locally (ADR-0010). Renamed
  `.env.example` → `.ratx.example`, `apps/api/.env` → `apps/api/.ratx`,
  `apps/web/.env.production.local` → `apps/web/.ratx.production.local`,
  added `apps/web/.ratx.example`. `apps/api`/`apps/worker` `config.py` now
  point `SettingsConfigDict(env_file=".ratx")`. `apps/web/next.config.ts`
  gained a small hand-rolled loader since Next.js only auto-loads
  `.env*`-named files. `.gitignore` / `apps/web/.gitignore` updated to
  ignore `.ratx`/`.ratx*` (with `!.ratx.example` carved out so the template
  stays tracked).

**Verified locally:** `make test` / `make lint` still green post-rename
(same 48 api + 1 worker + 20 web). Rebuilt web, confirmed the new
`127.0.0.1:8100` value actually got inlined into `.next/server` output
(NEXT_PUBLIC_* vars are build-time-inlined, so this needed a real rebuild,
not just a service restart). Restarted both systemd units, reconfirmed
`https://vespersoul.com` (dashboard renders) and
`https://api.vespersoul.com/market/tape` (live BTC price via Binance) both
still serve correctly.

**Not done / deliberately deferred:**

- No provider keys deployed yet (Finnhub/FRED/Alpaca) — `apps/api/.ratx`
  has them blank, same as local dev. SPY/QQQ/yield-curve/heatmap/news/
  calendar correctly show "unavailable" on the live site rather than fake
  data. Drop keys into `apps/api/.ratx` and restart `amt-api` when
  available.
- `apps/worker` isn't deployed — it's still a no-op APScheduler skeleton,
  nothing in `/market/*` depends on it yet.
- Deployment is systemd + manually-edited nginx config, not part of the
  repo/CI — no redeploy script yet. Fine for a single-box demo, would need
  revisiting before a second environment or a team touches this.

---

## 2026-08-12 — P2: Static dashboard

**Done:**

Backend (`apps/api/app/market/`, needed by the frontend blocks below —
extends P1 rather than a new phase's worth of provider work):

- `Router` generalized: `quote()`'s cache→budget→fallback policy is now a
  shared private `_call()`, with `candles()`, `news()`, `calendar()` added
  on top of it (ADR-0008). Each has its own cache-freshness TTL (quotes/
  candles 30s, news 300s, calendar 3600s, per docs/PLAN.md §3.1).
- `config/providers.yaml`: new capability chains — `equity_candles` (alpaca),
  `crypto_candles` (binance, hyperliquid), `macro_candles` (fred),
  `equity_news` (finnhub), `earnings_calendar` (finnhub), `macro_calendar`
  (fred).
- New endpoints: `GET /market/candles`, `GET /market/news`,
  `GET /market/calendar` (the last merges earnings + macro releases, same
  pattern as `/market/tape`'s multi-capability composition).
- 15 new backend tests (router generic-call fallback/TTL behavior + the
  three new endpoints, including graceful partial-failure on `/calendar`).
  56/56 backend tests green.

Frontend (`apps/web/src/`):

- Dark-first terminal design system in `app/globals.css`: CVD-checked token
  palette (dataviz skill reference palette — categorical blue accent, status
  green/red for quote deltas, diverging blue/red for the heatmap), Geist
  Sans/Mono, spacing/radius scale. No light theme — deliberate, see
  ADR-0009.
- `Shell` (main menu + non-functional prompt bar + static persona-switcher
  label — both wired for real in later phases per docs/PLAN.md), `Tape`
  (global ticker strip).
- Six block components per docs/PLAN.md P2 scope — `QuoteGrid` (stat tiles,
  embeds `Sparkline`), `Sparkline`, `YieldCurve` (FRED tenors DGS1MO..DGS30,
  hand-rolled SVG line chart), `Heatmap` (sector-ETF universe, diverging
  blue/red fill), `NewsList`, `EconomicCalendar` — every one an async Server
  Component hitting `lib/market.ts` directly, every one rendering an
  explicit "unavailable" state on a failed/empty fetch rather than a
  fabricated number (ADR-0009).
- Fixed 12-column CSS Grid default layout (`app/page.module.css`),
  responsive at the 1024px/768px breakpoints, collapsing to one column on
  mobile.
- `Block`/`BlockSkeleton`/`Unavailable` shared chrome with a fixed
  `minHeight` per block so the Suspense-boundary skeleton→content swap
  doesn't shift layout.
- 20 new frontend tests (Testing Library) covering the live-data render path
  and the graceful-degradation path for every block, plus `Shell`/
  `Sparkline`/`Block`. Added RTL `cleanup()` to `vitest.setup.ts` (was
  missing — first multi-test file surfaced cross-test DOM leakage).

**Verified locally:**

- `make test` / `make lint` / `make typecheck` all green (48 api + 1 worker
  + 20 web tests; ruff/mypy/eslint/tsc all clean).
- `next build` succeeds; `/` prerenders static with a 15s ISR revalidate,
  113KB first-load JS.
- Live end-to-end smoke test: dockerized Redis/Postgres up, real API server
  + real Next dev server, no provider keys configured (same state as the P1
  smoke test). Confirmed both required states render correctly on the same
  page: **BTC** (keyless Binance) shows a real live price end-to-end through
  `Tape` and `QuoteGrid`; **SPY/QQQ/yield-curve/heatmap/news/calendar** (all
  need Finnhub/FRED/Alpaca keys not yet in `.env`) each render their explicit
  "unavailable" message — never a stale placeholder or a zero.

**Not done / deliberately deferred:**

- No hover crosshair/tooltip on `YieldCurve` beyond native SVG `<title>` —
  the dataviz skill's interaction layer is a nice-to-have here, not gated by
  P2's DoD (Lighthouse + responsive + no layout shift), and the prompt
  bar/persona-switcher precedent in P2's own spec ("prompt bar
  (non-functional)") is to ship the visual shell now and wire interactivity
  later.
- No light theme / theme toggle — this is a terminal, not a marketing page;
  P2 doesn't ask for one and the primary showcase context (screenshots,
  demo) is dark.
- No Lighthouse CI run yet — needs a deployed or tunneled URL; the
  `next build` output (113KB first load, static prerender) is a strong
  proxy but hasn't been scored. Flagged for the user to confirm ≥90 once
  there's a URL to point Lighthouse at.
- Equity/macro/news/calendar blocks are correctly built against real
  endpoints but untested against live Finnhub/FRED/Alpaca responses in this
  environment — same gap as P1, still blocked on API keys in `.env`.
- `packages/shared` still has no generated TS types from the Pydantic
  models — the frontend hand-maintains matching interfaces in
  `lib/market.ts` instead; deferred again, now that the frontend actually
  does consume this data, worth revisiting if the two start drifting.

**Next:** Phase 3 — Attention engine (`docs/PLAN.md` section 7, P3). Do not
start until the user has reviewed P2.

---

## 2026-08-12 — P1: Market Data Gateway

**Done (all in `apps/api/app/market/`):**

- Canonical schema (`schemas.py`): `Instrument`, `Quote`, `Candle`,
  `CurvePoint`, `NewsItem`, `Event`.
- `Provider` Protocol (`providers/base.py`) — `quote`/`candles`/`news`/
  `calendar`/`cost` — plus `CallSpec`, `DateRange`, `ProviderError`.
- Five adapters, each implementing exactly the capability its free tier
  actually offers (see docs/DECISIONS.md ADR-0006 for why some methods raise
  `NotImplementedError` rather than faking data): `finnhub.py` (quote, news,
  earnings calendar), `fred.py` (quote/candles as series observations,
  release calendar), `alpaca.py` (quote via latest trade, candles via bars),
  `binance.py` (quote/candles, keyless), `hyperliquid.py` (quote/candles,
  keyless).
- `cache.py`: Redis cache that tracks entry age so a stale-but-present entry
  can still be served (see ADR-0005).
- `budget.py`: fixed-window per-provider call budget in Redis (ADR-0004).
- `router.py`: capability → provider fallback chain (`config/providers.yaml`),
  cache-then-budget-then-vendor per provider, stale-cache-on-breach, raises
  `MarketDataUnavailable` only once the whole chain is exhausted.
- `dependencies.py` + `app/main.py` lifespan: builds the Gateway once at
  startup, tears it down on shutdown.
- `app/api/market.py`: `GET /market/tape` (fixed multi-capability tape) and
  `GET /market/quote?capability=&symbols=`.
- Tests (39, all offline): per-provider respx-mocked fixture tests
  (`tests/market/test_{finnhub,fred,alpaca,binance,hyperliquid}.py`), plus
  fakeredis-backed budget/cache/router unit tests and TestClient-level
  `/market/tape` tests proving transparent fallback and the 503-on-total-
  failure path.

**Verified locally:**

- `make test` / `make lint` green (Python + web).
- `pip install -e ".[dev]"` in a scratch venv (mirrors the CI job exactly) →
  installs clean, 39/39 tests pass, ruff/mypy clean.
- Live smoke test against the *real* app (`app/main.py` booted, dockerized
  Redis up, no provider keys configured): `GET /market/tape` returned a real
  live BTC price from Binance's public API; equity/macro capabilities
  degraded to an empty (not crashed) result since no Finnhub/FRED/Alpaca keys
  are configured yet — expected, and the endpoint stayed at 200 with a
  partial tape rather than failing outright.

**Not done / deliberately deferred:**

- No live end-to-end verification of Finnhub, FRED, or Alpaca — those need
  real API keys (all free to obtain) in `.env`. Binance/Hyperliquid work
  live right now with zero config.
- `/market/tape` composition is limited to what the four P1 providers can
  reach (SPY/QQQ, BTC, DGS2/DGS10/VIXCLS/DCOILWTICO). DXY and gold need
  Twelve Data, which is a P1-matrix fallback provider, not a required P1
  adapter — deferred rather than guessed at.
- `candles`/`news`/`calendar` exist on the providers that support them but
  aren't wired to REST endpoints yet — P1's DoD only requires `/market/tape`
  and the fallback/budget behavior; endpoint surface grows as later phases
  need it (agent tools in phase 4, dashboard blocks in phase 2).
- `packages/shared` still has no generated TS types from these Pydantic
  models — deferred until the frontend actually consumes this data (phase 2).

**Next:** Phase 2 — Static dashboard (`docs/PLAN.md` section 7, P2). Do not
start until the user has reviewed P1.

---

## 2026-08-12 — P0: Foundations

**Done:**

- Monorepo scaffolded: `apps/{web,api,worker}`, `packages/shared`,
  `mcp/terminal-mcp`, `config`, `docs`, `scripts` (see `CLAUDE.md` for layout).
- `apps/api`: FastAPI skeleton, `/health` endpoint, ruff+mypy(strict)+pytest,
  own `.venv`.
- `apps/worker`: APScheduler skeleton with one no-op job, same tooling, own
  `.venv`.
- `apps/web`: Next.js 15 (App Router, TS, src dir), eslint, tsc, vitest +
  Testing Library, one placeholder page + passing test. Built with Node 20
  (installed via nvm — system Node is 18.19.1, incompatible).
- `docker-compose.yml`: Postgres 16 + Redis 7 for local dev, on host ports
  5433/6380 to avoid the box's existing native Postgres/Redis.
- `Makefile` + `scripts/dev.sh`: `make dev` runs docker deps + all three apps
  together; `make test` / `make lint` / `make typecheck` run everything.
- `.pre-commit-config.yaml`: ruff, ruff-format, mypy (api+worker), eslint (web).
- `.github/workflows/ci.yml`: three jobs (api, worker, web), each running
  lint+typecheck+test(+build for web). Verified the underlying commands
  locally (editable installs, `npm ci` equivalent) but the workflow itself
  hasn't run on GitHub yet — no remote exists for this repo.
- `.env.example`, `CLAUDE.md`, `docs/DECISIONS.md` (ADR-0001..0003).

**Verified locally:** `make lint` and `make test` both green across all three
apps. `make dev` boots docker deps + api + worker + web; api `/health` returns
200; web compiles and serves.

**Not done / deliberately deferred:**

- No GitHub remote configured, so the plan's "open a PR titled `P0:
  foundations`" step is blocked — needs `gh auth login` (gh CLI isn't
  installed) or a manually created repo + remote. Flagged to the user.
- `config/{taxonomy,providers,budgets}.yaml` are not populated — that's
  phase 1 (providers/budgets) and phase 3 (taxonomy) scope.
- `packages/shared` has no generated types yet (phase 1).
- npm audit shows 3 high-severity transitive advisories (postcss, sharp) that
  only clear on a Next.js 16 upgrade, which would break the plan's Next 15
  pin and requires Node ≥20.9 either way. Left as-is for now; revisit if it
  becomes a real (not just build-tooling) exposure.

**Next:** Phase 1 — Market Data Gateway (`docs/PLAN.md` section 7, P1). Do not
start until the user has reviewed P0.
