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

    # Signs the anonymous profile_id cookie (docs/PLAN.md section 4.1) so a
    # client can't forge someone else's profile. Dev-only default — real
    # deployments must set a random value in .ratx.
    secret_key: str = "dev-insecure-secret-change-in-ratx"

    # The one frontend origin allowed to make credentialed (cookie-bearing)
    # cross-origin requests — /profile/* is called directly from the
    # browser (event tracking, live layout), unlike /market/* which is only
    # ever fetched server-side by Next.js Server Components.
    web_origin: str = "http://localhost:3000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
