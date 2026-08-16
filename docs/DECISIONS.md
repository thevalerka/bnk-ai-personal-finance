# Decisions

ADR-style log: context → decision → consequence. Newest first.

---

## ADR-0028: Hyperliquid trading (testnet, builder-fee commission) — pulled ahead of P5, direct browser→Hyperliquid signing, backend as a post-hoc commission ledger only

**Context:** New product direction, separate from the read-only dashboard: let users trade through this interface while execution happens directly on Hyperliquid, earning a small commission per trade via Hyperliquid's **builder codes** (not a spread or custody fee). `docs/PLAN.md` section 6 already sketched this as P6 (read-only wallet)/P7 (flagged execution), sequenced after P5 (Suggestion rail) — per this session's decision, it jumps ahead of P5 instead, and P6/P7 are effectively done in one combined pass, testnet-only.

**Signing scheme, researched before writing any code:** Hyperliquid has two different EIP-712 signing schemes, and conflating them is the most common mistake in third-party integrations. *User-signed actions* (`approveBuilderFee`, `approveAgent`) are plain typed data over domain `HyperliquidSignTransaction` (chain id 42161, with `hyperliquidChain: "Mainnet"|"Testnet"` inside the message). *L1 actions* (placing orders) sign the **msgpack serialization** of the action wrapped in a phantom `Agent` EIP-712 struct, fixed chain id 1337 regardless of network. Hand-rolling the latter (msgpack + keccak + the Agent wrapper) is exactly the kind of thing that silently produces `INVALID_SIGNATURE` if gotten slightly wrong — a financial signing path is not where to save a dependency.

**Decision — use `@nktkas/hyperliquid` (+ `viem` for the injected-wallet connection) for all client-side signing**, rather than reimplementing either scheme by hand. First web3 dependency in this repo (`apps/web/package.json`). `viem`'s `WalletClient`, once bound to an account, structurally satisfies the SDK's duck-typed `AbstractWallet` interface at runtime (`signTypedData`/`getAddresses`/`getChainId`) even though TypeScript can't prove it — `apps/web/src/lib/hyperliquid.ts`'s `asAbstractWallet()` documents and isolates that one narrow cast.

**Decision — wallet discovery via EIP-6963, not a bare `window.ethereum` check.** With MetaMask and Phantom both installed, `window.ethereum` is a collision: whichever extension's script runs last silently wins it, so a naive check can connect the wrong wallet or miss one entirely. `apps/web/src/lib/wallet.ts`'s `discoverWallets()` listens for `eip6963:announceProvider` (the standard both wallets support for exactly this reason — confirmed against Phantom's own docs before writing the fallback path) and returns every wallet that answers, plus two static fallbacks for wallets that haven't adopted EIP-6963 yet: `window.ethereum` (generic/MetaMask, labeled via its `isMetaMask` flag) and Phantom's own non-colliding `window.phantom.ethereum` namespace. `TradingView`'s connect step renders one button per discovered wallet rather than a single "Connect wallet" action.

**Decision — the backend never builds, signs, or relays a trading action; the browser talks to Hyperliquid directly.** The original plan (written before inspecting the actual SDK) assumed a "build unsigned action → sign in browser → relay signed bytes through the backend" split, mirroring how `MarketGateway` proxies read-only vendor calls. Inspecting `@nktkas/hyperliquid`'s `ExchangeClient` showed its `order()`/`approveBuilderFee()` methods sign *and* submit in one call — there is no supported lower-level hook to get a signed-but-unsubmitted payload back out. Rather than fight the SDK's grain (or drop to unsupported internals for a financial signing path), the design changed mid-implementation: the frontend (`apps/web/src/lib/hyperliquid.ts`) builds, signs, and submits every action straight to `api.hyperliquid-testnet.xyz` itself. This is also a more honest shape for "backend never holds keys or custody" (`CLAUDE.md`) — there is no window where the backend even *sees* an action before it's final.

**Consequence — the backend (`apps/api/app/trading/`) is now a thin, post-hoc commission ledger, not a gateway:**
- `GET /trading/config` — public, non-secret builder address + fee rate the frontend needs to attach to a signed call.
- `POST /trading/approvals` / `POST /trading/fills` — logged *after* the browser already got a real signed acceptance from Hyperliquid. `/trading/fills` re-verifies the claimed order against Hyperliquid's own `orderStatus` info call (`{"status": "unknownOid"}` sentinel for a nonexistent order, confirmed live against the real testnet API before writing the check) before persisting — `CLAUDE.md`'s "no number without a real provider response behind it" applied to commission accounting, not just displayed market data. Both endpoints are rate-limited per wallet (`app/trading/budget.py`, same fixed-window Redis idiom as `app.agent.budget.AgentBudget`, keyed by wallet instead of profile).
- `GET /trading/orders?wallet=` — this wallet's logged fill history, backing the frontend's order list. New Postgres tables `builder_approvals`/`order_fills` (`apps/api/db/schema.sql`), same idempotent-`CREATE TABLE IF NOT EXISTS` style as the attention engine's tables.
- `TradingGateway` (`apps/api/app/trading/gateway.py`) is a sibling to `MarketGateway`, not a Router capability — same precedent `sec_edgar`/`polymarket` already established for things that don't fit the quote/candles/news/calendar Provider Protocol.

**Scope, deliberately testnet-only:** `hyperliquid_builder_address` defaults to blank in `apps/api/app/config.py` — same honest-degrade pattern as a blank `anthropic_api_key`, `/trading/config` reports `configured: false` and the UI shows an explicit "not configured" state rather than a dead flow. No mainnet path, no kill switch, no live-funds opt-in exist yet — those are real P7 non-negotiables (`docs/PLAN.md` section 6) to build before ever pointing this at mainnet.

---

## ADR-0027: Phase 4 — Agent (tool-use loop, SSE, dashboard mutation); built and tested without a live Anthropic key

**Context:** Phase 4 per `docs/PLAN.md` section 5/7 (P4). No `ANTHROPIC_API_KEY` exists anywhere in this deployment (checked `apps/api/.ratx`, the environment, and `ant auth status` — nothing). Explored using this session's own Claude Code login as a stand-in; that's a personal subscription OAuth credential scoped to this CLI session, not a portable API key, and baking it into a public production service would be both the wrong mechanism and likely against Anthropic's terms for that credential. User chose to build the full phase now with mocked tests (same discipline every other provider in this repo already uses — respx/FakeProvider doubles, never a real vendor call in CI) and defer live verification/deployment until a real Console API key is added.

**Decision — backend (`apps/api/app/agent/`, new):**

- **Tools** (`tools.py`, 13 total): `get_quotes`/`get_candles`/`get_curve`/`get_news`/`get_calendar` wrap the existing `Router` capabilities directly (no new vendor code); `get_predictions`/`get_earnings_calendar` reuse `market.py`'s `_predictions`/`_earnings_calendar` cache-bypass helpers; `get_world_indices` reuses a `_world_indices(gateway)` helper extracted from the `/market/world` endpoint for this purpose. `screen` is honestly scoped to this dashboard's own curated equity universe (Tape + Most Traded + World Map ETFs) — no free-tier provider here offers a real screener, matching the same disclosed limitation `page.tsx`'s Most Traded panel already carries. `render_chart` fetches real candles and returns both a compact summary (for Claude's context) and a full chart spec (for the frontend, via a separate SSE event) — kept apart so a plotted chart doesn't cost context tokens on an OHLC array the model doesn't need to reason over. `set_focus`/`add_block` both resolve to the same real lever, `attention.service.record_event(..., EventKind.PIN)` — the plan describes them as separate tools, but the attention engine only has one mutation primitive; `add_block` uses full weight and is honest in its result about whether the target node is one of the 3 blocks (`BLOCK_NODES`) that actually resize today (ADR-0012's scope), pinning the interest for real either way. `explain_layout` reuses the existing `/profile/explain` and `/profile/layout` service functions verbatim. Every tool call on a real instrument also fires a best-effort `AGENT_MENTION` event (weight 4.0, the plan's own event table) onto whatever taxonomy node it maps to — the one entry in that table nothing else in the app populates.
- **Loop** (`service.py`): a manual tool-use loop against `client.messages.stream(...)` (Sonnet 5, per the plan's own "Sonnet for the interactive path" choice — not the Opus-5-by-default guidance an assistant would otherwise reach for, because this is the user's documented product decision, not a cost shortcut), not the SDK's `tool_runner` — this needs its own SSE contract to the browser (text/tool_call/tool_result/chart/mutation/done/error, not Anthropic's raw stream shape) and side effects (chart specs, mutation flags) the runner has nowhere to carry. Capped at 6 tool-use turns so a bad loop degrades to a clear error instead of an unbounded number of Claude calls. `stop_reason: "refusal"` is handled explicitly (distinct from `end_turn`) even though Sonnet 5 doesn't carry the same elevated-cybersecurity-classifier behavior Opus 5/Fable 5 do — cheap to handle, and the plumbing is real regardless of which model classifies what.
- **System prompt** (`system_prompt.py`): the plan's five rules verbatim — no number without a tool call, cite source+timestamp, refuse personalized advice and say why, distinguish fact from expectation, say so when a provider is degraded rather than hedging. One constant, cached via a `cache_control: ephemeral` breakpoint on every request (docs' own prompt-caching guidance: stable content first, breakpoint before the volatile per-request question).
- **Cost control** (`budget.py`, plan section 5.3): a monthly token counter (Redis, calendar-month key, self-expiring) and a per-profile requests/minute limiter, both fixed-window counters matching `BudgetManager`'s existing pattern just keyed differently (tokens/month vs. calls/window). Checked *before* opening a turn — refusing a request costs nothing; starting one and aborting mid-stream would have already spent tokens.
- **Identity:** `resolve_profile`/`set_profile_cookie` promoted from private to public in `app/api/profile.py` and reused as-is — the agent attributes `set_focus`/`add_block` to the visitor's real interest vector, not a separate identity scheme.

