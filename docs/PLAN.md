# Adaptive Markets Terminal — Build Plan

**Audience:** Claude Code (Sonnet), working autonomously phase by phase.
**Owner:** Valerio — this is both a working product and a hiring portfolio piece for finance/AI roles.

---

## 0. How to use this plan

- Work **one phase at a time**. Do not start phase N+1 until the Definition of Done (DoD) of phase N is green.
- At the start of every session: read `CLAUDE.md`, then `docs/STATE.md` (running log of what is done / what is next). Update `docs/STATE.md` at the end of every session.
- Every phase ends with: tests passing, `docker compose up` (or PM2) working from a clean checkout, and a short entry in `docs/DECISIONS.md` (ADR-style: context → decision → consequence).
- **Never fabricate market data.** Any number rendered in the UI or spoken by the AI must trace back to a real provider response or a seeded fixture explicitly labelled as demo data.
- Prefer boring, inspectable code over cleverness. This repo is read by hiring managers.

---

## 1. Product definition

A single full-width dashboard that **reallocates its own screen real estate** based on what the user actually looks at.

Three loops:

1. **Data loop** — normalized market data from free providers, cached server-side.
2. **Attention loop** — every interaction updates an interest vector; the interest vector drives the layout grid.
3. **AI loop** — a prompt bar under the main menu that can answer, chart, and *mutate the dashboard*; plus a right-hand rail of proactive event-driven suggestions.

Trading is phase 6+, non-custodial, on-chain only.

### Showcase requirements (these are product features, not extras)

These exist because the primary user is a hiring manager who will spend 90 seconds on the site:

- **Instant value with zero cold start.** First paint shows a populated global tape, not an empty state.
- **"View as" persona switcher** — Macro / Equity PM / Options trader / Crypto native. Loads a pre-seeded interest vector so a visitor can see the personalization work in one click instead of ten minutes of browsing.
- **"Why am I seeing this" panel** — click any block, see the interest weights, decay, and source events that put it there at that size. This is the single most persuasive thing on the site for a quant/AI hiring manager.
- **`/architecture` page** — live system diagram, provider status, cache hit rates, request budget consumption, p95 latency. Real numbers from the running system.
- **`/notes` engineering log** — short posts on the personalization math, the provider abstraction, the agent tool design.

---

## 2. Architecture

```
Browser (Next.js 15, App Router, RSC)
   │  SSE for streams, REST for the rest
   ▼
API (FastAPI, Python 3.12)
   ├── /market      → Market Data Gateway (provider adapters + Redis cache + budget manager)
   ├── /profile     → Attention engine (event ingest → interest vector → layout plan)
   ├── /agent       → Anthropic Messages API, tool-use loop, SSE streaming
   ├── /briefing    → scheduled suggestion generation (cluster-level, cached)
   └── /wallet      → read-only chain state (phase 6)
   ▼
Postgres (profiles, events, interest vectors, briefings, cached fundamentals)
Redis (hot quotes, rate-limit budgets, agent session state)
Workers (APScheduler or arq): ingestion, briefing generation, decay job
```

**Deployment:** the existing Ubuntu VPS. Caddy reverse proxy + Let's Encrypt in front, PM2 running three processes (`amt-web`, `amt-api`, `amt-worker`). Postgres + Redis via Docker on the same box. Subdomain, e.g. `terminal.<domain>`.

**Why Python for the API:** reuses existing quant/data tooling and keeps the numerical parts (decay, vector math, curve interpolation) in one language. Next.js stays a presentation layer — no business logic in the frontend.

---

## 3. Data layer

### 3.1 Hard rule: the Gateway pattern

The browser **never** talks to a data vendor. All providers sit behind `app/market/providers/*.py`, each implementing:

```python
class Provider(Protocol):
    name: str
    async def quote(self, symbols: list[str]) -> list[Quote]: ...
    async def candles(self, symbol: str, tf: str, limit: int) -> list[Candle]: ...
    async def news(self, topics: list[str], since: datetime) -> list[NewsItem]: ...
    async def calendar(self, window: DateRange) -> list[Event]: ...
    def cost(self, call: CallSpec) -> int   # budget units consumed
```

