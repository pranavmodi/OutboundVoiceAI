"""Backfill backend config — loaded from env / .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    backfill_backend_port: int = 8001
    backfill_database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/backfill"
    backfill_cors_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,"
        "http://localhost:3001,http://127.0.0.1:3001"
    )
    radflow_webhook_enabled: bool = True
    radflow_webhook_token: str = ""
    backfill_simulator_enabled: bool = True


settings = Settings()
