from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://industrial:industrial_dev_password@localhost:5432/industrial_sre"
    redis_url: str = "redis://localhost:6379/0"
    telemetry_interval_seconds: float = 1.0
    sandbox_enabled: bool = True
    sandbox_image: str = "python:3.12-alpine"
    sandbox_timeout_seconds: int = 20
    anomaly_vibration_threshold: float = 11.0
    anomaly_temperature_threshold: float = 115.0
    anomaly_pressure_threshold: float = 145.0
    anomaly_flow_min_threshold: float = 65.0
    cors_allowed_origins: str = "http://localhost:3000,http://localhost:8000"
    operator_api_token: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
