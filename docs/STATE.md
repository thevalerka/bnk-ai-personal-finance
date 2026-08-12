# State

Running log of what's done and what's next. Update at the end of every session.
Newest entry first.

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
