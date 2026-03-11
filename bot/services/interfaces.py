from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(slots=True)
class IntentResult:
    intent: str
    confidence: float


class IIntentRecognizer(ABC):
    @abstractmethod
    async def detect_intent(self, text: str, context: dict[str, Any] | None = None) -> IntentResult:
        """Detect user intent from free text."""


@dataclass(slots=True)
class ExtractedEntities:
    name: str | None = None
    phone: str | None = None
    service: str | None = None
    doctor: str | None = None
    date: str | None = None
    time: str | None = None


class IEntityExtractor(ABC):
    @abstractmethod
    async def extract(self, text: str, context: dict[str, Any] | None = None) -> ExtractedEntities:
        """Extract structured entities from free text."""


class ICrmClient(Protocol):
    async def create_appointment(self, payload: dict[str, Any]) -> None:  # pragma: no cover - external integration
        """Send appointment data to external CRM."""

    async def notify_admin(self, payload: dict[str, Any]) -> None:  # pragma: no cover - external integration
        """Notify external CRM / admin about important event."""

