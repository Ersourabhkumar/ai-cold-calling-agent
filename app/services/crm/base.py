"""CRM provider abstraction (mirrors the calling-provider pattern)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class CRMProvider(ABC):
    """Push completed-call results out of the system."""

    name: str = "base"

    @abstractmethod
    def push_call_result(self, payload: dict) -> dict:
        raise NotImplementedError
