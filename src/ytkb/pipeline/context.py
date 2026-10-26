"""Contesto della pipeline: configurazione, database e adapter esterni (iniettabili nei test)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from ytkb.config import Settings
from ytkb.db import Database
from ytkb.errors import ConfigError
from ytkb.llm.base import LLMProvider, LLMUsage
from ytkb.models import VideoMeta
from ytkb.utils.timeutil import utcnow
from ytkb.youtube.transcripts import TranscriptService


class Notifier(Protocol):
    def video_done(self, *, video_id: str, title: str, channel: str, summary_html: str, report_html: Any,
                   requested_by: str | None) -> None: ...

    def video_failed(self, *, video_id: str, title: str, error: str, requested_by: str | None) -> None: ...


@dataclass
class PipelineContext:
    settings: Settings
    db: Database
    llm: LLMProvider
    fetch_metadata: Callable[[str], VideoMeta]
    transcripts: TranscriptService
    capturer: Any | None = None  # ytkb.youtube.media.FrameCapturer (fase 2)
    notifier: Notifier | None = None
    channel_filters: Callable[[str], dict[str, Any] | None] = field(default=lambda _cid: None)
    clock: Callable[[], datetime] = utcnow
    current_video_id: str | None = None

    def record_usage(self, purpose: str, usage: LLMUsage | None) -> None:
        if usage is None:
            return
        self.db.record_llm_call(
            video_id=self.current_video_id, purpose=purpose, model=usage.model, service_tier=usage.service_tier,
            input_tokens=usage.input_tokens, output_tokens=usage.output_tokens, thought_tokens=usage.thought_tokens,
            video_tokens=usage.video_tokens, cost_usd=usage.cost_usd, now=self.clock(),
        )


def make_provider(settings: Settings) -> LLMProvider:
    if settings.llm.provider == "fake":
        from ytkb.llm.fake import FakeProvider

        return FakeProvider()
    key = settings.secrets.reveal(settings.secrets.gemini_api_key)
    if not key:
        raise ConfigError("GEMINI_API_KEY mancante: inseriscila nel file .env "
                          "(per una prova senza chiave imposta llm.provider: fake in config/settings.yaml)")
    from ytkb.llm.gemini import GeminiProvider

    return GeminiProvider(key, settings.llm)


def build_context(settings: Settings, db: Database, llm: LLMProvider | None = None) -> PipelineContext:
    """Contesto con gli adapter reali (YouTube, Gemini)."""
    from ytkb.llm.transcribe import GeminiUrlTranscriptSource
    from ytkb.youtube.metadata import fetch_metadata
    from ytkb.youtube.transcripts import TranscriptApiSource, YtdlpSubsSource

    provider = llm or make_provider(settings)
    ctx = PipelineContext(
        settings=settings, db=db, llm=provider,
        fetch_metadata=lambda vid: fetch_metadata(vid, settings),
        transcripts=TranscriptService(settings, {}),
    )
    ctx.transcripts = TranscriptService(settings, {
        "transcript_api": TranscriptApiSource(settings),
        "ytdlp_subs": YtdlpSubsSource(settings),
        "gemini_url": GeminiUrlTranscriptSource(settings, provider, ctx.record_usage),
    })
    try:
        from ytkb.youtube.media import FrameCapturer

        ctx.capturer = FrameCapturer(settings)
    except ImportError:  # pragma: no cover - fase 2 non ancora installata
        ctx.capturer = None
    try:
        from ytkb.youtube.channels import channel_filter_lookup

        ctx.channel_filters = channel_filter_lookup(settings)
    except ImportError:  # pragma: no cover
        pass
    if settings.telegram.enabled:
        try:
            from ytkb.notify.telegram import TelegramNotifier

            ctx.notifier = TelegramNotifier.from_settings(settings)
        except ImportError:  # pragma: no cover
            pass
    return ctx
