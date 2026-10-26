"""Interfaccia comune dei provider LLM.

La pipeline parla solo con ``LLMProvider``: cambiare modello o fornitore non tocca il resto del codice.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Generic, Protocol, TypeVar

from pydantic import BaseModel

from ytkb.errors import PermanentError, TemporaryError

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class TextPart:
    text: str


@dataclass(frozen=True)
class ImagePart:
    data: bytes
    mime_type: str = "image/jpeg"
    resolution: str = "high"  # low | medium | high | ultra_high


@dataclass(frozen=True)
class VideoUrlPart:
    """Un video YouTube passato per link; opzionalmente solo una finestra [start_s, end_s]."""

    url: str
    start_s: float | None = None
    end_s: float | None = None
    fps: float | None = None
    resolution: str | None = None  # low | medium | high


Part = TextPart | ImagePart | VideoUrlPart


@dataclass
class LLMUsage:
    model: str
    service_tier: str = "standard"
    input_tokens: int = 0
    output_tokens: int = 0
    thought_tokens: int = 0
    video_tokens: int = 0  # token di video/audio provenienti da link YouTube
    cost_usd: float = 0.0
    calls: int = 1

    def add(self, other: LLMUsage) -> LLMUsage:
        return LLMUsage(
            model=other.model or self.model,
            service_tier=other.service_tier or self.service_tier,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            thought_tokens=self.thought_tokens + other.thought_tokens,
            video_tokens=self.video_tokens + other.video_tokens,
            cost_usd=self.cost_usd + other.cost_usd,
            calls=self.calls + other.calls,
        )


@dataclass
class LLMResponse(Generic[T]):
    data: T
    usage: LLMUsage
    raw_text: str = ""
    warnings: list[str] = field(default_factory=list)


class LLMOutputError(TemporaryError):
    """Il modello ha risposto con un JSON non valido anche dopo i tentativi."""

    def __init__(self, message: str, usage: LLMUsage | None = None):
        super().__init__(message)
        self.usage = usage


class LLMRequestError(PermanentError):
    """Richiesta rifiutata in modo definitivo (chiave non valida, modello inesistente, video non accessibile)."""

    def __init__(self, message: str, usage: LLMUsage | None = None):
        super().__init__(message)
        self.usage = usage


class LLMTemporaryError(TemporaryError):
    def __init__(self, message: str, usage: LLMUsage | None = None):
        super().__init__(message)
        self.usage = usage


class LLMProvider(Protocol):
    name: str

    def generate(
        self,
        *,
        purpose: str,
        model: str,
        system: str,
        parts: Sequence[Part],
        schema: type[T],
        max_output_tokens: int | None = None,
    ) -> LLMResponse[T]:
        """Genera un output strutturato conforme a ``schema`` (modello Pydantic)."""
        ...