A `Router` picks a provider per capability + asset class, with declared fallback chains. A `BudgetManager` in Redis holds a token bucket per provider per window and **refuses** calls that would breach the free tier rather than getting the key banned. Every response is cached with a per-capability TTL (quotes 15–30s, news 5min, calendar 1h, fundamentals 24h, macro series 6h).

Consequence: swapping Finnhub for Twelve Data is a config change. Say this out loud on the `/architecture` page.

### 3.2 Provider matrix (all free tiers — verify limits at implementation time, they move)

| Need | Primary | Fallback | Notes |
|---|---|---|---|
| US equity quotes, news, earnings calendar | **Finnhub** (free ~60 req/min) | Twelve Data (~800 req/day) | Most generous free tier; news carries sentiment |
| Real-time equity trades/quotes (IEX feed) | **Alpaca** (free real-time IEX + paper trading) | — | Also the natural paper-trading backend |
| Reference data, EOD, historical | **Polygon/Massive Stocks Basic ($0 tier)** | Stooq CSV, Tiingo | Low rate, fine for backfills |
| Fundamentals, filings | **SEC EDGAR** (free, requires descriptive User-Agent) | FMP free EOD fundamentals | Company facts JSON is excellent and uncapped in practice |
| **Fixed income / macro / curves** | **FRED API** (free) | US Treasury FiscalData API, ECB SDW | DGS1..DGS30 series → live yield curve, 2s10s, real yields, breakevens. This is the backbone of the fixed-income view |
| Economic calendar (FOMC, CPI, NFP) | FRED release calendar + Finnhub calendar | scraped fallback | FOMC dates are known months ahead — seed them statically too |
| Crypto spot/perp | **Binance public REST/WS** (no key), **Hyperliquid public API/WS** | CoinGecko demo key | Free, no auth, websockets |
| On-chain / RWA prices | **Pyth Hermes**, Jupiter quote API | — | Needed anyway for phase 6 |
| Commodities / FX | Twelve Data, Stooq, FRED (DCOILWTICO etc.) | — | |
| News flow, event detection | Provider news + **RSS aggregation** + GDELT | — | Dedupe by URL hash + title trigram similarity |

Scraping is the **last** resort and is isolated in `providers/scrape/` with its own circuit breaker, so a broken selector can never take down the app. `yfinance`-style sources are treated as unreliable by default.

### 3.3 MCP — consume *and* publish

- **Consume:** wire Alpha Vantage's official MCP server and/or a Finnhub MCP into Claude Code itself, so *development* is faster. Do not put MCP on the request path of the web app — the Gateway with explicit budgets is the production path.
- **Publish (differentiator):** ship `mcp/terminal-mcp/` — an MCP server exposing this platform's own tools (`get_curve`, `get_interest_profile`, `screen_universe`, `get_briefing`). Ship it as a small standalone package with a README. Being an MCP *author* is a much stronger signal than being an MCP user, and it makes the whole platform usable from Claude Desktop.

### 3.4 Canonical schema

Normalize everything to internal types before it leaves the Gateway: `Instrument{id, symbol, class, exchange, currency}`, `Quote`, `Candle`, `CurvePoint`, `NewsItem{id, ts, headline, url, source, tickers[], topics[]}`, `Event{ts, kind, importance, title, tickers[], topics[]}`. Providers translate into these; nothing downstream ever sees a vendor field name.

---

## 4. Attention engine (the core IP)

### 4.1 Identity

Anonymous-first, matching the no-KYC ethos: a signed HTTP-only cookie holds a `profile_id` (UUID) issued on first visit. No email, no password. Optional upgrade paths:
- **Sign In With Solana (SIWS)** — wallet becomes the durable identity, profile follows the wallet across devices.
- Export/import profile as a JSON blob ("your data is yours" — say it on the page).

### 4.2 Taxonomy

A DAG in `config/taxonomy.yaml`:

```
asset_class (equities, fixed_income, fx, commodities, crypto, derivatives)
  └── bucket (us_large_cap, rates_ust, credit_ig, energy, precious_metals, majors, perps, options_vol …)
        └── node (sector, region, theme: "ai_capex", "fed_policy", "tokenization")
              └── instrument (AAPL, DGS10, BTC, CL=F …)
```

Every event maps to one or more nodes. Weight propagates up the DAG with a decay factor per level (child 1.0, parent 0.6, grandparent 0.3).

