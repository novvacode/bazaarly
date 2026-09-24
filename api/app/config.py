"""Application settings loaded from environment variables (SPEC §20).

`get_settings()` fails fast with a readable message when a variable required for the
current `APP_ENV` is missing or insecure.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_JWT_SECRET = "change-me-to-64-random-chars"  # noqa: S105 - placeholder, rejected in prod


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(_REPO_ROOT / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Common ---
    app_env: Literal["local", "test", "production"] = "local"
    app_base_url: str = "http://localhost:3000"

    # --- API ---
    database_url: str = "postgresql+asyncpg://bazaarly:bazaarly@localhost:5432/bazaarly"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = _DEFAULT_JWT_SECRET
    access_token_ttl_min: int = 15
    refresh_token_ttl_days: int = 30
    cors_origins: str = "http://localhost:3000"

    # --- Storage ---
    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_bucket: str = "bazaarly"
    s3_access_key_id: str = "minioadmin"
    s3_secret_access_key: str = "minioadmin"  # noqa: S105 - local MinIO default
    s3_public_base_url: str = "http://localhost:9000/bazaarly"
    s3_region: str = "auto"

    # --- Email ---
    email_provider: Literal["smtp", "resend", "memory"] = "smtp"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    resend_api_key: str = ""
    email_from: str = "Bazaarly <orders@example.com>"

    # --- Payments ---
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    razorpay_base_url: str = "https://api.razorpay.com"

    # --- AI assistant ---
    llm_provider: Literal["anthropic", "fake"] = "anthropic"
    llm_model: str = "claude-haiku-4-5"
    anthropic_api_key: str = ""
    embedder: Literal["fastembed", "fake"] = "fastembed"
    rag_min_similarity: float = 0.45
    assistant_daily_cap: int = 300

    # --- Queue ---
    worker_concurrency: int = 4
    job_default_max_attempts: int = 5
    daily_summary_hour: int = Field(default=21, ge=0, le=23)

    # --- Observability ---
    sentry_dsn: str = ""
    log_level: str = "INFO"
    slow_query_ms: int = 200

    # --- Rate limiting ---
    rate_limit_enabled: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cookie_secure(self) -> bool:
        return self.app_base_url.startswith("https://")

    @model_validator(mode="after")
    def _check_required(self) -> Settings:
        if self.app_env != "production":
            return self
        problems: list[str] = []
        if self.jwt_secret == _DEFAULT_JWT_SECRET or len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET must be set to a random string of at least 32 chars")
        required = {
            "RAZORPAY_KEY_ID": self.razorpay_key_id,
            "RAZORPAY_KEY_SECRET": self.razorpay_key_secret,
            "RAZORPAY_WEBHOOK_SECRET": self.razorpay_webhook_secret,
        }
        if self.email_provider == "resend":
            required["RESEND_API_KEY"] = self.resend_api_key
        if self.llm_provider == "anthropic":
            required["ANTHROPIC_API_KEY"] = self.anthropic_api_key
        problems += [f"{name} is required in production" for name, v in required.items() if not v]
        if problems:
            raise ValueError("; ".join(problems))
        return self


class ConfigError(RuntimeError):
    pass


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        lines = [
            f"  - {'.'.join(map(str, e['loc'])) or 'settings'}: {e['msg']}" for e in exc.errors()
        ]
        raise ConfigError("Invalid configuration:\n" + "\n".join(lines)) from None
