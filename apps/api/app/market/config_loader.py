from pathlib import Path

import yaml

from app.market.budget import ProviderBudget

CONFIG_DIR = Path(__file__).resolve().parents[4] / "config"


def load_provider_chains() -> dict[str, list[str]]:
    with (CONFIG_DIR / "providers.yaml").open() as f:
        data: dict[str, list[str]] = yaml.safe_load(f)
    return data


def load_budgets() -> dict[str, ProviderBudget]:
    with (CONFIG_DIR / "budgets.yaml").open() as f:
        raw = yaml.safe_load(f)
    return {name: ProviderBudget(**limits) for name, limits in raw.items()}
