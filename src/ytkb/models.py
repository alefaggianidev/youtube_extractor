"""Modelli di dominio condivisi da tutta la pipeline."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from ytkb.utils.text import fmt_ts


class VideoStatus(StrEnum):
    QUEUED = "queued"          # pronto da lavorare (subito o a next_attempt_at)
    WAITING = "waiting"        # YouTube non è ancora pronto (premiere, live, sottotitoli)
    PROCESSING = "processing"  # in lavorazione
    DONE = "done"              # report pronto
    SKIPPED = "skipped"        # scartato di proposito (Short, filtri, solo membri)
    FAILED = "failed"          # fallito dopo i tentativi o per errore permanente


class Stage(StrEnum):
    METADATA = "metadata"
    TRANSCRIPT = "transcript"
    ANALYSIS = "analysis"
    LOCATE = "locate"
    CAPTURE = "capture"
    READ = "read"
    RENDER = "render"
    PUBLISH = "publish"


class LiveStatus(StrEnum):
    NOT_LIVE = "not_live"
    IS_LIVE = "is_live"
    IS_UPCOMING = "is_upcoming"
    WAS_LIVE = "was_live"
    POST_LIVE = "post_live"  # live finita, ma YouTube sta ancora elaborando
    UNKNOWN = "unknown"


class Chapter(BaseModel):
    title: str
    start_s: float
    end_s: float | None = None


class VideoMeta(BaseModel):
    """Informazioni su un video ottenute da yt-dlp senza scaricarlo."""

    video_id: str
    title: str
    channel_id: str = ""
    channel_title: str = ""
    channel_handle: str = ""
    upload_date: date | None = None
    published_at: datetime | None = None
    release_at: datetime | None = None  # orario di inizio di premiere/live programmate
    duration_s: float | None = None
    live_status: LiveStatus = LiveStatus.UNKNOWN
    media_type: str = "video"  # video | short | livestream
    availability: str = "unknown"  # public | unlisted | private | subscriber_only | needs_auth ...
    language: str | None = None
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    chapters: list[Chapter] = Field(default_factory=list)
    width: int | None = None
    height: int | None = None
    thumbnail: str = ""
    subtitle_langs: list[str] = Field(default_factory=list)  # sottotitoli manuali disponibili
    auto_caption_langs: list[str] = Field(default_factory=list)  # sottotitoli automatici disponibili

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"

    @property
    def is_short(self) -> bool:
        if self.media_type == "short":
            return True
        vertical = bool(self.width and self.height and self.height > self.width)
        return vertical and (self.duration_s or 0) <= 180

    @property
    def is_public(self) -> bool:
        return self.availability in ("public", "unknown")

    @property
    def original_caption_lang(self) -> str | None:
        """Lingua dei sottotitoli automatici "originali" (yt-dlp li marca con suffisso -orig)."""
        for lang in self.auto_caption_langs:
            if lang.endswith("-orig"):
                return lang.removesuffix("-orig")
        return None


class TranscriptSegment(BaseModel):
    id: int
    start: float
    end: float
    text: str

    @property
    def label(self) -> str:
        return f"S{self.id:03d}"


class Transcript(BaseModel):
    video_id: str
    language: str
    source: str  # transcript_api | ytdlp_subs | gemini_url
    is_generated: bool = True
    segments: list[TranscriptSegment]

    def segment(self, segment_id: int) -> TranscriptSegment | None:
        if 0 <= segment_id < len(self.segments) and self.segments[segment_id].id == segment_id:
            return self.segments[segment_id]
        return next((s for s in self.segments if s.id == segment_id), None)

    def clamp_id(self, segment_id: int) -> int:
        if not self.segments:
            return 0
        return max(self.segments[0].id, min(self.segments[-1].id, int(segment_id)))

    def text_of(self, start_id: int, end_id: int | None = None, context: int = 0) -> str:
        end_id = start_id if end_id is None else end_id
        lo, hi = min(start_id, end_id) - context, max(start_id, end_id) + context
        return " ".join(s.text for s in self.segments if lo <= s.id <= hi)

    def to_prompt(self) -> str:
        """Testo per l'LLM: una riga per segmento, ``[S042 13:12] testo``."""
        return "\n".join(f"[{s.label} {fmt_ts(s.start)}] {s.text}" for s in self.segments)

    def to_readable(self) -> str:
        """Testo per le persone: ``[13:12] testo``."""
        return "\n".join(f"[{fmt_ts(s.start)}] {s.text}" for s in self.segments)

    @property
    def duration_s(self) -> float:
        return self.segments[-1].end if self.segments else 0.0