### 4.3 Event → interest vector

Ingest events (batched, `sendBeacon`, ~2s debounce):

| Event | Weight |
|---|---|
| block impression (>1s in viewport) | 0.2 |
| dwell, per additional 5s visible | 0.3 |
| hover / tooltip open | 0.5 |
| click into detail | 2.0 |
| chart interaction (zoom, timeframe change) | 2.5 |
| search / symbol lookup | 3.0 |
| agent prompt mentioning node | 4.0 |
| explicit pin / follow | 8.0 |
| explicit hide / mute | −10.0 (and set a floor override) |

Score per node with **exponential decay**, half-life 7 days:

```
s_n(t) = Σ_i w_i · 2^(−(t − t_i)/T½)
```

Recompute lazily on read (cheap: store `(score, last_updated)` per node and decay on access), plus a nightly compaction job that folds raw events older than 30 days into per-node aggregates.

### 4.4 Interest vector → layout

This is the literal answer to "the percentage of space reflects preferences":

1. Take the top-K nodes at the level being laid out (K = 6–10 depending on viewport).
2. `w = softmax(s / τ)` with temperature τ tuned so a strong preference doesn't collapse the grid to one block (start τ = 1.5, expose it in a debug drawer).
3. Clamp: `min 6%`, `max 40%` per block; renormalize.
4. **Exploration:** reserve ε = 10% of the area for a node the user has *not* engaged with, sampled from adjacent taxonomy nodes. Prevents a dead-end filter bubble and makes the "we follow the user into options/commodities" behavior actually discoverable.
5. Emit a `LayoutPlan`: ordered list of `{block_type, node, area_weight, priority}`.
6. Frontend renders it as a CSS Grid with `grid-template-areas` computed from a **squarified treemap** over the weights — full width, no gaps, deterministic for a given plan. Snap to a 12-column grid on desktop, collapse to weight-ordered single column on mobile.

**Cold start (first visit):** default vector — equities 35 / fixed income 25 / macro 15 / crypto 10 / commodities 8 / fx 7. Plus the global tape: indices, 2s10s, DXY, WTI, gold, BTC, VIX. Layout changes must be **animated and slow** (FLIP transitions, ~400ms, and never mid-interaction) — a dashboard that reflows while you read it feels broken; a dashboard that has visibly rearranged itself when you come back feels alive.

### 4.5 DoD for the engine

Golden tests: a scripted event sequence ("user clicks into 5 rates blocks over 3 days") produces an expected layout plan within tolerance. Include a `scripts/simulate_user.py` that replays personas — this is also what powers the "View as" switcher.

---

## 5. AI layer

### 5.1 The prompt bar

Full-width input directly beneath the main menu. Placeholder rotates through real, high-value examples ("Why is the curve steepening?", "Show me tomorrow's earnings that matter for my view", "Compare NVDA implied vol to realized").

Backend: `/agent/stream` → Anthropic Messages API with tool use, streamed over SSE. **Model choice:** Sonnet for the interactive path (latency), a cheaper/faster tier for classification and topic-tagging of events.

Tools exposed to the agent:

| Tool | Purpose |
|---|---|
| `get_quotes(symbols)` | live prices via Gateway |
| `get_series(series_id, range)` | FRED / candles |
| `get_curve(country, date?)` | yield curve, spreads |
| `get_news(topics, since)` | headlines |
| `get_calendar(window)` | earnings, macro events |
| `screen(filters)` | universe screening |
| `render_chart(spec)` | returns a chart spec the frontend renders inline |
| `add_block(node, type)` | **mutates the dashboard** |
| `set_focus(node, weight)` | explicit interest boost |
| `explain_layout()` | reads the user's own interest vector |

`add_block` / `set_focus` are the demo moment: the user types "I care about European credit" and the page rebuilds itself. Make sure this is smooth — it's the screenshot that goes in the application.

**Rules baked into the system prompt:** no number without a tool call; cite the source and timestamp of every figure; explicitly refuse to give personalized investment advice, and say why; distinguish "what happened" from "what people think will happen"; if data is stale or a provider failed, say so rather than hedging vaguely.

### 5.2 Suggestion rail (right column)

Not generated per user per request — that's a cost sink. Design:

