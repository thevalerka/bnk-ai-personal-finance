#!/usr/bin/env bash
# Runs web + api + worker together for local development, plus their
# Postgres/Redis dependencies via docker compose. Ctrl-C stops everything.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
nvm use default >/dev/null

docker compose up -d

pids=()
cleanup() {
  echo "Stopping..."
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

(cd apps/api && .venv/bin/uvicorn app.main:app --reload --port 8100) &
pids+=($!)

(cd apps/worker && .venv/bin/python -m app.main) &
pids+=($!)

(cd apps/web && npm run dev) &
pids+=($!)

wait
