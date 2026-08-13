# Decisions

ADR-style log: context → decision → consequence. Newest first.

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