1. Worker runs every 15 min: pulls calendar + earnings + top news + notable moves → builds an **event pool** with importance scores.
2. Users are bucketed into ~12 **interest clusters** (k-means over interest vectors, recomputed nightly). One LLM generation per cluster per cycle → cached cards.
3. Per-user: rank the cluster's cards against that user's exact vector, drop muted nodes, slot the top 5–8. Pure math, no LLM call.
4. Cards are typed: `earnings_today`, `macro_event`, `speech` (FOMC pressers, political speeches), `unusual_move`, `curve_signal`, `crossmarket_note`, `learn` (explainer for a node the user is newly exploring).
5. Every card carries a source link and a timestamp. Cards with no source do not ship.

Generic-first: an anonymous first-visit user gets the "global cluster" rail immediately. Personalization kicks in from event #1.

### 5.3 Cost control

Hard monthly token budget in config, enforced at the API layer. Per-IP and per-profile rate limits on the prompt bar (public site = public abuse surface). Prompt caching for the system prompt and tool definitions. Log token spend per endpoint and surface it on `/architecture` — showing you instrument your own LLM costs is itself a hiring signal.

---

## 6. Trading layer (phase 6+, feature-flagged, off by default)

Non-custodial, permissionless, **client-side signing only**. The backend never sees a private key, never holds funds, never routes an order it did not receive from a user-signed transaction.

**Stage A — read-only.** Wallet connect (Solana wallet-adapter: Phantom/Backpack; SIWS for auth). Show on-chain balances, positions, P&L. Zero trading risk, still demonstrates the whole integration.

