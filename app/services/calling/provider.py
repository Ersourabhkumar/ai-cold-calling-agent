from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CallRequest:
    phone_number: str
    call_id: int
    lead_id: int
    campaign_id: int
    webhook_url: str
    lead_context: dict[str, str] | None = None


@dataclass(frozen=True)
class CallResult:
    provider: str
    provider_call_id: str
    status: str
    metadata: dict[str, Any] | None = field(default=None)


class CallingProvider(ABC):
    """
    Abstract interface for all telephony providers.

    Production code should depend on this interface,
    not directly on any single provider.
    """

    @abstractmethod
    def start_call(self, request: CallRequest) -> CallResult:
        raise NotImplementedError

    @abstractmethod
    def hangup_call(self, provider_call_id: str) -> None:
        raise NotImplementedError