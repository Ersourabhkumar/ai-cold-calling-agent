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
            f"(sarvam, tabbly, plivo or twilio)."
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

    if provider == "tabbly":
        if not env("TABBLY_API_KEY"):
            health.errors.append("TABBLY_API_KEY is required for provider tabbly")
        if not env("TABBLY_AGENT_ID") and not env("TABLLY_AGENT_ID"):
            health.errors.append(
                "TABBLY_AGENT_ID is required for provider tabbly"
            )
        if not env("TABBLY_PHONE_NUMBER") and not env("TABLLY_PHONE_NUMBER"):
            health.warnings.append(
                "TABBLY_PHONE_NUMBER is not set; the provider will not be "
                "able to verify the configured agent phone."
            )
        if not env("TABBLY_ORGANIZATION_ID"):
            health.warnings.append(
                "TABBLY_ORGANIZATION_ID is not set; call-log reconciliation "
                "and status sync will not work until it is configured."
            )
        if not env("TABBLY_WEBHOOK_SECRET"):
            health.warnings.append(
                "TABBLY_WEBHOOK_SECRET is not set; status webhooks will be "
                "accepted without signature validation."
            )
        return

    if provider == "twilio":
        for key in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER"):
            if not env(key):
                health.errors.append(f"{key} is required for provider twilio")
        return

    if provider == "plivo":
        for key in ("PLIVO_AUTH_ID", "PLIVO_AUTH_TOKEN", "PLIVO_PHONE_NUMBER"):
            if not env(key):
                health.errors.append(f"{key} is required for provider plivo")
        return

    health.errors.append(f"Unknown TELEPHONY_PROVIDER {provider!r}")


def validate_production_config() -> ProductionHealth:
    """Inspect the environment and report production configuration issues.

    Returns structured health without raising; callers decide whether to fail
    startup (production) or merely log (development) the findings.
    """
    health = ProductionHealth()

    if is_production():
        _check_provider_config(health, env("TELEPHONY_PROVIDER", "tabbly") or "tabbly")

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