**Found and fixed a real bug while writing the API-level tests, not the unit tests** — the kind CLAUDE.md's "screenshot-only verification is what let the font bug ship" note warns about: `POST /agent/stream` must return a `StreamingResponse` directly (SSE requires it), but FastAPI silently discards the dependency-injected `Response` object's mutations whenever a handler returns its own `Response` instance — so `resolve_profile`'s `set_cookie` call, made from inside the async generator backing the stream, was setting a cookie that could never reach the client (Starlette sends `StreamingResponse` headers before it starts consuming `body_iterator`, i.e. before the generator — and thus `resolve_profile` — has run at all). First-time visitors would never get an `amt_profile` cookie from this endpoint. Fixed by resolving the profile (and thus its cookie) in `post_stream` itself, before the response is constructed and returned, then passing the resolved `profile_id` into the generator rather than having the generator re-derive it. Caught by an API-level test asserting the `Set-Cookie` header was present — a tool-level or service-level unit test could not have caught this, since the bug is specifically about response-object identity across the FastAPI/Starlette streaming boundary.

**Decision — frontend:** `lib/agent.ts` hand-parses SSE off a streamed `fetch` response (native `EventSource` can't do a credentialed POST with a JSON body) into a typed `AgentEvent` union. `PromptBar.tsx` replaces the P2-era disabled input in `Shell.tsx`; a dropdown panel renders the streaming answer, a "via get_quotes, get_curve" source footer from the turn's tool calls, and an inline `PriceHistoryChart` (reused as-is — the backend's `render_chart` chart spec's `Candle` shape matches the existing TS interface field-for-field) when the agent calls `render_chart`. A `mutation` SSE event dispatches a `window` custom event (`amt:layout-refresh`) that `DynamicGrid.tsx` listens for to refetch `/profile/layout` immediately, instead of waiting out its normal 30s poll — this is the plan's literal "the page rebuilds itself" demo moment.

**Consequence:** 181 backend tests (was 143, +38 for `apps/api/tests/agent/`) / 67 frontend (was 60, +7 for `PromptBar.test.tsx`) — `make test`/`lint`/`typecheck`/`build` all green. Verified with a real, unmocked browser: prompt bar renders enabled, submitting opens the panel and shows the user's turn, and — since no key is configured anywhere yet — a failed request degrades to a plain "Could not reach the agent." message with zero console/React errors, not a crash or a fabricated answer.

**Not done / deliberately deferred:**

- **Live verification against the real Anthropic API** — the DoD's "ten canned questions answered with sourced figures, zero fabricated numbers" needs a real model in the loop; every test here mocks the Anthropic client (a `FakeAsyncAnthropic` test double matching only the surface `service.py` uses) and exercises the *loop's* correctness, not the *model's* answers. Revisit once a Console key is added.
- **Deploy** — `amt-api`/`amt-web` were not rebuilt/restarted; the live site is unchanged this session. `/agent/stream` already 503s cleanly with no key configured, so deploying now wouldn't regress anything, but there's no live feature to show either way yet.
- **Cheaper-tier classification model** (plan 5.1: "a cheaper/faster tier for classification and topic-tagging of events") — no classification/topic-tagging feature exists yet to need it.
- **Token spend surfaced on `/architecture`** (plan 5.3) — that page is P8 scope, not built yet; spend is tracked (Redis) but not displayed anywhere.
- **`screen`'s universe** stays the same curated list as the rest of the app — a real full-market screener would need a new provider, out of scope here.

---

## ADR-0026: Real Polymarket earnings calendar exists — ADR-0024's "no earnings markets" finding was an artifact of the wrong endpoint, not the wrong answer

**Context:** User pointed directly at `polymarket.com/earnings` — a real, live page showing 40+ per-company "beat consensus EPS" markets. This contradicts ADR-0024's conclusion that Polymarket has no per-company earnings markets at real volume. Re-investigated live before writing any code (same standing rule as ADR-0024, applied to *re-checking* a prior finding this time): ADR-0024's probe was correct about what it measured — the top-400-by-24h-volume `/markets` feed genuinely has no earnings questions in it — but wrong about what that implied. `polymarket.com/earnings` is backed by a completely separate `gamma-api.polymarket.com/events?tag_slug=earnings` feed: individual earnings markets run low per-market volume (hundreds to a few thousand dollars each, not millions), so they never surface in a volume-ranked top-N list no matter how large N is, and their questions ("Will Home Depot (HD) beat quarterly earnings?") don't match the Fed/CPI/jobs keyword list `probability()` filters on anyway. Two different feeds, two different filtering strategies — the earlier probe only tried one.

**Decision:** Added `PolymarketProvider.earnings_calendar()`, a second method alongside `probability()`, hitting `/events?tag_slug=earnings` directly (one page, ~500-market cap, currently ~41 real events) rather than trying to make the volume-ranked feed find them. Parses ticker + company from the question text (`Will (.+) \((TICKER)\) beat quarterly earnings\?`), the analyst EPS consensus estimate from the market description text (no structured field for it), and the beat probability from the Yes-outcome price — same `outcomes`/`outcomePrices` JSON-string-list pattern `probability()` already used. **Found and fixed a real type bug before shipping**, caught only by testing against live data rather than trusting the schema from `probability()`'s feed: this `/events` endpoint returns `volume` as a numeric *string*, not a float like `/markets`' `volume24hr` — the initial `isinstance(volume_raw, int | float)` guard (copied from the existing pattern) would have silently zeroed every single volume. New `EarningsMarket` schema, new `GET /market/earnings-calendar` endpoint sharing `probability()`'s `_cached_bypass_call` plumbing and the same `polymarket` budget bucket (1 request vs. `probability()`'s 3).

Left `probability()`'s existing macro-keyword regex and its ADR-0024 Fed/S&P panel untouched — genuinely a different, still-real feed serving a different purpose, not superseded by this. Fixed ADR-0024's and `sources.yaml`'s "no earnings markets exist" claims to instead point here, since leaving a disproven claim in either would mislead the next session that re-reads them.

**Frontend:** New `EarningsCalendar.tsx`, grouped by report date (matching the real page's own layout) rather than a flat list — ticker, EPS estimate, and a probability pill per row, each linking out to the real Polymarket event page. Placed first on the homepage (user request) sharing the first row with a further-shrunk World Map (span 6 → span 5) rather than full-width, so both fit in one row (`page.module.css`).

**Found and fixed one more real bug live:** the first deploy showed "No earnings markets reachable right now" on the actual production page despite the API endpoint itself returning 41 real markets via direct curl — `npm run build` (which statically prerenders `/`, ISR revalidate 15s) had run *before* `amt-api` was restarted with the new endpoint, so the build-time prerender baked in a 404 from the not-yet-updated API. Same category of ISR/build-ordering trap as the one noted in `docs/STATE.md`'s 2026-08-14 entry — fixed by rebuilding `amt-web` a second time, after `amt-api` was already serving the new route, then restarting.

**Consequence:** 143 backend tests (was 137), 60 frontend. Live-verified: real endpoint returns 41 parsed markets (AS/VIK/HD/LZB/LOW/TGT/... with real tickers, EPS estimates, dates, and beat probabilities); screenshotted the rebuilt production homepage at desktop and 390px mobile widths, zero console errors, panel correctly grouped by date with the reduced World Map beside it.

**Not done / deliberately deferred:** no attempt to reconcile `earnings_calendar()`'s report date (the market's `endDate`, when the market stops trading) against the *actual* announced earnings date if the company later reschedules — the description's prose date and `endDate` should track together in practice, but no cross-check exists.

---

## ADR-0025: World map links each country to a full detail page (indices + treasury); zero new backend

**Context:** User asked for the World Map to link each nation to a detail page showing "the main stock indices and treasury," on top of three other asks landing the same session (ADR-0023/0024 below). The map already had a click-to-popup interaction (ETF price/FX/bond yield, ADR-0016) — the question was whether to replace that with navigation or add a link inside it.

**Decision:** Kept the existing popup (still useful as a quick-glance hover-equivalent) and added a "View full details, indices & treasury →" link inside it, going to a new `/country/[iso]/page.tsx` (iso = ISO 3166-1 numeric, matching `WorldCountrySpec.iso_numeric` everywhere else in the codebase — no new identifier scheme). **Needed zero backend changes** — every piece of data the page shows was already served by existing endpoints: `/market/world` (quote/FX/bond yield for every country, ADR-0016), `/market/candles?capability=equity_candles` (index ETF price history, same call `/stock/[symbol]` already makes), and the existing `<YieldCurve />` component (the full US tenor curve) reused as-is when `iso === "840"`. Every other country falls back to the single OECD long-term-benchmark point `/market/world` already carries — genuinely absent for ~7 countries (China/India/Brazil/Taiwan/Singapore/Hong Kong + a couple with no FRED series at all), rendered as "not available" per the existing non-negotiable, not derived or guessed.

