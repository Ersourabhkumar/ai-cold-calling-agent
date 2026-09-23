from __future__ import annotations

import os
from dataclasses import dataclass, field


def env(key: str, default: str | None = None) -> str | None:
    value = os.getenv(key)
    if value is None or not value.strip():
        return default
    return value.strip()


def is_production() -> bool:
    return (env("CALLING_MODE", "mock") or "mock").lower() == "production"


def _require(values: dict[str, str | None], key: str) -> bool:
    return bool(values.get(key))


@dataclass
class ProductionHealth:
    """Outcome of a production configuration check."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _check_provider_config(health: ProductionHealth, provider: str) -> None:
    provider = provider.lower()

    if provider in {"mock", "test", "local"}:
        health.errors.append(
            f"CALLING_MODE=production cannot use telephony provider "
            f"{provider!r}. Set TELEPHONY_PROVIDER to a real provider "
            f"(sarvam)."
        )
        return

    if provider == "sarvam":
        for key in ("SARVAM_API_KEY", "SARVAM_ORG_ID", "SARVAM_WORKSPACE_ID", "SARVAM_APP_ID"):
            if not env(key):
                health.errors.append(f"{key} is required for provider sarvam")
        for key in ("SARVAM_CONNECTION_ID", "SARVAM_AGENT_PHONE_NUMBER"):
            if not env(key):
                health.warnings.append(f"{key} is not set; sarvam calls will fail")
        return

    health.errors.append(f"Unknown TELEPHONY_PROVIDER {provider!r}")


def validate_production_config() -> ProductionHealth:
    """Inspect the environment and report production configuration issues.

    Returns structured health without raising; callers decide whether to fail
    startup (production) or merely log (development) the findings.
    """
    health = ProductionHealth()

    if is_production():
        _check_provider_config(health, env("TELEPHONY_PROVIDER", "sarvam") or "sarvam")

        database_url = env("DATABASE_URL", "") or ""
        if database_url.lower().startswith("sqlite"):
            health.errors.append(
                "DATABASE_URL must not be SQLite in production; "
                "use PostgreSQL (postgresql+psycopg://...)."
            )

        if not env("REDIS_URL"):
            health.warnings.append(
                "REDIS_URL is not set; Celery dispatch and rate limiting "
                "will not be shared across workers."
            )
    else:
        health.warnings.append(
            f"CALLING_MODE={env('CALLING_MODE', 'mock')!r}; provider dispatch "
            "is local and no live calls will be placed."
        )

    if not env("PUBLIC_BASE_URL"):
        health.warnings.append(
            "PUBLIC_BASE_URL is not set; webhook URLs will default to "
            "http://localhost:8000."
        )
    elif (
        is_production()
        and not (env("PUBLIC_BASE_URL") or "").lower().startswith("https://")
    ):
        health.warnings.append(
            "PUBLIC_BASE_URL should use https:// in production so provider "
            "webhooks reach the service."
        )

    if not env("API_KEY"):
        health.warnings.append(
            "API_KEY is not set; /api endpoints have no authentication."
        )

    llm_mode = (env("LLM_MODE", "test") or "test").lower()
    if is_production() and llm_mode == "test":
        health.warnings.append(
            "LLM_MODE=test in production; conversations will use the "
            "deterministic test engine instead of a live LLM."
        )

    return health