**Stage B — Solana RWA spot.** Tokenized equities/ETFs (xStocks-style tokens, Ondo's tokenized products) routed through the Jupiter aggregator: quote → user signs → submit → track. Start on devnet with mocked mints, then mainnet behind the flag with a tiny size cap.

**Stage C — Hyperliquid.** HyperCore spot (tokenized equities now trade there) and HIP-3 permissionless perps for equity/commodity exposure. Use Hyperliquid's API-wallet ("agent wallet") model so a scoped, revocable key signs orders and the master key never leaves the user's wallet. Websocket for fills and position updates.

**Non-negotiables:**
- Prominent, honest disclosure: this is unregulated on-chain trading; tokenized-equity legal status is in flux and varies by jurisdiction; users are responsible for their own compliance.
- No custody, no order routing on the user's behalf, no discretionary execution. The AI may *propose*; only the user signs.
- Kill switch: one env var disables the whole trading surface.
- Given the regulatory picture, keep the public demo in **read-only + paper mode** (Alpaca paper account) and gate live signing behind explicit opt-in. A hiring manager needs to see the integration works, not to be able to lose money on your portfolio site.

---

## 7. Phases

### P0 — Foundations (0.5 day)
Monorepo, `CLAUDE.md`, `docs/STATE.md`, `docs/DECISIONS.md`, ruff+mypy+pytest, eslint+tsc+vitest, pre-commit, GitHub Actions CI, `.env.example`, Docker compose for Postgres+Redis.
**DoD:** clean checkout → `make dev` runs web+api+worker; CI green.

### P1 — Market Data Gateway (2 days)
Provider protocol, Finnhub + FRED + Alpaca + Binance/Hyperliquid adapters, Router, BudgetManager, Redis cache, canonical schema, `/market/*` endpoints. Recorded-fixture tests (VCR-style) so tests never hit the network.
**DoD:** `GET /market/tape` returns a normalized global tape; killing the primary provider transparently falls back; budget breach returns cached-or-503, never an unbounded vendor call.

### P2 — Static dashboard (2 days)
Full-width shell, main menu, prompt bar (non-functional), global tape, block components: quote grid, sparkline, yield curve, news list, calendar, heatmap. Fixed default layout. Design system, dark-first, dense-but-readable (this is a terminal, not a marketing page — but it should not look like a 2013 bootstrap admin theme).
**DoD:** Lighthouse ≥90, first paint populated, no layout shift, works at 1280 / 1920 / 2560 and on mobile.

### P3 — Attention engine (3 days)
Taxonomy, event ingest, decay, interest vector, treemap layout solver, FLIP animations, "Why am I seeing this" panel, persona simulator + "View as" switcher.
**DoD:** golden layout tests pass; a 10-minute browsing session visibly and sensibly reshapes the page; explain panel numbers reconcile with the stored vector.

### P4 — Agent (2 days)
Tool-use loop, SSE streaming, inline chart rendering, `add_block`/`set_focus` dashboard mutation, rate limits, token budget, prompt caching, refusal/guardrail tests.
**DoD:** ten canned questions answered with sourced figures; zero fabricated numbers in the eval set; dashboard mutation works end-to-end.

### P5 — Suggestion rail (2 days)
Event pool, cluster generation, per-user re-ranking, card types, mute/pin feedback loop into the interest vector.
**DoD:** rail populated on first visit; a rates-heavy persona gets visibly different cards from a crypto persona; every card has a live source link.

### P6 — Wallet + read-only chain (1.5 days)
SIWS auth, profile migration cookie→wallet, balances, RWA/Hyperliquid position view.
**DoD:** connect wallet, see real holdings, profile persists across devices.

### P7 — Execution, flagged (2–3 days)
Jupiter route + sign + submit on devnet; Hyperliquid agent-wallet order flow on testnet; Alpaca paper for equities; full disclaimers; kill switch.
**DoD:** end-to-end trade on testnet/devnet/paper with confirmations and error handling; flag off in production by default.

### P8 — Showcase polish (1.5 days)
`/architecture` live metrics page, `/notes` engineering log with 3 posts, `terminal-mcp` package published, README with GIFs, OG images, seeded demo profiles, uptime + status. Recruiter path: landing → 1-click persona → prompt bar demo → architecture page.
**DoD:** a cold visitor understands what this is and that you built it, in under 60 seconds.

---

## 8. Repo layout

```
/apps/web            Next.js
/apps/api            FastAPI
/apps/worker         schedulers
/packages/shared     shared TS types generated from Pydantic models
/mcp/terminal-mcp    published MCP server
/config              taxonomy.yaml, providers.yaml, budgets.yaml, personas/
/docs                STATE.md, DECISIONS.md, ARCHITECTURE.md, PLAN.md
/scripts             simulate_user.py, seed.py, backfill.py
```

Generate TS types from the Pydantic models (`datamodel-code-generator` or an OpenAPI → TS step) so the frontend can never drift from the API.

---

## 9. `CLAUDE.md` seed

```md
# Adaptive Markets Terminal
Full-width market dashboard whose layout reallocates itself from a decayed
per-user interest vector. Python/FastAPI backend, Next.js frontend, Postgres+Redis.

## Non-negotiables
- No market number may be rendered or spoken without a real provider response
  behind it. Fixtures must be labelled as demo data in the UI.
- No vendor SDK types past the Gateway boundary. Canonical schema only.
- No provider call may exceed its declared free-tier budget. BudgetManager decides.
- Backend never holds keys or custody. Client-side signing only.
- Not investment advice. The agent proposes; the user decides and signs.

## Workflow
1. Read docs/STATE.md before anything.
2. One phase at a time; DoD in docs/PLAN.md must be green before moving on.
3. Tests before merge: pytest + vitest + typecheck + lint.
4. Log every architectural choice in docs/DECISIONS.md.
5. Update docs/STATE.md at session end.

## Commands
make dev / make test / make lint / make seed / make simulate PERSONA=macro
```

---

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Free tiers change or die mid-build | Gateway + fallback chains; provider config in YAML; never more than a day's work to swap |
| Layout reflow feels chaotic | Slow animation, hysteresis (only re-layout when weights move >5%), never reflow during interaction |
| LLM cost blowup on a public site | Cluster-level generation, caching, per-IP limits, hard budget with graceful degradation to non-AI mode |
| Fabricated figures embarrass you in front of a hiring manager | Tool-call-only numbers + an eval suite that fails CI on unsourced digits |
| Tokenized-equity regulatory shift | Trading behind a flag, read-only/paper by default, disclaimers, kill switch |
| Scope creep across six asset classes | Equities + fixed income are the only *complete* verticals in P1–P5; other classes get tape-level support and deepen only when a user's vector pulls there |

---

## 11. First session instruction

Start P0. Scaffold the monorepo, write `CLAUDE.md` and `docs/STATE.md`, get CI green, then open a PR titled `P0: foundations` with a summary of choices made. Do not start P1 in the same session.
