# config

Runtime configuration: `providers.yaml` (capability -> provider fallback
chains) and `budgets.yaml` (per-provider free-tier call budgets), both loaded
by `app/market/config_loader.py`. `taxonomy.yaml` (attention-engine DAG —
asset_class -> bucket -> node -> instrument, loaded by
`app/attention/taxonomy.py`) lands in phase 3. `personas/` (seeded interest
vectors for the "View as" switcher) lands alongside it.
