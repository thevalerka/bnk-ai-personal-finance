# Data sources

Companion to `config/sources.yaml`. The YAML is the machine-readable truth; this file
explains *why* each source is there and what will go wrong with it.

**Read this before implementing P1 (Market Data Gateway) or P5 (suggestion rail).**

---

## The one rule

> **The calendar comes from primary sources. Only the news firehose comes from aggregators.**

Aggregator calendars are re-published, occasionally wrong, and often paywalled at exactly
the tier you need. The Fed publishes FOMC dates years in advance for free. FRED publishes
every US statistical release date for free. Treasury publishes its auction schedule for free.
There is no reason to buy, scrape, or trust a middleman for scheduled events.

This is also a positioning argument: a finance hiring manager reading `/architecture`
will notice that FOMC dates came from federalreserve.gov and not from a scraped widget.

---

## Tiers

| Tier | Meaning | Trust | Failure policy |
|---|---|---|---|
| 0 | Primary — the institution that creates the data | Authoritative | **Blocking.** CI fails, page shows a degraded banner |
| 1 | Aggregator — resells or enriches | Good, verify | Fall back down the chain, log, continue |
| 2 | Expectations — market-implied probabilities | Opinion, not fact | Optional enrichment; never a standalone claim |
| 3 | Scraped | Low | Disabled by default, circuit-broken, flagged in UI |

`scripts/check_sources.py` exits non-zero only when a **tier-0** source is down.

---

## What each source is actually for

### Tier 0

**FRED** — the workhorse. Two distinct jobs: (a) every macro series behind the fixed-income
view (`series_map` in the YAML gives the full curve, spreads, real yields, breakevens, credit
OAS), and (b) `/fred/releases/dates`, which is the entire US macro calendar in one endpoint.
Build the curve block against `curve_definition` and you get a live UST term structure with
one API and one key.

**Federal Reserve** — RSS for press releases, speeches and testimony; a quarterly job that
seeds FOMC dates from the calendar page. FOMC is importance 100 and bypasses personalization
entirely: it moves every asset class, so every user sees it.

**Regional Feds** — twelve separate feeds, several with recently-changed CMS. Expect churn;
this is the most likely block to break in six months. Probe them individually.

**SEC EDGAR** — the highest signal-to-noise "news" source that exists and it is free. An 8-K
is a legally-mandated disclosure of a material event, timestamped to the minute. Map form
types to importance (item 2.02 results → 85, 5.02 exec change → 70). Requires a descriptive
`User-Agent` with a real contact or it 403s; keep under ~10 req/s.

**Treasury FiscalData** — auction schedule and results. Nobody's retail dashboard has this
and it matters enormously to rates traders. Cheap differentiator.

**BLS / BEA** — CPI, NFP, PCE, GDP with exact 08:30 ET timestamps. The BLS *schedule* is an
HTML page, not an API endpoint — parse it once a day and cross-check against FRED.

**ECB / Eurostat** — Governing Council dates and euro-area series. Dormant until a user's
interest vector tilts European, then immediately necessary.

**White House / congress.gov** — this is what powers the "X speaks at 14:00" card. Treat
political speech scheduling as inherently unreliable: always render "scheduled, subject to
change", never let the agent assert it as fact, and expire the card aggressively.

### Tier 1

**Finnhub** — best free tier for the combination of quotes, company news with sentiment, and
the earnings calendar. Its **economic** calendar has historically been paid-only, so the YAML
marks that explicitly. Do not design the macro calendar around it.

**Alpaca** — free real-time IEX quotes plus a paper-trading account you'll want anyway in P7.
Also gives market-session/holiday calendar for free.

**Alpha Vantage** — a very tight free tier (~25 req/day). Useless on the request path. Use it
for nightly sentiment enrichment only, and wire its MCP server into *Claude Code* for
development convenience — not into the app.

**Marketaux** — best non-US coverage in the free group, entity extraction is first-class.
The right fallback the moment a user cares about European or APAC names.

**Benzinga Basic** — free tier returns headline, teaser, and a link only. That constraint is
fine for a rail card, and Benzinga's analyst-action coverage is genuinely trader-grade. Must
link back.

