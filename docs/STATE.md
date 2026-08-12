# State

Running log of what's done and what's next. Update at the end of every session.
Newest entry first.

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
