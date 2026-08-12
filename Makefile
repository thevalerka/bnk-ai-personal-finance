SHELL := /bin/bash
NVM_INIT := export NVM_DIR="$$HOME/.nvm"; [ -s "$$NVM_DIR/nvm.sh" ] && . "$$NVM_DIR/nvm.sh"; nvm use default >/dev/null;

.PHONY: dev test lint typecheck seed simulate

dev:
	./scripts/dev.sh

test:
	cd apps/api && .venv/bin/python -m pytest -q
	cd apps/worker && .venv/bin/python -m pytest -q
	$(NVM_INIT) cd apps/web && npm run -s test

lint:
	cd apps/api && .venv/bin/python -m ruff check . && .venv/bin/python -m mypy app
	cd apps/worker && .venv/bin/python -m ruff check . && .venv/bin/python -m mypy app
	$(NVM_INIT) cd apps/web && npm run -s lint

typecheck:
	$(NVM_INIT) cd apps/web && npm run -s typecheck

seed:
	@echo "seed: not implemented yet (lands with the Market Data Gateway in phase 1)"

simulate:
	@echo "simulate PERSONA=$(PERSONA): not implemented yet (lands with the attention engine in phase 3)"
