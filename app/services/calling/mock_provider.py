from __future__ import annotations

import uuid

from app.services.calling.provider import (
    CallRequest,
    CallResult,
    CallingProvider,
)


class MockCallingProvider(CallingProvider):
    """
    Free local provider used for development/testing.

    No real phone call is placed.
    """

    def start_call(self, request: CallRequest) -> CallResult:
        provider_call_id = f"mock-{uuid.uuid4()}"

        return CallResult(
            provider="mock",
            provider_call_id=provider_call_id,
            status="INITIATED",
        )

    def hangup_call(self, provider_call_id: str) -> None:
        return None