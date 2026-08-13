# State

Running log of what's done and what's next. Update at the end of every session.
Newest entry first.

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
