"""Fonte di trascrizione ``gemini_url``: Gemini ascolta il video direttamente dal link YouTube.

Funziona solo con video pubblici. Per i video lunghi si procede a blocchi (``transcript.gemini_chunk_minutes``),
usando il ritaglio della finestra (start/end offset) e pochi fotogrammi a bassa risoluzione: ci interessa l'audio.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence

from ytkb.config import Settings
from ytkb.errors import PermanentError
from ytkb.llm.base import LLMProvider, LLMUsage, TextPart, VideoUrlPart
from ytkb.llm.prompting import render_prompt
from ytkb.llm.schemas import GeminiTranscript
from ytkb.models import VideoMeta
from ytkb.youtube.transcripts import RawSnippet, RawTranscript, TranscriptUnavailable

log = logging.getLogger(__name__)

UsageRecorder = Callable[[str, LLMUsage], None]


def resolve_offset(value: float, start: float, end: float) -> float:
    """Il modello può rispondere in secondi relativi alla clip o assoluti: riportiamo tutto ad assoluto."""
    length = end - start
    if start > 0 and start - 1 <= value <= end + 1 and value > length + 1:
        return value  # già assoluto
    return start + max(0.0, min(value, length))


def windows(duration_s: float, chunk_s: float) -> list[tuple[float, float]]:
    out, t = [], 0.0
    while t < duration_s:
        out.append((t, min(duration_s, t + chunk_s)))
        t += chunk_s
    return out


class GeminiUrlTranscriptSource:
    name = "gemini_url"

    def __init__(self, settings: Settings, provider: LLMProvider, record_usage: UsageRecorder | None = None):
        self._settings = settings
        self._provider = provider
        self._record = record_usage or (lambda purpose, usage: None)

    def fetch(self, meta: VideoMeta, languages: Sequence[str]) -> RawTranscript:
        if not meta.duration_s:
            raise TranscriptUnavailable("durata sconosciuta: impossibile trascrivere a blocchi")
        chunk_s = self._settings.transcript.gemini_chunk_minutes * 60
        snippets: list[RawSnippet] = []
        language = ""
        system = render_prompt("transcribe_system")
        for start, end in windows(meta.duration_s, chunk_s):
            parts = [
                VideoUrlPart(url=meta.url, start_s=start, end_s=end, fps=0.1, resolution="low"),
                TextPart(render_prompt("transcribe_user", start=round(start), end=round(end),
                                       title=meta.title, languages=", ".join(languages))),
            ]
            try:
                resp = self._provider.generate(purpose="transcribe", model=self._settings.llm.models.transcribe,
                                               system=system, parts=parts, schema=GeminiTranscript,
                                               max_output_tokens=max(32000, self._settings.llm.max_output_tokens))
            except PermanentError as exc:
                usage = getattr(exc, "usage", None)
                if usage:
                    self._record("transcribe", usage)
                raise TranscriptUnavailable(f"Gemini non può accedere al video: {exc}") from exc
            self._record("transcribe", resp.usage)
            language = language or resp.data.language
            lines = sorted(resp.data.lines, key=lambda line: line.start_s)
            for i, line in enumerate(lines):
                t0 = resolve_offset(line.start_s, start, end)
                t1 = resolve_offset(lines[i + 1].start_s, start, end) if i + 1 < len(lines) else end
                if line.text.strip():
                    snippets.append(RawSnippet(t0, max(0.5, t1 - t0), line.text.strip()))
        if not snippets:
            raise TranscriptUnavailable("Gemini ha restituito una trascrizione vuota")
        log.info("Trascrizione Gemini: %d righe", len(snippets))
        return RawTranscript(language or (meta.language or "it"), True, self.name, snippets)
