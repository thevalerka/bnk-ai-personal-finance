# Adaptive Markets Terminal

Full-width market dashboard whose layout reallocates itself from a decayed
per-user interest vector. Python/FastAPI backend, Next.js frontend, Postgres+Redis.

Full product/architecture spec: `docs/PLAN.md`. Read that before starting any phase.

## Non-negotiables

- No market number may be rendered or spoken without a real provider response
  behind it. Fixtures must be labelled as demo data in the UI.
- No vendor SDK types past the Gateway boundary. Canonical schema only.
- No provider call may exceed its declared free-tier budget. BudgetManager decides.
- Backend never holds keys or custody. Client-side signing only.
- Not investment advice. The agent proposes; the user decides and signs.

## Workflow

1. Read `docs/STATE.md` before anything.
2. One phase at a time; the Definition of Done for each phase (`docs/PLAN.md`
   section 7) must be green before moving on.
3. Tests before merge: `make test` (pytest × 2 + vitest) and `make lint`
   (ruff + mypy × 2 + eslint) must both pass.
4. Log every architectural choice in `docs/DECISIONS.md`.
5. Update `docs/STATE.md` at session end.

## Repo layout

```
/apps/web            Next.js 15 (App Router), Node 20 via nvm
/apps/api            FastAPI, own .venv, ruff+mypy+pytest
/apps/worker         APScheduler jobs, own .venv, ruff+mypy+pytest
/packages/shared     shared TS types generated from Pydantic models (not wired yet)
/mcp/terminal-mcp    published MCP server (phase 8, not started)
/config              taxonomy.yaml, providers.yaml, budgets.yaml, personas/
/docs                PLAN.md, STATE.md, DECISIONS.md
/scripts             dev.sh; simulate_user.py / seed.py / backfill.py land later
```

## Commands

- `make dev` — runs web + api + worker + docker-compose Postgres/Redis together
- `make test` — pytest (api, worker) + vitest (web)
- `make lint` — ruff + mypy (api, worker) + eslint (web)
- `make typecheck` — tsc --noEmit (web)
- `make seed` / `make simulate PERSONA=macro` — stubs, land in phase 1 / phase 3

## Environment notes specific to this VPS

- System Node is 18.19.1 (too old for Next.js 15+). Node 20 is installed via
  `nvm` for the `ubuntu` user; `scripts/dev.sh` and the Makefile source it
  explicitly. Don't assume `node`/`npm` on bare `$PATH` is v20 in a fresh
  non-login shell — always go through `nvm use default` first.
- `apps/api` and `apps/worker` each have their own `.venv` (not a shared one).
- Dockerized dev Postgres/Redis run on **non-default** host ports (5433, 6380)
  because the box also runs a native Postgres 16 + Redis used by an unrelated
  project (`chess` DB) — see `docs/DECISIONS.md` ADR-0002.
- `docker` requires either a fresh login shell (group membership) or
  `sg docker -c '...'` in the same shell where the group was just added.
