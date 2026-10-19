from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from environment variables (see .env.example). Secrets are never hard-coded."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    app_name: str = "AgentForge Academy"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"

    database_url: str = "postgresql+psycopg://agentforge:agentforge@localhost:5432/agentforge"
    db_pool_size: int = 10
    db_echo: bool = False

    # Sessions & cookies
    session_cookie: str = "af_session"
    csrf_cookie: str = "af_csrf"
    session_ttl_hours: int = 24 * 14
    cookie_secure: bool = False
    cookie_domain: str | None = None
    # NoDecode: accept "a,b" as well as a JSON list (parsed by the validator below)
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:5173"])
    frontend_url: str = "http://localhost:5173"
    trusted_proxies: int = 0

    # Email (console backend logs links instead of sending - development only)
    mail_backend: Literal["console", "smtp"] = "console"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    mail_from: str = "AgentForge Academy <no-reply@example.com>"

    # Rate limits (requests per window)
    rate_limit_auth_per_minute: int = 10
    rate_limit_sandbox_per_minute: int = 30
    rate_limit_agent_runs_per_minute: int = 10

    # Sandbox runner (isolated service). Empty URL => code execution is disabled and labelled as such.
    sandbox_url: str = ""
    sandbox_token: str = ""
    sandbox_timeout_ms: int = 5000

    # Model providers (server-side only; never sent to the browser)
    llm_provider: Literal["mock", "openai", "anthropic"] = "mock"
    openai_api_key: str = ""
    openai_model: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str = ""
    anthropic_model: str = ""
    # JSON map: {"model-name": {"input_per_mtok": 0.25, "output_per_mtok": 1.25}} for cost estimates
    model_prices: dict[str, dict[str, float]] = Field(default_factory=dict)
    agent_run_timeout_s: int = 60

    # Seed accounts (development convenience; disabled in production unless explicitly set)
    seed_admin_email: str = "admin@example.com"
    seed_admin_password: str = "ChangeMe-Admin-123!"
    seed_demo_email: str = "learner@example.com"
    seed_demo_password: str = "ChangeMe-Learner-123!"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return json.loads(v) if v.startswith("[") else [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("model_prices", mode="before")
    @classmethod
    def _parse_prices(cls, v):
        return json.loads(v) if isinstance(v, str) and v.strip() else (v or {})

    @model_validator(mode="after")
    def _production_guards(self) -> Settings:
        if self.env == "production":
            problems = []
            if not self.cookie_secure:
                problems.append("COOKIE_SECURE must be true")
            if self.mail_backend == "console":
                problems.append("MAIL_BACKEND must be smtp")
            if self.sandbox_url and not self.sandbox_token:
                problems.append("SANDBOX_TOKEN is required when SANDBOX_URL is set")
            if "ChangeMe" in self.seed_admin_password:
                problems.append("SEED_ADMIN_PASSWORD must be changed")
            if problems:
                raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self

    @property
    def is_test(self) -> bool:
        return self.env == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()
