from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".ratx", extra="ignore")

    env: str = "development"
    database_url: str = "postgresql://amt:amt@localhost:5433/amt"
    redis_url: str = "redis://localhost:6380/0"

    finnhub_api_key: str = ""
    fred_api_key: str = ""
    alpaca_api_key: str = ""
    alpaca_api_secret: str = ""

    # Phase 4 — Agent (docs/PLAN.md section 5). Sonnet for the interactive
    # prompt-bar path per the plan's own model choice (latency over Opus's
    # extra reasoning depth for a chat-speed tool-use loop).
    anthropic_api_key: str = ""
    agent_model: str = "claude-sonnet-5"
    # Hard cost ceiling (plan section 5.3) — a rough token count, not a
    # dollar figure, so it doesn't need updating every time list pricing
    # changes. Degrades to a 503 rather than an unbounded vendor bill once
    # exceeded for the remainder of the calendar month.
    agent_monthly_token_budget: int = 2_000_000
    # Public-site abuse surface (plan section 5.3): the prompt bar is the
    # one endpoint on this API a visitor can make it call an LLM from,
    # repeatedly, for free.
    agent_rate_limit_per_minute: int = 10

    # Signs the anonymous profile_id cookie (docs/PLAN.md section 4.1) so a
    # client can't forge someone else's profile. Dev-only default — real
    # deployments must set a random value in .ratx.
    secret_key: str = "dev-insecure-secret-change-in-ratx"

    # The one frontend origin allowed to make credentialed (cookie-bearing)
    # cross-origin requests — /profile/* is called directly from the
    # browser (event tracking, live layout), unlike /market/* which is only
    # ever fetched server-side by Next.js Server Components.
    web_origin: str = "http://localhost:3000"

    # Hyperliquid trading (docs/DECISIONS.md ADR-0028) — testnet only.
    # Signing/submission happen entirely client-side; these are the public
    # values the frontend needs to attach our commission to a trade.
    # Blank builder_address means trading isn't configured yet, same
    # degrade-honestly pattern as a blank anthropic_api_key: /trading/config
    # reports `configured: false` rather than the UI silently offering a
    # dead flow.
    hyperliquid_builder_address: str = ""
    # Tenths of a basis point (10 = 1bp) — Hyperliquid's own field unit.
    # Cap is 100 (10bp) for perps.
    hyperliquid_builder_fee_tenths_bp: int = 10
    hyperliquid_testnet_base_url: str = "https://api.hyperliquid-testnet.xyz"
    trading_rate_limit_per_minute: int = 20


@lru_cache
def get_settings() -> Settings:
    return Settings()
