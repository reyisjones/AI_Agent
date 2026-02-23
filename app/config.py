"""
Central configuration — all settings sourced from environment variables.
Secrets are never hardcoded; use .env locally or Azure Key Vault references
in Container Apps.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── OpenAI ──────────────────────────────────────────────────────────────
    openai_api_key: str = Field(..., description="OpenAI API key")
    openai_model: str = Field(default="gpt-4o", description="Model to use")
    openai_max_tokens: int = Field(default=4096)
    openai_temperature: float = Field(default=0.2)

    # ── API server ───────────────────────────────────────────────────────────
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)
    app_env: Literal["development", "staging", "production"] = Field(
        default="development"
    )
    log_level: str = Field(default="INFO")

    # ── Redis (short-term memory) ────────────────────────────────────────────
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL; leave blank to use in-memory fallback",
    )
    session_ttl_seconds: int = Field(
        default=3600, description="Session TTL in Redis"
    )

    # ── Postgres (long-term memory) ──────────────────────────────────────────
    postgres_dsn: str = Field(
        default="postgresql+asyncpg://agent:agentpass@localhost:5432/agentdb",
        description="Async Postgres DSN",
    )

    # ── Tool safety ──────────────────────────────────────────────────────────
    allowed_http_domains: list[str] = Field(
        default=["api.openai.com", "httpbin.org", "jsonplaceholder.typicode.com"],
        description="Allowlist of domains for the http_request tool",
    )
    tool_timeout_seconds: float = Field(default=10.0)
    tool_rate_limit_per_minute: int = Field(default=30)

    # ── Knowledge base ───────────────────────────────────────────────────────
    docs_path: str = Field(
        default="docs/", description="Local folder searched by knowledge_search tool"
    )

    # ── Observability ────────────────────────────────────────────────────────
    otlp_endpoint: str = Field(
        default="", description="OTLP gRPC endpoint, e.g. http://localhost:4317"
    )
    service_name: str = Field(default="ai-agent")
    service_version: str = Field(default="0.1.0")

    # ── Azure Key Vault (optional) ────────────────────────────────────────────
    azure_keyvault_url: str = Field(
        default="", description="Key Vault URL for production secrets"
    )

    @field_validator("allowed_http_domains", mode="before")
    @classmethod
    def _split_domains(cls, v: object) -> object:
        if isinstance(v, str):
            return [d.strip() for d in v.split(",") if d.strip()]
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
