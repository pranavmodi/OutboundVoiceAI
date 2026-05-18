"""Backfill backend config — loaded from env / .env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    backfill_backend_port: int = 8001
    backfill_database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/backfill"
    backfill_cors_origins: str = "http://localhost:3000"


settings = Settings()