Added a "Main World Indices" section: all 23 tracked countries' index ETFs in one sorted list (by day change), each linking to its own `/country/{iso}` — this is what makes "main stock indices" plural rather than just this-one-country's-index; the current country's row gets a left accent-border + bold-accent-text highlight (a plain `background: var(--surface-2)` alone turned out nearly invisible against the section's own `--tile-gradient`, caught visually before shipping).

Extracted the stock detail page's CSS (`stock/[symbol]/page.module.css`) into a shared `apps/web/src/app/detail.module.css` (renaming `.symbol` → `.title`, the only country-specific rename needed) so both drill-down pages read as one consistent pattern instead of two hand-maintained near-duplicates; deleted the now-redundant local file.

**Consequence:** New route `/country/[iso]`, ~2KB. `make test`/`lint`/`typecheck`/`build` all green. Live-verified: clicked Japan on the real production map, followed the new link to `/country/392`, confirmed real EWJ price history, real ¥157.54 FX rate, real 2.67% bond yield, and the full sorted 23-country index list. Confirmed the CSS extraction didn't regress `/stock/[symbol]` (a transient cold-start RSC error on the very first request after `next start` reproduced identically here and on two earlier unrelated pages this same session — not caused by this change; see the "known quirk" note in `docs/STATE.md`).

**Not done / deliberately deferred:** No per-country news/filings section (EDGAR-style filings only exist for the 10 curated US tickers, not foreign issuers). No multi-index-per-country breakdown (e.g. sector-level indices within a country) — one ETF proxy per country remains the model, unchanged from ADR-0015.

---

## ADR-0024: Prediction Markets panel (Polymarket) — real Fed-rate/index markets, not a fictional "earnings calendar"

