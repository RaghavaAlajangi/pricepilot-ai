from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Values come from the environment / .env file.

    Empty ``database_url`` or ``redis_url`` switch those integrations off,
    so the backend can also run standalone from the CSV (e.g. on Cloud Run).
    """

    app_name: str = "PricePilot AI"
    log_level: str = "INFO"

    # Data layer: Postgres if set, otherwise the CSV is loaded in memory.
    database_url: str = ""
    dataset_path: str = "data/dataset.csv"

    # Optional Redis cache for ML/agent results.
    redis_url: str = ""
    cache_ttl_seconds: int = 86400
    cache_max_size: int = 512

    # LLM (required only for the /agents endpoints).
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # API key that the frontend must send as X-API-Key to reach agent endpoints.
    # Generate with: openssl rand -hex 32
    app_api_key: str = ""

    # CORS: comma-separated list of allowed frontend origins (no trailing slashes).
    # Example: https://app.example.com,https://staging.example.com
    frontend_origins: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance (one read of the environment per process)."""
    return Settings()
