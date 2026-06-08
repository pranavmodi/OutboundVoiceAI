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
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_sms_from_number: str = ""
    backfill_sms_provider: str = "mock"
    backfill_public_base_url: str = ""
    twilio_webhook_auth_enabled: bool = False
    backfill_voice_provider: str = "twilio"
    backfill_appointment_api_base_url: str = ""
    backfill_appointment_api_token: str = ""
    backfill_wave_worker_enabled: bool = False
    backfill_wave_worker_poll_seconds: int = 15
    backfill_wave_worker_batch_size: int = 25


settings = Settings()