**Context:** User asked to "copy the earnings calendar from Polymarket" onto the homepage. Checked live before building anything (per this project's standing rule): Polymarket's `gamma-api.polymarket.com/markets` has essentially no per-company earnings markets at meaningful volume — scanning the top 400 active markets by 24h volume, keyword-matching on company/earnings-related terms returned zero hits. What it *does* have, verified live with real dollar volume (5-8M for the biggest single contracts): a cluster of Fed rate-decision markets tied to each FOMC meeting, plus daily S&P-500-direction markets. This matches `sources.yaml`'s own original design intent for Polymarket — `attach_to: { event_kind: fomc, match: "fed|rate|fomc" }` / `{ event_kind: macro_event, match: "cpi|inflation|jobs|payroll|gdp" }` — binding odds to macro/FOMC events, never earnings.

**Decision:** Built the honest version: a "Prediction Markets" panel surfacing real, live Polymarket markets matched against a macro/Fed/index keyword list (the same one `sources.yaml` specifies, extended with `s&p 500|nasdaq|dow jones|treasury yield` after confirming those categories exist with real volume too), sorted by 24h volume — not a fabricated earnings calendar. `PolymarketProvider.probability()` paginates the gamma API (3×100-market pages; Polymarket's server caps a single page at 100) and resolves each match's public URL via its parent **event** slug (`market.events[0].slug`), not the market's own slug — verified live that `/event/{market.slug}` 404s while `/event/{eventSlug}` 200s, since Polymarket groups related binary markets (e.g. "+50bps"/"+25bps"/"no change"/"-25bps") under one shared event page.

`probability()` doesn't fit the `Provider` Protocol (quote/candles/news/calendar) any more than `fundamentals()` did (ADR-0021) — added a matching narrow `ProbabilityProvider` Protocol and reused the exact cache-then-budget bypass pattern, generalized this pass into one shared `_cached_bypass_call()` helper (`apps/api/app/api/market.py`) instead of copy-pasting the fundamentals version, now used by both. New `GET /market/predictions` endpoint, 60s cache TTL (matches `sources.yaml`'s declared `probability_ttl`).

**Consequence:** 137 backend tests (was 132 after ADR-0023), 57 frontend. Live-verified: 9 real markets surfaced in production (Fed rate-path scenarios + rate-cut-count markets), probabilities summing sensibly within each FOMC-outcome group (e.g. 0.4% + 1.1% + 74.5% + 24.5% + 0.4% ≈ 100% across the five September-meeting outcomes). Panel renders a probability pill + a filled bar + 24h volume + resolution date per market, linking out to the real Polymarket event page.

**Not done / deliberately deferred:** No CPI/jobs/GDP markets found at any real volume in this pass — the keyword list covers them for whenever Polymarket does list one, but the panel is honestly Fed/index-dominated today. No attachment of these odds onto the existing `/market/calendar` FOMC entries (`sources.yaml`'s original `attach_to` design) — a standalone panel was the more direct read of "place it in homepage" and needed no calendar-schema changes; revisit the attachment design later if wanted.

---

## ADR-0023: Two more homepage additions — CNBC/MarketWatch RSS news, and a Forex panel needing zero new backend

**Context:** Same session as ADR-0024/0025, two smaller asks: "find and add other news sources," and "add FOREX to the homepage with the main currencies."

**Decision:**
- **News:** `rss_media` (`sources.yaml`'s already-cataloged CNBC + MarketWatch RSS entries) — both verified live before coding, keyless, headline+link only per the licensing note. Same `RegionalFedsProvider`/`FederalReserveProvider`-shaped provider (stdlib `ElementTree`, no new dependency), merged into `NEWS_CAPABILITIES` as `media_news`. (`sources.yaml` also lists a third, per-symbol Yahoo Finance feed — skipped: it needs a ticker templated into the URL, which doesn't fit a flat `news()` call with no symbol parameter; a stock-detail-page feature, not a homepage-feed one.)
- **Forex:** needed **zero backend changes** — FRED's H.10 daily FX series (`DEXUSEU`, `DEXJPUS`, etc.) were already live and wired for the World Map's currency labels (ADR-0016). Verified all 7 major-pair series live (EUR/GBP/AUD vs USD, USD vs JPY/CAD/CHF/CNY) for both `quote` and `candles`. New `Forex.tsx` component only — reuses `QuoteGrid.module.css`'s tile styling for visual consistency but isn't `QuoteGrid` itself (needs pair labels instead of raw FRED series IDs, and `FredProvider.quote()` never computes `change_percent` — confirmed by reading the provider — so trend/% change here are computed client-side from the last two candle closes instead, the same candles already fetched for the sparkline).

**Consequence:** 132 backend tests (was 129), +3 frontend components/tests (Forex, plus the RSS provider's backend tests). Live-verified: `rss_media` items showing in production `/market/news` (16 real CNBC/MarketWatch headlines) alongside Finnhub's 100; all 7 FX pairs rendering real live rates with correctly-signed day-over-day change and sparklines.

---

## ADR-0022: Fundamentals expanded to quarterly + ~20 line items; found and fixed a stale-cache schema crash live

**Context:** User asked to also cover quarterly earnings and report substantially more data than ADR-0021's 5-line annual table. Verified live across all 10 curated tickers (not just the 5 from ADR-0021) which additional us-gaap tags actually exist before adding them: `InterestExpense`/`IncomeTaxExpenseBenefit`/`EarningsPerShareDiluted`/`EarningsPerShareBasic`/`StockholdersEquity`/`CashAndCashEquivalentsAtCarryingValue`/`NetCashProvidedByUsedInOperatingActivities` are universal across all 10; `SellingGeneralAndAdministrativeExpense` alone only covers 4, but combined with `GeneralAndAdministrativeExpense` as a fallback covers all 10; `Liabilities` is genuinely absent for 2 of 10 (stays null, not computed as Assets − Equity, which wouldn't equal reported Liabilities exactly once minority interest/other items are involved).

**Decision:**
- `SecEdgarProvider.fundamentals()` now pulls **both** annual (10-K, last 5 fiscal years) and quarterly (10-Q, last 8 quarters) periods in one call, merged into one date-sorted list (their end dates never collide in practice, so no special interleaving logic needed). `FinancialPeriod` grew from 10 fields to ~24: cost structure (R&D, SG&A, opex), profitability (gross/operating/net margins), per-share (EPS diluted/basic — a different XBRL unit, `USD/shares`, not `USD`), cash flow (operating cash flow, capex, and a computed free cash flow), and balance sheet (assets, liabilities, equity, cash, long-term debt).
- **Balance-sheet concepts are "instant" XBRL facts** (a point-in-time snapshot, `end` only, no `start`/duration) — genuinely different from income-statement "duration" facts, confirmed live before writing code. Added a separate `_instant_values()` helper that looks values up against the exact period-end dates already chosen from the income-statement figures, rather than reusing the span-based duration filter (which requires a `start` date that doesn't exist on these facts).
- Quarterly cash-flow figures are frequently null for Q2/Q3 specifically (not a bug): many companies' XBRL only tags `NetCashProvidedByUsedInOperatingActivities` as a year-to-date cumulative value except in Q1 (where cumulative == standalone) — the existing 80-100 day span filter correctly excludes the cumulative multi-quarter figures, which is honest (no number) rather than showing a wrong one (a 9-month cumulative mislabeled as one quarter).
- **Found and fixed a real bug live** (not caught by tests, which use fresh fixtures every run): the 24h Redis cache from ADR-0021 held `FinancialPeriod` payloads in the *old* shape, missing the newly-required `fiscal_period`/`form` fields — reading that stale cache back crashed the whole `/market/stock/{symbol}` endpoint with a Pydantic `ValidationError` (confirmed via `journalctl`, not just a symptom in the browser). Fixed two ways: (1) the cache key gained a `v2` version segment so old entries are simply never read again (they still expire naturally within 24h, no manual cleanup needed); (2) `_validated_periods()` in `apps/api/app/api/market.py` now catches `ValidationError` on every cache-read path and treats it as a cache miss rather than propagating — general protection against this exact class of bug recurring on the *next* schema change too, not just this one.
- **Frontend:** `CompanyFinancials.tsx` rewritten as a transposed table (metrics as rows, periods as columns — the standard financial-statement layout, not the previous one-row-per-period table, which doesn't scale past a handful of columns) grouped into Income Statement / Per Share / Cash Flow / Balance Sheet sub-sections, rendered twice (Annual, Quarterly) by splitting on `form`.

**Consequence:** 129 backend tests (unchanged count from ADR-0021's 129, since the test rewrite replaced rather than added — expanded fixture now includes EPS/instant-Assets/cash-flow data, plus a new assertion set covering the annual+quarterly interleaving and the instant-fact lookup). 52 frontend tests. `make test`/`lint`/`typecheck`/`build` all green. Live-verified (real, unmocked): AAPL — 3 fiscal years plus 4 quarters checked field-by-field, including the expected Q2/Q3 operating-cash-flow gaps; MSFT — 13 periods (5 annual + 8 quarterly) with real R&D (~$35B), margins (~68% gross), and a genuinely-null `interest_expense` across the board (MSFT doesn't tag that concept the way the fallback list expects — an honest gap, not a bug); GOOGL spot-checked live on production after deploy, 13 periods, 200 OK. Deployed live: `amt-api` restarted (surfaced and fixed the stale-cache crash in the process — first attempt 500'd, second succeeded), `amt-web` rebuilt and restarted.

**Not done / deliberately deferred:** No derived standalone-Q4 figure (would require subtracting Q1+Q2+Q3 from the FY total across every line item — a real computation, not fabrication, but adds meaningful complexity and risk of tag-mismatch errors; FY already covers the same period at the annual grain). No YoY/QoQ delta column. `Liabilities` stays null for the 2/10 tickers that don't report it, rather than being derived from Assets − Equity.

---

## ADR-0021: Company financial profile from EDGAR XBRL company-facts, bypassing Router; Tape banner also links to the detail page

**Context:** User asked for a detailed corporate profile (revenue, gross margin, operating expenses, operating income) sourced from EDGAR filings, plus click-through from the header's Tape banner, not just the Quotes/Most-Traded tiles from ADR-0020. EDGAR's `companyfacts` XBRL endpoint (`data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`, already documented in `sources.yaml`'s `filings.endpoints.company_facts`) has this data for free. Verified live before writing any code, across 5 of the curated 10 tickers (AAPL/NVDA/TSLA/SOFI/PLTR): us-gaap XBRL tag names vary — `RevenueFromContractWithCustomerExcludingAssessedTax` is universal, but `Revenues` and `GrossProfit`/`OperatingExpenses` aren't (SOFI, a lender, reports neither of the latter two — no traditional cost-of-revenue structure). Also confirmed the same concept's fact array mixes single-quarter, cumulative year-to-date, and full-year values under one tag (10-Qs report both a quarter and its cumulative total), and that a 10-K's figures get re-reported as restated comparatives in later filings.

**Decision:**
- **Scope: annual (10-K) only**, last 5 fiscal years — mixing quarterly and annual totals in one trend table reads as noise (a $94B quarter next to a $416B year). `SecEdgarProvider.fundamentals()` (new method, `apps/api/app/market/providers/sec_edgar.py`) filters each us-gaap concept's fact array to `form=="10-K", fp=="FY"`, and a 350-380 day start/end span (excludes quarterly/cumulative facts under the same tag); dedupes by period-end keeping the most-recently-`filed` value (the latest restatement) per period. Tag fallback chains per line item (revenue tries 3 tag names, cost-of-revenue tries 2, others 1) — first tag with data for a period wins, later tags only fill gaps. `GrossProfit` computed from Revenue − CostOfRevenue when the company doesn't report it directly; left `null` (not computed) when neither revenue nor cost-of-revenue tags exist either, same "don't fabricate" discipline as everywhere else — verified this is a real, not hypothetical, case (SOFI).
- **Bypasses Router**, unlike every other capability: fundamentals doesn't fit quote/candles/news/calendar, and extending the `Provider` Protocol to add a 5th method would force every other provider (7 files) to grow a `NotImplementedError` stub just to satisfy strict-mypy structural typing for one SEC-only feature. Added a narrow `FundamentalsProvider` Protocol (`providers/base.py`, one method) instead, and exposed `cache`/`budget`/`sec_edgar` directly on `MarketGateway` (`dependencies.py`) so the endpoint can still apply the same cache-then-budget discipline by hand (`_fundamentals()` helper in `apps/api/app/api/market.py`) rather than skipping it — 24h cache TTL (matching `sources.yaml`'s declared `fundamentals_ttl`), and a real `budget.try_consume("sec_edgar", 1)` check before hitting the (potentially multi-MB) companyfacts endpoint.
- `StockDetail` gained a `financials: list[FinancialPeriod]` field, populated alongside quote/candles/filings/news in the existing bundled `/market/stock/{symbol}` endpoint — no new route.
- **Frontend:** new `CompanyFinancials.tsx` — a plain HTML table (Fiscal Year / Revenue / Gross Margin / Operating Expenses / Operating Income / Operating Margin / Net Income), horizontally scrollable, `null` fields render as "—". Placed between Price History and SEC Filings on the detail page.
- **Tape banner click-through**: `Tape.tsx`'s equity items (mirrors `TAPE_SPEC`'s `equity_quote` list, same hand-maintained-parallel convention as its existing `SYMBOL_LABELS` map) now render as `<Link>` to `/stock/{symbol}`; crypto/macro-series items stay plain `<span>`, same equity-only restriction as `QuoteGrid.tsx` (ADR-0020). The marquee duplicates its content for the seamless scroll loop — the `aria-hidden` copy's links get `tabIndex={-1}` so they're not a real (but invisible) keyboard tab stop; Tape isn't inside `DynamicGrid`'s click zone, so no `stopPropagation` is needed here the way `QuoteTile.tsx` needed it.

**Consequence:** 129 backend tests (was 125) — real fixture data extracted from AAPL's live companyfacts response, including a genuine same-period restatement-with-different-value case to prove the "latest filed wins" dedup logic, plus a synthetic no-GrossProfit-tag fixture to prove the Revenue−COGS fallback. 52 frontend tests (was 51). `make test`/`lint`/`typecheck`/`build` all green. Live-verified (unmocked provider call): AAPL's 5-year gross margin (41.8%→46.9%) and MSFT's (68.4%→67.9%) both land exactly where public knowledge says they should; MSFT's FY2022 `operating_expenses` genuinely renders "—" in production (that filing didn't tag `OperatingExpenses`), confirmed as the honest-gap path working as designed, not a bug. Deployed live: `amt-api` and `amt-web` both restarted, confirmed via `api.vespersoul.com/market/stock/{symbol}` and a real click from `vespersoul.com`'s Tape banner through to a stock page with live data.

**Not done / deliberately deferred:** No quarterly financials view. `fundamentals()`'s SEC budget consumption isn't unified with `news()`'s (they're two separate manual/Router-mediated paths sharing the same `sec_edgar` budget key in Redis, which is correct, but the "10 req/s good citizen" ceiling is enforced per-call-site rather than centrally) — acceptable at this traffic scale, worth revisiting if `SecEdgarProvider` grows a third access pattern.

---

## ADR-0020: Stock detail page — one bundled endpoint, click-through only from equity tiles

**Context:** User asked for a per-stock detail page ("history and filings") reachable by clicking a stock, plus a live deploy of the day's four new sources (ADR-0017/0018/0019). No dynamic route existed anywhere in `apps/web` yet — this is the first.

**Decision:**
- **Backend:** `GET /market/stock/{symbol}` (`apps/api/app/api/market.py`) bundles quote + 180-day candles + filings + 30-day company news into one `StockDetail` response (`apps/api/app/market/schemas.py`), same page-specific-aggregate pattern as `/tape`/`/world` — each piece its own try/except so one dead capability only blanks its own section. `SecEdgarProvider.news()` (ADR-0019) gained topic-scoping: when `topics` names a curated ticker it fetches only that company instead of all 10, so the detail page's filings call doesn't pull the whole curated set. `cost()` updated to match (real request count, not always 10).
- **Frontend click-through:** `QuoteGrid.tsx`'s tiles were plain non-interactive `<div>`s. Since `QuoteGrid` is a Server Component (can't hold `onClick`), extracted a new `"use client"` `QuoteTile.tsx` that renders a `<Link href="/stock/{symbol}">` with `event.stopPropagation()` — necessary because `DynamicGrid.tsx`'s Quotes/Heatmap cards already have a card-level `onClick` that opens the attention engine's "why am I seeing this" explain panel (same bubbling conflict `PanelControls.tsx` already solved for its own buttons in that zone). **Only `equity_quote` tiles are clickable** — `QuoteGrid` now tracks each symbol's source capability and renders crypto/macro-series tiles (BTC, VIX, 2Y, ...) as the old plain `<div>`, since a "stock" page showing history+filings doesn't apply to them. This makes both the Most Traded panel and DynamicGrid's Quotes block clickable for free; the Tape marquee was deliberately left alone (continuously scrolling, mixes the same asset classes, and isn't inside DynamicGrid's click zone anyway — lower value than the two static panels).
- **Chart:** `PriceHistoryChart.tsx`, hand-rolled SVG (no library), same discipline as `YieldCurveChart`/`Sparkline` — trend-colored line+area, hover crosshair with a date/price tooltip, x-axis thinned to ~6 labels regardless of window length.
- Any ticker works for quote/candles; filings/company-news honestly degrade to "unavailable" outside the curated 10 (ADR-0019) or when Finnhub has nothing — verified live with JPM (uncurated: real quote+chart+news, honest "no SEC filings tracked" message, not an error).

**Consequence:** Found and fixed two real bugs live (unmocked Playwright screenshots against a rebuilt local server, not just unit tests): (1) filings/news lists were unbounded — a heavily-covered ticker's 30-day company-news could return 50+ articles, blowing the page out to 16000px; capped at 15 filings / 10 news items, matching `NewsList.tsx`'s existing `.slice(0, 10)` precedent. (2) the chart's min-price label and the last x-axis date label both anchored to the bottom-right corner and visually overlapped; moved price labels to the left edge, clear of both corners. Also fixed a small pre-existing cosmetic bug surfaced by `sec_edgar`'s underscore-heavy name: `.source`'s `text-transform: capitalize` CSS only capitalizes the first letter of the whole string, not each word, so `"sec_edgar"` rendered as `"Sec_edgar"` — added a one-line `formatSource()` (space-replace-underscore) in both the new page and `NewsList.tsx` (same pre-existing bug there, e.g. `"federal_reserve"` → `"Federal_reserve"`) for consistency.

125 backend tests (was 121), 51 frontend tests unchanged in count but `QuoteGrid.test.tsx` continues passing against the new `QuoteTile`-based render. `make test`/`lint`/`typecheck`/`build` all green. **Deployed live**: `amt-api` restarted for the endpoint, `amt-web` rebuilt (`NEXT_PUBLIC_API_BASE_URL` is build-time-inlined per ADR history) and restarted; verified against the real `vespersoul.com` — clicked PLTR from the live homepage, landed on `/stock/PLTR` with real price/chart/filings/news, zero console errors. Also verified live (this same restart) that ADR-0017/0018/0019's four sources are actually serving: `regional_feds`/`sec_edgar`/`federal_reserve`/`treasury` all present in `/market/news` and `/market/calendar` responses.

**Not done / deliberately deferred:** Tape marquee stays non-clickable (see above). No `generateMetadata`/SEO for the new route. No historical-filing pagination beyond the most recent 15.

---

## ADR-0019: SEC EDGAR 8-K filings added, scoped to the equity universe already tracked live elsewhere

**Context:** ADR-0017 deferred SEC EDGAR specifically because it "needs a curated CIK list first — a real scope decision, not a quick add." `sources.yaml` calls it out as "the highest signal-to-noise 'news' source that exists, and it is free" — an 8-K is a legally-mandated, timestamped disclosure of a material event. The scope question is which tickers to track. Rather than inventing a new universe, reused the one this app already queries for real: the union of `TAPE_SPEC` (`apps/api/app/api/market.py`) and `MOST_TRADED_GROUPS` (`apps/web/src/app/page.tsx`), minus SPY/QQQ/DIA/IWM (ETFs don't file 8-Ks the way an operating company does) — same precedent `config/taxonomy.yaml` already set ("built from exactly the symbols the P1/P2 blocks already query for real, no aspirational instruments"). That's 10 tickers: AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA, AMD, PLTR, SOFI.

Resolved each ticker's CIK live from SEC's own `company_tickers.json` (keyless, public) rather than hand-typing them — all 10 matched cleanly. Verified the `submissions/CIK{cik10}.json` endpoint's actual shape live (not assumed from `sources.yaml`'s docs) against AAPL before writing the provider: parallel arrays (`form`, `acceptanceDateTime`, `accessionNumber`, `items`, `primaryDocument`, ...) under `filings.recent`, and confirmed the filing-document URL pattern (`sec.gov/Archives/edgar/data/{cik}/{accessionNoDashes}/{primaryDocument}`) resolves with a real 200.

**Decision:** `SecEdgarProvider` (`apps/api/app/market/providers/sec_edgar.py`) implements `news()` only — loops the 10-ticker map sequentially (not concurrently, to respect SEC's <=10 req/s ask even though 10 sequential awaited requests wouldn't come close to bursting it), fetches each company's submissions JSON with the required descriptive `User-Agent` (`sources.yaml`'s declared contact string), filters to `form == "8-K"` and `acceptanceDateTime >= since`, and maps the filing's `items` codes to a plain-English label for the headline (`2.02` → "Results of Operations and Financial Condition", etc. — `9.01` "Financial Statements and Exhibits" deliberately excluded from label selection since it's almost always a boilerplate companion item, not the newsworthy one). `calendar()`/`quote()`/`candles()` raise `NotImplementedError` — filings are already-happened disclosures, not scheduled events, so this stays a pure news source, not the `filings` capability `sources.yaml`'s fuller routing table separately describes. Wired into `dependencies.py`, a new `sec_filings_news` capability in `config/providers.yaml` (merged into `NEWS_CAPABILITIES`), and a self-imposed budget (`config/budgets.yaml`, 60/60s — SEC publishes no per-key limit, just the <=10 req/s ask).

**Consequence:** 121 backend tests now pass (was 118); `make lint`/`typecheck` still green. Live-verified end-to-end (unmocked provider call, not just the respx-mocked tests): 45 real 8-Ks surfaced across the 10 tickers over a 120-day window, correctly clustered around late-July/early-August Q2 earnings season with accurate item labels. Coverage is intentionally exactly the 10 tickers this app already shows real quotes for — expanding it later is a config-only change to `_COMPANIES`, but should stay tied to what's actually displayed elsewhere rather than growing independently. Tier-1 aggregators needing new API keys and Polymarket/Kalshi (needs a persistent events table) remain deferred, unchanged by this pass.

---

## ADR-0018: Regional Fed speeches added (Atlanta only); White House briefings and 4 of 5 regional-Fed feeds are dead

**Context:** User asked to continue adding sources from `sources.yaml` beyond ADR-0017's federal_reserve/treasury pair. The next two keyless tier-0 candidates that don't need a new API key are `regional_feds` (5 banks' speech RSS) and `white_house` (briefing-room RSS) — both already flagged `status: verify` in `sources.yaml` since free-tier/feed shapes "move constantly; do not assume, curl it first." Probed all 6 declared URLs live before writing any code, per that instruction and the project's non-negotiable against unverified data:

- **NY Fed** (`/rss/feeds/speeches`) — 302 → `/errors/404`. No working RSS discoverable anywhere on the site (checked the speeches page, footer, common alt paths).
- **SF Fed** (`/feed/`) — 200, but it's the general SF Fed blog (community-development posts, cash-ops announcements, housing data, occasional Daly remarks mixed in), not a speeches feed. No dedicated speech feed exists.
- **Chicago Fed** (`/rss/speeches`) — 404 on the declared URL; found a differently-named feed (`/forms/rss/Speeches`) that returns 200 but is stale and mislabeled — its actual content is 2022-2023 CFNAI index releases, last updated April 2023, not speeches at all.
- **Atlanta Fed** (`/rss/speeches`) — 404 on the declared URL; found the real one (`/rss/speechindex`), which checked out clean: real, current speeches (Bostic remarks through Feb 2026).
- **St. Louis Fed** (`/rss/speeches`) — 301 → `/404-error`. No working RSS discoverable.
- **White House** (`/briefing-room/feed/`) — 404. Also checked `/feed/` (404), `wp-json` (403), and looked for a feed link on `/remarks/`, `/presidential-actions/`, `/news/` (none found). RSS support appears to have been fully removed in a site redesign (only a Yoast SEO sitemap remains, no feed).

**Decision:** Implemented `RegionalFedsProvider` (`apps/api/app/market/providers/regional_feds.py`) with exactly one member — Atlanta — dict-shaped the same way `federal_reserve.py`'s `_FEEDS` is, so a bank can be added back the moment its feed is fixed. Did not implement `white_house` at all — zero working feed means there's nothing to adapt (the project's own rule: don't write an adapter for a source whose probe fails). Wired `regional_feds` into `apps/api/app/market/dependencies.py`, a new `regional_fed_news` capability in `config/providers.yaml` (merged into `NEWS_CAPABILITIES` in `apps/api/app/api/market.py`, same "merge not fallback" pattern as `macro_news`), and a `regional_feds` budget block in `config/budgets.yaml` (60/hour, matching `sources.yaml`'s declared self-imposed cap). Updated the root `sources.yaml` itself to record per-member findings (`status: dead`/`stable` notes on each of the 5 regional banks, `status: dead` on `white_house`) so the aspirational doc stays honest rather than silently drifting from what was actually verified.

**Consequence:** Found and fixed a real content-quality bug while live-testing the implemented provider (not mocked data): Atlanta Fed's titles carry embedded literal markup verified live (e.g. `...at <cite>Farm Journal</cite>'s Top Producer Summit`) that would render as raw angle-bracket text in a headline — added a small tag-stripping regex in `regional_feds.py` before it ever reached a test fixture. 118 backend tests now pass (was 115), `make lint`/`typecheck` still green. `regional_feds` ships covering one bank instead of the five `sources.yaml` originally listed — a materially smaller slice than planned, but an honest one; revisit the other four if their sites change again. SEC EDGAR (needs a curated CIK list), the tier-1 aggregators (need new API keys), and Polymarket/Kalshi (needs a persistent events table) remain deferred per ADR-0017, unchanged by this pass.

---

## ADR-0017: Federal Reserve (news) and Treasury FiscalData (calendar) added as primary sources, from a subset of SOURCES.md/sources.yaml

**Context:** User supplied `SOURCES.md` + `sources.yaml` (repo root) — a much larger aspirational source registry (~20 sources, tiered, with a full routing/dedup/provenance/importance-scoring/worker-cron architecture) than this app currently has, explicitly scoped for P1 and P5 ("read this before implementing P1 ... or P5"). Building that whole system is out of scope for "add some news and calendar sources" — it's multiple phases' worth of work (a `provenance`/`revision_of` DB schema, a dedup pipeline, an importance-ranking formula, worker cron scheduling) layered on top of infrastructure (a persistent events table) this app doesn't have yet. The doc's own stated rule pointed at the highest-value, lowest-effort slice: *"the calendar comes from primary sources... There is no reason to buy, scrape, or trust a middleman."*

**Decision:** Added exactly two new keyless, tier-0 primary sources, each wired into the *existing* `Provider`/`Router`/`config/providers.yaml` architecture (ADR-0004..0008) rather than adopting `sources.yaml`'s new schema wholesale:

- **`FederalReserveProvider`** (`news` capability, RSS: `press_monetary.xml` + `speeches.xml`) — plain stdlib `xml.etree.ElementTree`, no feed-parsing dependency, verified live before writing any code. `/market/news` changed from single-capability (`equity_news` only, with an unused `capability` query param no real caller ever varied) to always merging `equity_news` + `macro_news`, mirroring `/market/calendar`'s existing merge-not-fallback pattern.
- **`TreasuryProvider`** (`calendar` capability, `auctions_query` REST endpoint, filtered to `auction_date` within the requested window) — confirmed live that this endpoint returns genuinely forward-looking announced auctions (not just historical results). `CALENDAR_CAPABILITIES` gained `auction_calendar`.

Deferred entirely: SEC EDGAR (needs a curated CIK list — a real scope decision, not a quick add), every tier-1 aggregator needing a new API key (Marketaux, Alpha Vantage, FMP, Benzinga — this session only has keys for Finnhub/FRED/Alpaca), Polymarket/Kalshi odds-attachment (a real P5 feature, "attach live odds to a calendar event" needs the calendar to be a persistent, queryable table first), and the entire tiers/dedup/provenance/importance-scoring/cron-schedule system `sources.yaml` describes.

**Consequence:** Found and fixed a real usability bug surfaced by adding these: Finnhub's earnings calendar returns an unfiltered universe of every public company reporting same-day (481 entries on a single day in testing) — a pure chronological slice buried all 7 new non-earnings events (2 FRED, 5 Treasury) past the visible top-10 every time, making the new sources technically live but never actually seen. `EconomicCalendar.tsx` now reserves slots for non-earnings kinds before backfilling with earnings (`selectVisible`), re-sorted chronologically for display — a proportionate frontend fix, not the full importance-scoring formula `sources.yaml` describes for the same problem. `EconomicCalendar` also gained a third categorical dot (`auction` → the neutral/muted token, not a new hue — no palette re-validation needed). Revisit `sources.yaml`'s fuller vision (SEC filings, prediction-market odds, provenance tracking) as real P5 work once there's a persistent events table to build it against.

---

## ADR-0016: World map popup's currency/yield data comes from FRED (H.10 FX + OECD long-term rates), not a new provider

**Context:** ADR-0015 deferred currency and treasury-yield data entirely, on the assumption no wired provider offered them. User then asked for a per-country click popup showing the ETF, currency vs. USD, and bond yield "if available" — worth re-checking that assumption before building UI for data that doesn't exist. Verified live against the real FRED API (not assumed from docs, per CLAUDE.md's non-negotiable) before writing any code:

- FRED hosts the Fed's H.10 daily FX release as individual series (`DEXUSEU`, `DEXJPUS`, `DEXCAUS`, ...) — real, free, already-configured FRED key, no new provider. Confirmed for 20 of `WORLD_COUNTRIES`' currencies; Indonesia (IDR) and Saudi Arabia (SAR) have no H.10 series.
- FRED also mirrors OECD's monthly long-term (~10Y benchmark) government bond yield series (`IRLTLT01<CC>M156N`). Confirmed for 15 countries (Germany, Japan, UK, France, Italy, Canada, Australia, South Korea, Netherlands, Switzerland, Sweden, Spain, Mexico, South Africa; US uses the existing daily `DGS10`); not published for China, India, Brazil, Taiwan, Singapore, or Hong Kong.
- The H.10 series aren't quoted in one consistent direction (some are USD-per-foreign-unit, others foreign-units-per-USD) — recorded per-country as `fx_direction` in `WorldCountrySpec` (`apps/api/app/api/market.py`) so the endpoint emits one coherent display string (`"1 EUR = $1.1559"` vs `"$1 = 157.54 JPY"`) instead of pushing that vendor quirk onto the frontend.

**Decision:** `GET /market/world` now also queries `macro_series` (FRED) for the deduplicated set of FX and yield series across all countries, each in its own try/except so a FRED hiccup degrades only the currency/yield fields (`fx_label`/`bond_yield_pct` go `null`) without taking down the ETF-driven map fill, which is the primary visual. Countries with no real series for a field (Indonesia/Saudi Arabia FX+yield; China/India/Brazil/Taiwan/Singapore/Hong Kong yield) get `null` there permanently — the frontend popup shows "not available" rather than a fabricated number or a guess.

**Consequence:** No new provider, no new budget line — `macro_series`'s existing FRED-only chain absorbs this. `WORLD_COUNTRIES` grew from a 3-tuple to a small dataclass (`WorldCountrySpec`) to hold the extra fields legibly. Revisit if a future country needs FX/yield data FRED doesn't carry — that's a real new-provider decision, not a config tweak.

---

## ADR-0015: World map is index-view-only, proxied by country ETFs; geo data ships two small packages, no rendering library

**Context:** User asked for a world map coloring countries red/green, toggleable between index performance (default), currency, and treasury yield. None of the five wired providers (Finnhub/FRED/Alpaca/Binance/Hyperliquid) offer per-country index levels, FX rates, or non-US bond yields — FRED's yield curve is US Treasury only. Rendering actual country shapes also needs real geometry data, which no amount of hand-rolling (the ADR-0009 precedent for charts) can substitute for.

**Decision:** Ship index view only. Each tracked country is proxied by its most liquid US-listed single-country iShares MSCI ETF (`WORLD_INDEX_SPEC` in `apps/api/app/api/market.py` — SPY for the US, EWJ Japan, EWG Germany, MCHI China, INDA India, etc.), quoted through the existing `equity_quote` capability — real quotes, not fabricated country-level numbers, same non-negotiable as everywhere else. Currency and treasury-yield toggles are deferred until an FX/multi-country-bond provider exists. For geometry, added exactly two small packages — `world-atlas` (pre-built topology data, 50m resolution: the coarser 110m atlas silently drops small-area countries like Singapore/Hong Kong) and `topojson-client` (topology → GeoJSON, no rendering logic) — then hand-rolled the equirectangular lon/lat → SVG-path projection in `apps/web/src/lib/worldGeo.ts` rather than pulling in `react-simple-maps`/`d3-geo`. All of this runs server-side only (`WorldMap.tsx` is a Server Component); only the resulting compact path strings reach the client, so the ~650KB raw topology has zero bundle cost.

**Consequence:** `apps/web/package.json` gains its first non-Next/React runtime dependencies, a deliberate, narrow exception to the "zero extra deps" posture — justified because unlike a bar/line chart, country geometry isn't something hand-rolling can honestly replace. The atlas itself needed a real bug fix to use safely: some small territories (e.g. "Ashmore and Cartier Is.") share their parent country's ISO code as a *separate* topology feature, and a handful of disputed regions (Kosovo, Somaliland, N. Cyprus, Indian Ocean Ter., Siachen Glacier) carry no ISO code at all — both caused React key collisions until `worldGeo.ts` was changed to merge same-code features into one path and drop codeless ones (verified via a Testing Library key-collision regression test). Revisit currency/yield toggles once a real FX/bond provider is evaluated and budgeted, per docs/PLAN.md section 3.2's provider-matrix process.

---

## ADR-0014: Light theme is the default; dark is a redesigned second theme, not the removed original

**Context:** ADR-0009 shipped dark-only deliberately ("this is a terminal, not a marketing page"). User asked for a bright default theme, keeping dark available, with the dark palette itself redesigned toward a bluish, gradient-heavy, monospace-forward look (reference: `design-dark.png`).

**Decision:** Supersedes ADR-0009's "no light theme" call. Added a `data-theme` attribute on `<html>` (`light` | `dark`), a `ThemeToggle` client component persisting the choice to `localStorage`, defaulting to light for first-time visitors. Both palettes are token-complete in `globals.css` (no bare-`:root`-only definitions), so no component needed to change — every block already consumes tokens, not hardcoded colors, the same property that made the P2 redesign passes low-risk.

**Consequence:** Two palettes to keep in sync going forward instead of one; any new token added to light must get a dark counterpart and vice versa. First paint briefly shows the default (light) theme before the persisted choice applies on mount, same class of trade-off ADR-0013 already accepted for personalized layout — acceptable here since it self-corrects in one frame and doesn't flash unstyled content.

---

## ADR-0013: Personalized layout is fetched client-side, not via SSR cookie-forwarding

**Context:** P2's dashboard blocks are Server Components on a static/ISR
page (`revalidate: 15`, ADR-0009) — no per-request personalization. P3
needs the layout (and event tracking) to depend on the visitor's own
`profile_id` cookie. The idiomatic Next.js way to personalize a Server
Component is to read `cookies()` and opt the route into dynamic rendering,
but that means: (a) losing the static/ISR page entirely, and (b) Server
Components can't set cookies themselves — minting a first-visit profile_id
would need Middleware or a Route Handler forwarding Set-Cookie from the API,
adding a second network hop in front of every request.

**Decision:** The layout call (`GET /profile/layout`) and all event
tracking happen from the *browser*, directly against the API's public
origin, using its own cookie jar — no SSR involvement at all. This needed
two things `docs/STATE.md`'s existing `NEXT_PUBLIC_API_BASE_URL` couldn't
provide: that var is deliberately `127.0.0.1:8100` in production (a
same-box loopback fast-path for Server Component fetches, ADR-0010-adjacent
convenience) and is unreachable from a visitor's own browser. Added a
second var, `NEXT_PUBLIC_API_PUBLIC_URL` (`https://api.vespersoul.com` in
prod, same as the loopback value in local dev), used only by
`lib/attention.ts`'s client-side calls — and CORS
(`allow_credentials=True`, origin-locked to `WEB_ORIGIN`) on the API side,
since `web.` and `api.` are different origins even though they're
same-site for cookie purposes.

**Consequence:** The dashboard shell stays exactly the static/ISR page it
was (confirmed still prerenders after this phase — `apps/web`'s build
output). Trade-off: the personalized layout isn't in the initial HTML —
there's a visible beat (default 4/4/4 split → real layout) after the first
`/profile/layout` response lands, rather than arriving pre-shaped. Revisit
if that flash becomes a real showcase concern; the SSR/Middleware path
above is still available later without touching the attention-engine math.

---

## ADR-0012: P3's layout solver reallocates 3 existing blocks, not a per-node treemap

**Context:** docs/PLAN.md section 4.4's full vision is a fully dynamic set
of blocks — one per taxonomy node, arranged by a squarified treemap, with
K=6–10 competing nodes and an ε=10% exploration slot sampled from an
unengaged adjacent node. Building that means a registry of new
block-type-per-node renderers (a sector tile, a curve-segment card, a macro
indicator, …) on top of P2's fixed five block types — a materially larger
frontend surface than the attention-engine math itself.

**Decision:** Scope P3's layout solver (`app/attention/layout.py`) to
reallocate space between the three P2 blocks that already map cleanly onto
a disjoint set of taxonomy nodes — Quotes (`equities.us_large_cap.broad_market`
+ `crypto.majors.btc`), Yield Curve (`fixed_income.rates_ust.*`), Sector
Heatmap (the remaining `equities.us_large_cap.*` sector nodes). News/
Calendar stay at a fixed span: they're cross-cutting list UIs where "bigger"
isn't the same kind of preference signal a stat-tile's or a chart's area is.
Two consequences follow directly from a fixed 3-block candidate set: "top-K"
is a no-op (K is always 3), and there's no fourth "adjacent unengaged node"
to reserve ε=10% for — the existing MIN_AREA/MIN_COLUMNS floor (never let a
block go below its minimum, regardless of score) substitutes for that
purpose within this reduced scope. The plan's 6%/40% area clamps are also
rescaled: they're policy tuned for a treemap with many simultaneous blocks,
where 6% of the page is still legible; translated onto one 12-column row
shared by exactly 3 blocks, 6% rounds to under a column. `MIN_COLUMNS=2` /
`MAX_COLUMNS=8` is the same never-starve/never-dominate policy re-scaled to
this row's actual denominator.

**Consequence:** Ships the actual demo moment (DoD: "a 10-minute browsing
session visibly and sensibly reshapes the page") on real, decayed interest
scores with zero fabricated numbers, without a per-node block-rendering
system. The fully generic version — new block types dynamically appearing
per taxonomy node, real treemap geometry, true exploration sampling — is a
legitimate future phase, not a compromise on the math itself (decay,
propagation, softmax, clamping are all implemented exactly per section 4.3/
4.4). Revisit if/when a hiring-manager demo specifically wants to see a
brand-new node-driven block appear rather than existing blocks resize.

---

## ADR-0011: Attention engine's Postgres access is raw asyncpg, not an ORM

**Context:** Phase 3 (attention engine) is the first thing in this codebase
to actually touch Postgres — `database_url` has existed in `app/config.py`
since P0 but nothing read or wrote through it. The schema is small (three
tables: `profiles`, `events`, `interest_scores`) and every other layer in
this codebase already avoids heavy frameworks in favor of small, readable
abstractions (the market gateway's `Provider` Protocol classes, hand-rolled
budget/cache logic — see ADR-0004..0008).

**Decision:** `app/db.py` wraps a plain `asyncpg` connection pool; queries
are raw SQL against `db/schema.sql`, applied idempotently
(`CREATE TABLE IF NOT EXISTS`) at API startup rather than through a
migration framework — three tables don't yet justify Alembic's
metaprogramming and migration-history bookkeeping. `db/schema.sql` is
deliberately the single source of truth a reader can open and understand
the whole store in one pass (CLAUDE.md: "Prefer boring, inspectable code
over cleverness. This repo is read by hiring managers.").

**Consequence:** No ORM dependency, no N+1 footguns, but also no
auto-generated migrations — a schema change means hand-editing
`schema.sql` and confirming `CREATE ... IF NOT EXISTS`/`ADD COLUMN IF NOT
EXISTS` stays idempotent for existing databases. Revisit with a real
migration tool (Alembic or plain numbered `.sql` files + a tracking table)
if the schema outgrows a single file or needs destructive migrations.
`tests/attention/` hit a real Postgres (transaction-per-test, rolled back
in `conftest.py`'s `db_conn` fixture) rather than mocking SQL, matching how
`tests/market/` already avoids the network for HTTP providers but still
exercises real Redis semantics via `fakeredis` — there's no equivalent
in-memory Postgres, so CI gained a `postgres:16` service container
(`.github/workflows/ci.yml`) mirroring `docker-compose.yml`'s local setup.

---

## ADR-0010: Secrets live in `.ratx` files, not `.env`

**Context:** User preference: don't use the standard `.env` filename for
files holding real config/secrets, even locally. `.env` is the first thing
any scanner, `find`, or careless `cat *` glob goes looking for; a
non-standard name doesn't add cryptographic protection but does remove the
free win an opportunistic script gets from guessing the filename, and costs
nothing since both apps' config loaders take an explicit path anyway.

**Decision:** Renamed `.env.example` → `.ratx.example` (root, for
`apps/api`/`apps/worker`) and added `apps/web/.ratx.example`. Real files:
`apps/api/.ratx`, `apps/web/.ratx.local` (dev) / `apps/web/.ratx.production.local`
(prod) — never committed (`.gitignore` / `apps/web/.gitignore` updated from
`.env`/`.env*` to `.ratx`/`.ratx*`). `apps/api/app/config.py` and
`apps/worker/app/config.py`: `SettingsConfigDict(env_file=".ratx")`. Next.js
only auto-loads files literally named `.env*`, so `apps/web/next.config.ts`
gained a small hand-rolled loader (`loadRatxEnv`) that reads
`.ratx`/`.ratx.$(NODE_ENV)`/`.ratx.local`/`.ratx.$(NODE_ENV).local` in that
precedence — same low-to-high override order Next.js uses for `.env*` — and
never overrides a var already present in the real shell environment.

**Consequence:** No new dependency (the web loader is ~15 lines, no
`dotenv` package). One thing to remember: `next build` (not `next start`)
is what needs `apps/web/.ratx.production.local` present, since
`NEXT_PUBLIC_*` vars are inlined at build time via webpack's define plugin
— rebuild (`npm run build`) after changing it, a restart of `amt-web` alone
won't pick up a change. Verified: rebuilt web, confirmed the inlined value
in `.next/server` output, restarted both `amt-api`/`amt-web` systemd units,
reconfirmed `https://vespersoul.com` and `https://api.vespersoul.com` both
still serve correctly off the renamed files.

---

## ADR-0009: Dashboard blocks are Server Components with a fixed layout, no chart library, no client state

**Context:** P2 needs quote/sparkline/yield-curve/news/calendar/heatmap
blocks that render real numbers server-side (CLAUDE.md non-negotiable: no
number without a real provider response behind it) and must hit Lighthouse
≥90 with no layout shift. The interest-vector-driven treemap layout is P3,
not P2 — P2 explicitly asks for a "fixed default layout."

**Decision:** Every block (`apps/web/src/components/*.tsx`) is an `async`
React Server Component that calls `apps/web/src/lib/market.ts` directly
(server-to-server fetch to the FastAPI gateway, no client-side data
fetching, no state management library). Charts (`Sparkline`, `YieldCurve`,
`Heatmap`) are hand-rolled inline SVG against the dataviz skill's mark specs
rather than a charting dependency. The grid (`apps/web/src/app/page.module.css`)
is a static 12-column CSS Grid with `grid-column: span N` per block and
media-query overrides at the 1024px/768px breakpoints — no treemap solver
yet. Every `fetch` in `market.ts` catches failures and returns `null` rather
than throwing, and every block renders an explicit "unavailable" state on
`null` instead of a fabricated or zeroed number.

**Consequence:** Zero client JS shipped for data fetching or charting keeps
the bundle small (113KB first load) and first paint populated straight from
SSR/ISR (`next: { revalidate }` per block, matching docs/PLAN.md §3.1's
per-capability TTLs: 15s quotes, 60s candles, 300s news, 3600s calendar).
Cost: charts have no hover crosshair/tooltip beyond native SVG `<title>`,
and the layout is hand-placed, not data-driven — both explicitly deferred to
phase 3 (attention engine) rather than gold-plated now. Verified live: with
no Finnhub/FRED/Alpaca keys configured on this box, BTC (keyless Binance)
renders a real price end-to-end while every other block correctly renders
"unavailable" instead of guessing — see docs/STATE.md P2 entry.

---

## ADR-0008: Router's cache→budget→fallback policy is generic across quote/candles/news/calendar

**Context:** P1 shipped `Router.quote()` with cache-then-budget-then-vendor
fallback (ADR-0004..0006). P2's blocks need `candles` (sparklines), `news`,
and `calendar` too, and those capabilities need the identical policy — the
only real differences are the cache key shape and freshness TTL (quotes/
candles 30s, news 5min, calendar 1h per docs/PLAN.md §3.1).

**Decision:** `Router` now has one private generic `_call()` that all four
public methods (`quote`, `candles`, `news`, `calendar`) delegate to, each
supplying its cache-key format, `CallSpec` cost, Pydantic model for cache
deserialization, and a provider-invocation closure. `config/providers.yaml`
gained `equity_candles`/`crypto_candles`/`macro_candles`/`equity_news`/
`earnings_calendar`/`macro_calendar` chains — each currently single-provider
(candles/news/calendar aren't fallback alternatives to each other the way
`equity_quote`'s `[finnhub, alpaca]` is; each provider offers exactly one
source for each of these, per ADR-0006).

**Consequence:** Four capabilities share one tested code path instead of
four near-duplicate ones; new candle/news/calendar REST endpoints
(`/market/candles`, `/market/news`, `/market/calendar`) are thin wrappers.
`/market/calendar` merges `earnings_calendar` + `macro_calendar` (both
queried, not a fallback chain between them) the same way `/market/tape`
already merges multiple capabilities — one provider being down degrades that
slice, not the whole response.

---

## ADR-0007: Crypto symbols are canonical coin names; providers translate

**Context:** Binance's trading-pair convention ("BTCUSDT") and Hyperliquid's
coin-name convention ("BTC") disagree, but `config/providers.yaml` puts both
in the same `crypto_quote` fallback chain. If the Router passed the caller's
symbol straight through, a Binance outage would fail over to Hyperliquid
with a symbol Hyperliquid doesn't recognize ("BTCUSDT" isn't a Hyperliquid
coin), silently breaking the fallback the chain exists to provide.

**Decision:** Callers (the Router, `/market/tape`) always use canonical coin
symbols ("BTC", "ETH", assuming a USD-quoted pair). `BinanceProvider` maps
canonical → its own `<COIN>USDT` pair internally and maps back on the way
out, so `Quote.symbol` is always canonical regardless of which provider
served it. This is the same rule the canonical schema already applies
elsewhere (docs/PLAN.md section 3.4): vendor field names/formats never leak
past the provider boundary — symbol conventions are a vendor format too.

**Consequence:** The `crypto_quote` chain in `config/providers.yaml` can add
or reorder providers freely without the caller needing to know each
provider's symbol dialect. Current limitation: only USDT-quoted pairs are
reachable through Binance this way; a non-USD quote currency would need a
small extension to the mapping, not a redesign.

---

## ADR-0006: Providers implement only the capabilities their free tier has

**Context:** The `Provider` Protocol declares `quote`/`candles`/`news`/
`calendar`/`cost` uniformly, but no real vendor's free tier covers all four
data shapes — e.g. Finnhub's `/stock/candle` requires a paid plan; Binance and
Hyperliquid have no news or calendar; Alpaca's plan here is quotes/bars only,
not news (that's Finnhub's job per docs/PLAN.md section 3.2).

**Decision:** Each adapter implements only what it can honestly serve from
its actual free-tier access, and raises `NotImplementedError` — not fabricated
or empty data — for the rest. `ProviderError` is reserved for transient
failures (network, vendor 5xx, bad response shape) that the Router should
retry against the next provider in the chain; `NotImplementedError` means
"this provider was never going to serve this capability," which is a config
error, not something to fall back from.

**Consequence:** The Router only ever calls a provider for a capability it's
actually configured for in `config/providers.yaml` — `NotImplementedError`
is a backstop against a config mistake, not a normal runtime path. No code
path can return numbers that didn't come from a real provider response,
which is the project's first non-negotiable (`CLAUDE.md`).

---

## ADR-0005: Cache stores age, not just a TTL, so stale reads are possible

**Context:** The Router's contract is "budget breach returns cached-or-503,
never an unbounded vendor call." A plain Redis `EX` TTL can't do this: once
an entry expires it's just gone, so there's nothing left to fall back to
the moment a provider goes over budget right after its cache entry ages out.

**Decision:** `Cache` stores `{cached_at, payload}` and keeps entries alive
in Redis for up to 24h (`STALE_MAX_SECONDS`) regardless of the capability's
"fresh" TTL. `Cache.get` reports both the payload and whether it's still
fresh; the Router serves fresh cache immediately, and falls back to a stale
entry (marking it as such) only once every provider in the chain is either
erroring or over budget.

**Consequence:** A provider outage or budget breach degrades to "slightly
stale data" instead of "no data," as long as *something* was fetched in the
last 24h. Costs a little extra Redis memory (bounded by the 24h cap) for a
meaningfully better failure mode.

---

## ADR-0004: Fixed-window counter instead of a true token bucket for budgets

**Context:** docs/PLAN.md section 3.1 calls the budget mechanism a "token
bucket." A real token bucket (continuous refill) is more correct — no burst
of denials right at a window boundary — but needs either a Lua script or a
sorted-set sliding-window implementation in Redis to be atomic.

**Decision:** `BudgetManager` uses a plain `INCR` + conditional `EXPIRE` fixed
window instead: N calls allowed per window, counter resets when the window's
TTL lapses. A provider with no entry in `config/budgets.yaml` is unrestricted
by design, so ad-hoc/dev providers don't need a budget entry to work.

**Consequence:** Enforces "never exceed N calls per window" correctly and
atomically with two cheap Redis ops, at the cost of a theoretical 2x burst
right at a window boundary (N calls at the end of one window, N more right
after it resets). Acceptable for free-tier vendor limits, which exist to
prevent sustained abuse, not to police exact per-second pacing. Revisit if a
vendor's free tier turns out to bill/ban on burst rather than sustained rate.

---

## ADR-0003: Separate `.venv` per Python app, not a shared one

**Context:** `apps/api` and `apps/worker` are both Python but have different
dependency sets (FastAPI/uvicorn vs. APScheduler) and will diverge further as
each grows.

**Decision:** Each app owns its own `.venv` and `pyproject.toml`, installed
independently. No shared root-level Python environment.

**Consequence:** Slightly more disk/setup cost, but each app's dependency
graph stays legible and CI jobs for api/worker are fully independent (a
worker-only dependency bump can't break the api build). `packages/shared` is
TS-only for the same reason — Python code shares via HTTP/DB, not imports.

---

## ADR-0002: Dockerized dev Postgres/Redis on non-default ports (5433, 6380)

**Context:** This VPS already runs a native Postgres 16 and Redis (used by an
unrelated `chess` project) on the standard ports 5432/6379. The plan calls for
Postgres+Redis via Docker so `docker compose up` gives a reproducible dev
environment for anyone cloning the repo (a hiring manager included).

**Decision:** `docker-compose.yml` maps Postgres to host port 5433 and Redis
to 6380, leaving the native services on 5432/6379 untouched. `DATABASE_URL`
and `REDIS_URL` in `.env.example` point at the mapped ports.

**Consequence:** No port collision with existing infra. Anyone who clones this
repo elsewhere (no native Postgres/Redis running) still gets working defaults
since the app only ever talks to `localhost:5433`/`:6380`, never the
platform-default ports.

---

## ADR-0001: Node 20 via nvm, system Node left at 18

**Context:** The plan specifies Next.js 15, which (like the current tooling
ecosystem around it — eslint 9, latest create-next-app) requires Node ≥18.18,
and current `create-next-app`/tooling versions increasingly assume ≥20. The
VPS's system Node is 18.19.1. The VPS also runs a global `pm2` installed
against system Node, which we don't want to risk breaking.

**Decision:** Install Node 20 via `nvm` for the `ubuntu` user rather than
replacing system Node. `apps/web`, `scripts/dev.sh`, the Makefile, CI, and
`.pre-commit-config.yaml` all explicitly `nvm use default`/pin Node 20 rather
than relying on ambient `$PATH`.

**Consequence:** System Node/pm2 stay untouched. Every entry point that needs
Node 20 has to source nvm explicitly (documented in `CLAUDE.md`) — a fresh
non-login shell will otherwise silently pick up system Node 18 and things
will fail in confusing ways (e.g. `create-next-app` refusing to run, or a
subtly different eslint/typescript resolution).
