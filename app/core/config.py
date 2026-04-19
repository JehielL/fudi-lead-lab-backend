from functools import lru_cache
from typing import Annotated

from pydantic import AnyUrl, BeforeValidator, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_csv(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        return value
    return [item.strip() for item in value.split(",") if item.strip()]


CsvList = Annotated[list[str], BeforeValidator(_split_csv)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Fudi Lead Lab API"
    app_version: str = "0.1.0"
    environment: str = "local"
    api_v1_prefix: str = "/api/v1"
    docs_enabled: bool = True
    log_level: str = "INFO"

    cors_origins: CsvList = Field(default_factory=lambda: ["http://localhost:5173"])

    jwt_secret_key: SecretStr = Field(default=SecretStr("change-me-in-env"))
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 60

    admin_username: str = "admin@fudi.local"
    admin_password: SecretStr = Field(default=SecretStr("admin"))
    admin_display_name: str = "Fudi Admin"

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "fudi_lead_lab"

    redis_url: str = "redis://localhost:6379/0"

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: SecretStr = Field(default=SecretStr("minioadmin"))
    minio_secure: bool = False
    minio_bucket: str = "fudi-lead-lab"

    smtp_send_enabled: bool = False
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from_email: str = "noreply@fudi.local"
    smtp_use_tls: bool = True
    smtp_timeout_seconds: float = 10.0
    outreach_max_attempts: int = 3

    dependency_check_timeout_seconds: float = 1.5

    @property
    def normalized_environment(self) -> str:
        return self.environment.lower().strip()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