**GDELT** — narrative and theme clustering, not tradeable headlines. Feeds the taxonomy topic
tagger rather than the news list.

**Media RSS** — cheap breadth, headline-and-link only. These URLs rot faster than anything
else in the file; the probe script exists largely for them.

### Tier 2 — the differentiator

**Polymarket and Kalshi.** A card that says *"CPI Thursday"* is a calendar. A card that says
*"CPI Thursday — 68% priced for a sub-3% print"* is a product. The `attach_to` block in the
YAML binds live odds onto scheduled events by keyword match.

There is existing in-house Polymarket infrastructure to lean on here, which makes this the
lowest-effort, highest-differentiation item on the entire source list. Build it in P5, not later.

Two honest constraints: prediction-market prices are thin on many contracts, and they are an
*opinion of the crowd*, not data. Render them as "market-implied", show the contract's volume
so a reader can judge thinness, and never let the agent state a probability as a forecast of
its own.

---

## The four things that will break

### 1. Timezones
US releases are announced in **Eastern Time**, which shifts twice a year. Naive datetime
parsing produces a calendar that is silently one hour wrong for several weeks each spring
and autumn — the kind of bug that is invisible in testing and humiliating in production.
Store UTC, parse with `zoneinfo` against the source's declared timezone, render in the
user's local zone.

### 2. Revisions
Macro prints get revised, sometimes substantially. Never `UPDATE` an actual. Insert a new
row with `revision_of = <event_id>` and surface the revision as its own event — "Q2 GDP
revised down to 1.8% from 2.3%" is often more interesting than the original print.

### 3. Deduplication
The same Reuters story arrives from six aggregators within ninety seconds. Three-stage dedupe
(see `normalization.dedupe`): canonical URL hash → title trigram similarity within a 6h window
→ same-tickers/same-15min-bucket/same-kind. On collision, **keep the highest-tier source** so
the SEC filing wins over the aggregator's summary of the SEC filing.

### 4. Provenance
Every persisted row carries `source_id`, `fetched_at`, and `provenance ∈ {primary, aggregator,
scraped}`. The UI shows it. The agent cites it. This is what makes "no fabricated numbers"
enforceable rather than aspirational — and it's what lets the `/architecture` page show
honest per-source freshness.

---

## Licensing

- Headline + teaser + link only for all aggregator and media news. **Never store or render
  full article bodies.**
- Every card links back to its source. Sourceless cards do not ship.
- Some free tiers forbid commercial use outright (API Ninjas' earnings calendar, for one).
  This site is a non-commercial portfolio — record that assumption per provider in
  `docs/DECISIONS.md` so it's a documented decision rather than an oversight.
- Government sources (FRED, SEC, BLS, BEA, Treasury) are public domain. Prefer them wherever
  they cover the need — which, for the calendar, is everywhere.

---

## Implementation order for P1

Build in this order; each step is independently demoable.

1. `check_sources.py` green for tier 0 → you know what you actually have.
2. `Provider` protocol + `Router` + `BudgetManager` + Redis cache, with **one** adapter (FRED).
3. Curve block end-to-end: FRED → canonical `CurvePoint[]` → rendered yield curve.
   This proves the whole vertical slice with a single stable source.
4. Add Finnhub (quotes, news, earnings) and Alpaca (real-time IEX). Now the Router has a real
   chain to walk and fallback is testable.
5. SEC EDGAR filings poller. Now you have an event stream with real importance scoring.
6. Calendar assembly: FRED releases + Fed RSS + Treasury auctions → unified `Event` table.
7. Polymarket enrichment on top of the calendar. Demo moment.
8. Everything else as the interest vector demands it.

Record every provider added or dropped in `docs/DECISIONS.md` with the date and the reason.

---

## Adding a source later

1. Add a block to `config/sources.yaml` with `status: verify`.
2. Add a probe to `PROBES` in `scripts/check_sources.py`; run it.
3. Write the adapter implementing `Provider`; it reads config, never hardcodes URLs or limits.
4. Add it to the relevant `routing` chain — **position matters**, the Router walks in order.
5. Record cost, limits, and licensing in `docs/DECISIONS.md`.
6. Flip `status: stable` only once the probe has passed for a week in CI.
