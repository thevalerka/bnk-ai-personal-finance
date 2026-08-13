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


@lru_cache
def get_settings() -> Settings:
    return Settings()
