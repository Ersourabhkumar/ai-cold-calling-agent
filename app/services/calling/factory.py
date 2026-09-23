from __future__ import annotations

import os

from app.services.calling.mock_provider import MockCallingProvider
from app.services.calling.provider import CallingProvider
from app.services.calling.sarvam_provider import SarvamCallingProvider


def get_calling_provider() -> CallingProvider:
    mode = (
        os.getenv("CALLING_MODE")
        or os.getenv("CALL_PROVIDER", "mock")
    ).lower()

    provider = (
        os.getenv("TELEPHONY_PROVIDER", "sarvam")
        if mode == "production"
        else mode
    ).lower()

    if mode == "production" and provider in {"mock", "test", "local"}:
        raise ValueError(
            f"CALLING_MODE is production but TELEPHONY_PROVIDER is '{provider}'. "
            "Mock providers must never be selected in production."
        )

    if provider in {"mock", "test", "local"}:
        return MockCallingProvider()

    if provider == "sarvam":
        return SarvamCallingProvider()

    raise ValueError(
        f"Unsupported calling provider: {provider}"
    )